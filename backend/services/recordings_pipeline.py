"""Phase 1: headless transcript pipeline.

media in -> transcribe -> brand-glossary correct -> two transcript outputs:
  1. a timestamped CUT transcript (corrected, drives the edit)
  2. a clean READABLE Markdown transcript (brand-voice, numbers formatted)
plus a review-flags list (proper names / ambiguous terms a human must confirm).

This is the part that retires Descript for the transcript path. No video cutting
yet - that is Phase 2.
"""

import json
import tempfile
from pathlib import Path
from typing import Callable, Optional

from .whisper_service import transcribe_audio
from .glossary import load_corrections, correct_transcript_text
from .readable_pass import make_readable


AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


def _fmt_ts(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def _ensure_audio(media_path: Path) -> tuple[Path, Optional[Path]]:
    """Return (audio_path, temp_to_cleanup). Extracts audio from video inputs."""
    if media_path.suffix.lower() in AUDIO_EXTS:
        return media_path, None
    from .ffmpeg_service import extract_audio
    tmp = Path(tempfile.gettempdir()) / f"rec_{media_path.stem}.wav"
    extract_audio(str(media_path), str(tmp))
    return tmp, tmp


def _cut_transcript_md(segments: list, title: str) -> str:
    lines = [f"# {title} - transcript (timestamped)", ""] if title else []
    for seg in segments:
        speaker = seg.get("speaker")
        prefix = f"[{_fmt_ts(seg.get('start', 0))}]"
        who = f" {speaker}:" if speaker else ""
        lines.append(f"{prefix}{who} {(seg.get('text') or '').strip()}")
    return "\n".join(lines) + "\n"


def _dedupe_flags(flags: list) -> list:
    seen, out = set(), []
    for f in flags:
        key = f.get("term", "").lower()
        if key and key not in seen:
            seen.add(key)
            out.append(f)
    return out


def process_recording(media_path: str, title: str = "", quality: str = "standard",
                      out_dir: Optional[str] = None, readable_llm: bool = True,
                      on_progress: Optional[Callable[[int, str], None]] = None) -> dict:
    """Run the headless transcript pipeline on a media file.

    Returns a dict with the corrected segments, the readable markdown, review
    flags, glossary changes, and (if out_dir given) the written file paths.
    """
    def progress(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    media = Path(media_path)
    if not media.exists():
        raise FileNotFoundError(f"Media not found: {media_path}")

    progress(5, "Preparing audio...")
    audio_path, tmp = _ensure_audio(media)

    try:
        progress(15, "Transcribing...")
        data = transcribe_audio(
            str(audio_path), quality=quality,
            on_progress=lambda stage, pct, msg: progress(15 + int(pct * 0.6), msg),
        )
    finally:
        if tmp and tmp.exists():
            tmp.unlink()

    segments = data.get("segments", [])

    progress(80, "Applying brand glossary...")
    corr = load_corrections()
    all_flags, all_changes = [], []
    for seg in segments:
        res = correct_transcript_text(seg.get("text", ""), corr, do_number_format=False)
        seg["text"] = res["text"]
        all_flags.extend(res["review_flags"])
        all_changes.extend(res["safe_changes"])
    review_flags = _dedupe_flags(all_flags)

    progress(88, "Writing readable transcript...")
    readable = make_readable(segments, title=title, deterministic_only=not readable_llm)

    result = {
        "title": title,
        "segment_count": len(segments),
        "segments": segments,
        "cut_transcript_md": _cut_transcript_md(segments, title),
        "readable_markdown": readable["markdown"],
        "readable_backend": readable["backend"],
        "review_flags": review_flags,
        "glossary_changes": all_changes,
    }

    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        slug = title.lower().replace(" ", "-") or media.stem
        (out / f"{slug}.cut.json").write_text(json.dumps(segments, indent=2), encoding="utf-8")
        (out / f"{slug}.cut.md").write_text(result["cut_transcript_md"], encoding="utf-8")
        (out / f"{slug}.readable.md").write_text(result["readable_markdown"], encoding="utf-8")
        (out / f"{slug}.review-flags.json").write_text(json.dumps(review_flags, indent=2), encoding="utf-8")
        result["output_dir"] = str(out)
        result["files"] = {
            "cut_json": f"{slug}.cut.json",
            "cut_md": f"{slug}.cut.md",
            "readable_md": f"{slug}.readable.md",
            "review_flags": f"{slug}.review-flags.json",
        }

    progress(100, "Done")
    return result
