"""Speaker diarization and management endpoints."""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..services.diarization import diarize_audio, assign_speakers_to_segments, rename_speakers
from ..services.whisper_service import load_transcript, save_transcript
from ..services import task_manager as tm

router = APIRouter(prefix="/api/speakers", tags=["speakers"])

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"


class DiarizeRequest(BaseModel):
    project_name: str
    num_speakers: Optional[int] = None


class RenameSpeakerRequest(BaseModel):
    project_name: str
    speaker_map: dict  # e.g. {"SPEAKER_0": "Host", "SPEAKER_1": "Guest"}


def _do_diarize(task_id: str, project_dir: Path, num_speakers: int = None):
    """Background diarization worker."""
    audio_path = project_dir / "processing" / "audio.wav"
    if not audio_path.exists():
        raise FileNotFoundError("Audio not found. Run transcription first.")

    def on_progress(step, pct, message):
        tm.update_task(task_id, progress=int(pct), message=message)

    # Run diarization
    speaker_turns = diarize_audio(str(audio_path), num_speakers, on_progress)

    # Save raw diarization result
    diar_dir = project_dir / "transcripts"
    diar_dir.mkdir(exist_ok=True)
    with open(diar_dir / "speakers.json", "w") as f:
        json.dump({"turns": speaker_turns}, f, indent=2)

    # Apply speaker labels to best available transcript
    for name in ["edited.json", "cleaned.json", "corrected.json", "raw.json"]:
        transcript_path = diar_dir / name
        if transcript_path.exists():
            transcript = load_transcript(str(transcript_path))
            labeled = assign_speakers_to_segments(transcript["segments"], speaker_turns)
            transcript["segments"] = labeled
            save_transcript(transcript, str(transcript_path))

    speakers = list(set(t["speaker"] for t in speaker_turns))
    return {
        "speakers": speakers,
        "turns": len(speaker_turns),
    }


@router.post("/diarize")
async def diarize(req: DiarizeRequest):
    """Run speaker diarization as a background task."""
    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    existing = tm.get_active_task(req.project_name, "diarize")
    if existing:
        return tm.task_to_dict(existing)

    task_id = tm.create_task(req.project_name, "diarize")
    tm.run_in_background(task_id, _do_diarize, project_dir, req.num_speakers)
    return tm.task_to_dict(tm.get_task(task_id))


@router.post("/rename")
async def rename(req: RenameSpeakerRequest):
    """Rename speaker labels (e.g., SPEAKER_0 -> 'Host')."""
    project_dir = PROJECTS_DIR / req.project_name
    transcripts_dir = project_dir / "transcripts"

    for name in ["edited.json", "cleaned.json", "corrected.json", "raw.json"]:
        path = transcripts_dir / name
        if path.exists():
            transcript = load_transcript(str(path))
            transcript["segments"] = rename_speakers(
                transcript["segments"], req.speaker_map
            )
            save_transcript(transcript, str(path))

    return {"status": "renamed", "speaker_map": req.speaker_map}


@router.get("/{project_name}")
async def get_speakers(project_name: str):
    """Get speaker info for a project."""
    speakers_path = PROJECTS_DIR / project_name / "transcripts" / "speakers.json"
    if not speakers_path.exists():
        raise HTTPException(404, "No diarization data. Run speaker detection first.")

    with open(speakers_path) as f:
        data = json.load(f)

    speakers = list(set(t["speaker"] for t in data["turns"]))
    return {
        "speakers": speakers,
        "turns": len(data["turns"]),
    }
