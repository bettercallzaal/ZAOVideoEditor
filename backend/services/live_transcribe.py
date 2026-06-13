"""Live (real-time) transcription: transcribe stream audio in short chunks.

The browser records the stream's audio in short clips (a fresh MediaRecorder per
clip, so each is a self-contained file) and POSTs them one at a time. We
transcribe each clip on the fast path (Groq when a key is set, else the base
Whisper model), rebase its timestamps to the clip's offset-from-start,
brand-correct the text, and append to a rolling live transcript. Pairs with
live_marks: the words scroll by while you mark the hot moments.
"""

import json
from pathlib import Path
from typing import Callable, Optional

LIVE_TRANSCRIPT_FILE = "live_transcript.json"


def _path(project_dir: Path) -> Path:
    return project_dir / LIVE_TRANSCRIPT_FILE


def _default_transcribe(audio_path: str, quality: str, engine: str) -> dict:
    """Real transcriber: routes Groq/local via the recordings pipeline."""
    from .recordings_pipeline import _transcribe
    return _transcribe(audio_path, quality, engine, lambda *_: None)


def _brand_correct(segments: list) -> list:
    """Best-effort glossary pass so the live transcript reads on-brand."""
    try:
        from .glossary import load_corrections, correct_transcript_text
        corr = load_corrections()
        for seg in segments:
            seg["text"] = correct_transcript_text(
                seg.get("text", ""), corr, do_number_format=False)["text"]
    except Exception:
        pass
    return segments


def transcribe_chunk(audio_path: str, offset: float = 0.0, quality: str = "fast",
                     engine: str = "auto",
                     transcriber: Optional[Callable] = None) -> list:
    """Transcribe one chunk, rebased to its offset-from-start, brand-corrected."""
    transcriber = transcriber or _default_transcribe
    data = transcriber(str(audio_path), quality, engine)
    rebased = []
    for s in (data.get("segments", []) or []):
        text = (s.get("text") or "").strip()
        if not text:
            continue
        rebased.append({
            "start": round(float(s.get("start", 0.0)) + offset, 2),
            "end": round(float(s.get("end", 0.0)) + offset, 2),
            "text": text,
        })
    return _brand_correct(rebased)


def _load(project_dir: Path) -> dict:
    p = _path(project_dir)
    if not p.exists():
        return {"segments": []}
    try:
        return json.loads(p.read_text())
    except (ValueError, OSError):
        return {"segments": []}


def append_chunk(project_dir: Path, audio_path: str, offset: float = 0.0,
                 quality: str = "fast", engine: str = "auto",
                 transcriber: Optional[Callable] = None) -> dict:
    """Transcribe a chunk and append it to the rolling live transcript."""
    new_segs = transcribe_chunk(audio_path, offset=offset, quality=quality,
                                engine=engine, transcriber=transcriber)
    state = _load(project_dir)
    state["segments"].extend(new_segs)
    state["segments"].sort(key=lambda s: s["start"])
    _path(project_dir).write_text(json.dumps(state, indent=2), encoding="utf-8")
    return {"added": new_segs, "count": len(state["segments"])}


def get_live_transcript(project_dir: Path) -> dict:
    state = _load(project_dir)
    segs = state.get("segments", [])
    return {"segments": segs, "text": " ".join(s["text"] for s in segs),
            "count": len(segs)}
