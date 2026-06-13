"""Phase 1: headless transcript pipeline.

media in -> transcribe -> brand-glossary correct -> two transcript outputs:
  1. a timestamped CUT transcript (corrected, drives the edit)
  2. a clean READABLE Markdown transcript (brand-voice, numbers formatted)
plus a review-flags list (proper names / ambiguous terms a human must confirm).

This is the part that retires Descript for the transcript path. No video cutting
yet - that is Phase 2.
"""

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

from .whisper_service import transcribe_audio
from .glossary import load_corrections, correct_transcript_text
from .readable_pass import make_readable
from .cut_planner import build_edit_sheet

# Transcription is CPU-heavy; cap concurrent runs so a shared instance does not
# thrash. STUDIO_MAX_CONCURRENT (default 1) - raise it on a beefy/GPU box.
_TRANSCRIBE_GATE = threading.Semaphore(max(1, int(os.environ.get("STUDIO_MAX_CONCURRENT", "1"))))


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


def _transcribe(audio_path: str, quality: str, engine: str, progress) -> dict:
    """Route transcription. Groq (cloud, near-instant, free tier) when available
    and requested; otherwise faster-whisper at the chosen local model size.

    quality: fast=base, balanced=small, best=large-v3 (slow on CPU).
    engine:  auto (groq if GROQ_API_KEY set, else local), groq, local.
    """
    from .tool_availability import check_tool
    use_groq = engine == "groq" or (engine == "auto" and check_tool("groq"))
    if use_groq:
        try:
            from .groq_service import transcribe_audio_groq
            progress(20, "Transcribing on Groq (fast cloud)...")
            return transcribe_audio_groq(
                audio_path,
                on_progress=lambda pct, msg: progress(15 + int(pct * 0.6), msg),
            )
        except Exception as e:
            progress(16, f"Groq unavailable ({e}); using local model...")

    # local faster-whisper. Map our speed labels onto the engine's model + quality.
    # fast -> base (forced by quality="fast"); balanced -> small (single pass);
    # best -> large-v3 single pass (quality="standard"). Avoid "high" (3-pass, 3x slower).
    q = {"fast": "fast", "balanced": "balanced", "best": "standard"}.get(quality, "fast")
    model = {"fast": "base", "balanced": "small", "best": "large-v3"}.get(quality, "base")
    progress(18, f"Transcribing with the {model} model...")
    return transcribe_audio(
        audio_path, model_size=model, quality=q,
        on_progress=lambda stage, pct, msg: progress(15 + int(pct * 0.6), msg),
    )


def _detect_speakers(audio_path: str, segments: list, progress) -> list:
    """Best-effort diarization -> speaker labels on segments. Never blocks."""
    try:
        from .diarization import diarize_audio, assign_speakers_to_segments
        progress(78, "Detecting speakers...")
        turns = diarize_audio(audio_path)
        if turns:
            return assign_speakers_to_segments(segments, turns)
    except Exception as e:
        print(f"Speaker detection skipped: {e}")
    return segments


