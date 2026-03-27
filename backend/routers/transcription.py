from pathlib import Path
from fastapi import APIRouter, HTTPException
from ..models.schemas import TranscriptionRequest
from ..services.whisper_service import transcribe_audio, save_transcript, load_transcript
from ..services.ffmpeg_service import extract_audio
from ..services import task_manager as tm

router = APIRouter(prefix="/api/transcription", tags=["transcription"])

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"


def _do_transcribe(task_id: str, project_dir: Path, model_size: str,
                   quality: str, engine: str, refine: bool):
    """Background transcription worker with multi-engine support."""
    tm.update_task(task_id, progress=2, message="Checking audio...")

    audio_path = project_dir / "processing" / "audio.wav"
    if not audio_path.exists():
        tm.update_task(task_id, progress=3, message="Extracting audio...")
        # Prefer trimmed video if silence removal was done
        video_path = project_dir / "processing" / "trimmed.mp4"
        if not video_path.exists():
            video_path = project_dir / "processing" / "assembled.mp4"
        if not video_path.exists():
            for ext in [".mp4", ".mov", ".mkv", ".webm"]:
                p = project_dir / "input" / f"main{ext}"
                if p.exists():
                    video_path = p
                    break
        extract_audio(str(video_path), str(audio_path))

    def on_progress(step, pct, message):
        tm.update_task(task_id, progress=int(pct), message=message)

    # Determine which engine to use
    actual_engine = _resolve_engine(engine)

    tm.update_task(
        task_id, progress=5,
        message=f"Starting {quality} transcription ({actual_engine})...",
    )

    if actual_engine == "groq":
        from ..services.groq_service import transcribe_audio_groq
        transcript_data = transcribe_audio_groq(
            str(audio_path),
            on_progress=lambda pct, msg: tm.update_task(task_id, progress=int(pct), message=msg),
        )
    elif actual_engine == "whisperx":
        from ..services.whisperx_service import transcribe_audio_whisperx
        transcript_data = transcribe_audio_whisperx(
            str(audio_path),
            quality=quality,
            on_progress=lambda p, m: tm.update_task(task_id, progress=int(p * 0.85), message=m),
        )
    else:
        transcript_data = transcribe_audio(
            str(audio_path),
            model_size=model_size,
            quality=quality,
            on_progress=on_progress,
        )

    # Optional timestamp refinement with stable-ts
    if refine:
        try:
            from ..services.tool_availability import check_tool
            if check_tool("stable_ts"):
                tm.update_task(task_id, progress=88, message="Refining timestamps (stable-ts)...")
                from ..services.stable_ts_service import refine_timestamps
                transcript_data["segments"] = refine_timestamps(
                    str(audio_path), transcript_data["segments"],
                    on_progress=lambda p, m: tm.update_task(
                        task_id, progress=88 + int(p * 0.07), message=m,
                    ),
                )
                transcript_data["timestamp_refined"] = True
        except Exception as e:
            # Non-fatal — keep original timestamps
            tm.update_task(task_id, progress=92, message=f"Timestamp refinement skipped: {e}")

    tm.update_task(task_id, progress=95, message="Saving transcript...")

    raw_path = project_dir / "transcripts" / "raw.json"
    save_transcript(transcript_data, str(raw_path))

    raw_text_path = project_dir / "transcripts" / "raw.txt"
    with open(raw_text_path, "w") as f:
        f.write(transcript_data["raw_text"])

    passes = transcript_data.get("passes", 1)
    return {
        "segments": len(transcript_data["segments"]),
        "language": transcript_data.get("language", "unknown"),
        "duration": round(transcript_data.get("duration", 0), 1),
        "quality": quality,
        "engine": actual_engine,
        "passes": passes,
        "timestamp_refined": transcript_data.get("timestamp_refined", False),
    }


def _resolve_engine(engine: str) -> str:
    """Resolve 'auto' engine to best available, or validate requested engine."""
    from ..services.tool_availability import check_tool

    if engine == "auto":
        if check_tool("whisperx"):
            return "whisperx"
        return "faster-whisper"
    elif engine == "groq":
        if not check_tool("groq"):
            return "faster-whisper"  # graceful fallback if no API key
        return "groq"
    elif engine == "whisperx":
        if not check_tool("whisperx"):
            return "faster-whisper"  # graceful fallback
        return "whisperx"
    return "faster-whisper"


@router.post("/transcribe")
async def transcribe(req: TranscriptionRequest):
    """Start transcription as a background task."""
    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    existing = tm.get_active_task(req.project_name, "transcribe")
    if existing:
        return tm.task_to_dict(existing)

    quality = req.model_size
    if quality not in ("fast", "standard", "high"):
        quality = "standard"

    task_id = tm.create_task(req.project_name, "transcribe")
    tm.run_in_background(
        task_id, _do_transcribe, project_dir,
        req.model_size, quality, req.engine, req.refine_timestamps,
    )
    return tm.task_to_dict(tm.get_task(task_id))


@router.get("/{project_name}/raw")
async def get_raw_transcript(project_name: str):
    project_dir = PROJECTS_DIR / project_name
    raw_path = project_dir / "transcripts" / "raw.json"
    if not raw_path.exists():
        raise HTTPException(404, "Raw transcript not found. Run transcription first.")
    return load_transcript(str(raw_path))
