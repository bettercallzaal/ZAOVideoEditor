"""Fetch existing YouTube captions instead of re-transcribing.

For a YouTube VOD (the canonical recording surface), pulling the auto-captions is
seconds vs minutes of Whisper on CPU - and it matches the team's current flow
(grab YouTube auto-captions). Uses yt-dlp to download the json3 caption track,
which carries segment timing (and word offsets when present). Returns the same
{segments, raw_text} shape the rest of the pipeline expects.
"""

import json
import subprocess
import tempfile
from pathlib import Path


def captions_available() -> bool:
    """yt-dlp is what we use to fetch captions."""
    try:
        return subprocess.run(["yt-dlp", "--version"], capture_output=True, timeout=10).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _parse_json3(data: dict) -> list:
    """Parse a YouTube json3 caption track into pipeline segments."""
    segments = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if not text or text == "\n":
            continue
        start = ev.get("tStartMs", 0) / 1000.0
        dur = ev.get("dDurationMs", 0) / 1000.0
        end = start + dur
        words = []
        for s in segs:
            w = s.get("utf8", "").strip()
            if not w:
                continue
            w_start = start + s.get("tOffsetMs", 0) / 1000.0
            words.append({"word": w, "start": round(w_start, 3), "end": round(end, 3)})
        segments.append({
            "id": len(segments), "start": round(start, 3), "end": round(end, 3),
            "text": text, "words": words,
        })
    # fix word end times to the next word's start where we can
    for seg in segments:
        ws = seg["words"]
        for i in range(len(ws) - 1):
            ws[i]["end"] = ws[i + 1]["start"]
    return segments


def fetch_captions(url: str, lang: str = "en") -> dict:
    """Download the caption track for a YouTube URL. Raises if none available."""
    if not captions_available():
        raise RuntimeError("yt-dlp is not installed")
    tmp = Path(tempfile.mkdtemp(prefix="yt_caps_"))
    out_tmpl = str(tmp / "cap")
    # Prefer manual subs, fall back to auto-generated; json3 carries timing.
    cmd = [
        "yt-dlp", "--skip-download",
        "--write-subs", "--write-auto-subs",
        "--sub-langs", f"{lang},{lang}-orig,{lang}.*",
        "--sub-format", "json3",
        "--no-warnings", "-o", out_tmpl, url,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    files = list(tmp.glob("*.json3"))
    if not files:
        raise RuntimeError("No captions available for this video")
    # yt-dlp often writes several tracks (en, en-orig, a near-empty en-US stub).
    # Parse them all and keep the richest one rather than the alphabetically-first.
    segments = []
    for f in files:
        try:
            parsed = _parse_json3(json.loads(f.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            parsed = []
        if len(parsed) > len(segments):
            segments = parsed
    for f in tmp.glob("*"):
        f.unlink()
    tmp.rmdir()
    if not segments:
        raise RuntimeError("Caption track was empty")
    return {
        "segments": segments,
        "raw_text": " ".join(s["text"] for s in segments),
        "duration": segments[-1]["end"] if segments else 0.0,
        "source": "youtube-captions",
    }