def process_recording(media_path: str, title: str = "", quality: str = "fast",
                      engine: str = "auto", out_dir: Optional[str] = None,
                      readable_llm: bool = True, plan_cuts: bool = True,
                      suggest_falsestarts: bool = False, detect_speakers: bool = False,
                      captions_url: Optional[str] = None,
                      on_progress: Optional[Callable[[int, str], None]] = None) -> dict:
    """Run the headless transcript pipeline on a media file.

    quality: fast (base model, default - viable on CPU) | balanced (small) | best (large-v3).
    engine:  auto (Groq if GROQ_API_KEY set, else local) | groq | local.
    captions_url: if set (a YouTube URL), use that video's existing captions instead
                  of running Whisper - seconds vs minutes. Falls back to Whisper if
                  no captions are available.
    detect_speakers: run diarization and label segments with speakers.

    Returns a dict with the corrected segments, the readable markdown, review
    flags, glossary changes, an edit sheet (cut plan), and (if out_dir given) the
    written file paths.
    """
    def progress(pct, msg):
        if on_progress:
            on_progress(pct, msg)

    media = Path(media_path)
    if not media.exists():
        raise FileNotFoundError(f"Media not found: {media_path}")

    # Fast path: use the YouTube VOD's existing captions, skip audio + Whisper.
    if captions_url:
        try:
            from .youtube_captions import fetch_captions
            progress(12, "Fetching YouTube captions...")
            data = fetch_captions(captions_url)
            segments = data.get("segments", [])
            if detect_speakers:
                audio_path, tmp = _ensure_audio(media)
                try:
                    segments = _detect_speakers(str(audio_path), segments, progress)
                finally:
                    if tmp and tmp.exists():
                        tmp.unlink()
            duration = data.get("duration") or (segments[-1].get("end", 0.0) if segments else 0.0)
            return _finish_pipeline(segments, duration, title, out_dir, readable_llm,
                                    plan_cuts, suggest_falsestarts, media, progress)
        except Exception as e:
            progress(10, f"No usable captions ({e}); transcribing instead...")

    progress(5, "Preparing audio...")
    audio_path, tmp = _ensure_audio(media)

    acquired = _TRANSCRIBE_GATE.acquire(timeout=0)
    if not acquired:
        progress(6, "Queued - waiting for a free transcription slot...")
        _TRANSCRIBE_GATE.acquire()
    try:
        data = _transcribe(str(audio_path), quality, engine, progress)
        segments = data.get("segments", [])
        if detect_speakers:
            segments = _detect_speakers(str(audio_path), segments, progress)
    finally:
        _TRANSCRIBE_GATE.release()
        if tmp and tmp.exists():
            tmp.unlink()

    duration = data.get("duration") or (segments[-1].get("end", 0.0) if segments else 0.0)
    return _finish_pipeline(segments, duration, title, out_dir, readable_llm,
                            plan_cuts, suggest_falsestarts, media, progress)


def _finish_pipeline(segments, duration, title, out_dir, readable_llm,
                     plan_cuts, suggest_falsestarts, media, progress):
    """Stages after transcription: glossary correct -> cut plan -> readable -> write.

    Shared by the Whisper path and the YouTube-captions fast path.
    """
    progress(80, "Applying brand glossary...")
    corr = load_corrections()
    all_flags, all_changes = [], []
    for seg in segments:
        res = correct_transcript_text(seg.get("text", ""), corr, do_number_format=False)
        seg["text"] = res["text"]
        all_flags.extend(res["review_flags"])
        all_changes.extend(res["safe_changes"])
    review_flags = _dedupe_flags(all_flags)

    progress(85, "Planning cuts...")
    edit_sheet = build_edit_sheet(
        segments, duration, include_falsestarts=suggest_falsestarts,
    ) if plan_cuts else {"duration": duration, "cuts": []}

    progress(90, "Writing readable transcript...")
    readable = make_readable(segments, title=title, deterministic_only=not readable_llm)

    result = {
        "title": title,
        "segment_count": len(segments),
        "duration": round(duration, 2),
        "segments": segments,
        "cut_transcript_md": _cut_transcript_md(segments, title),
        "readable_markdown": readable["markdown"],
        "readable_backend": readable["backend"],
        "review_flags": review_flags,
        "glossary_changes": all_changes,
        "edit_sheet": edit_sheet,
    }

    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        slug = title.lower().replace(" ", "-") or media.stem
        (out / f"{slug}.cut.json").write_text(json.dumps(segments, indent=2), encoding="utf-8")
        (out / f"{slug}.cut.md").write_text(result["cut_transcript_md"], encoding="utf-8")
        (out / f"{slug}.readable.md").write_text(result["readable_markdown"], encoding="utf-8")
        (out / f"{slug}.review-flags.json").write_text(json.dumps(review_flags, indent=2), encoding="utf-8")
        (out / f"{slug}.edit-sheet.json").write_text(json.dumps(edit_sheet, indent=2), encoding="utf-8")
        result["output_dir"] = str(out)
        result["files"] = {
            "cut_json": f"{slug}.cut.json",
            "cut_md": f"{slug}.cut.md",
            "readable_md": f"{slug}.readable.md",
            "review_flags": f"{slug}.review-flags.json",
            "edit_sheet": f"{slug}.edit-sheet.json",
        }

    progress(100, "Done")
    return result
