"""Filler word detection and removal endpoints."""

from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..services.filler_detection import detect_fillers, remove_fillers_from_transcript
from ..services.whisper_service import load_transcript, save_transcript

router = APIRouter(prefix="/api/fillers", tags=["fillers"])

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"


class FillerRequest(BaseModel):
    project_name: str


class FillerRemoveRequest(BaseModel):
    project_name: str
    types: Optional[list] = None  # ["filler_word", "filler_phrase", "contextual_filler"]


def _get_best_transcript(project_dir: Path) -> tuple:
    """Get the best available transcript. Returns (data, filename)."""
    for name in ["edited.json", "cleaned.json", "corrected.json", "raw.json"]:
        path = project_dir / "transcripts" / name
        if path.exists():
            return load_transcript(str(path)), name
    raise HTTPException(404, "No transcript found. Run transcription first.")


@router.post("/detect")
async def detect(req: FillerRequest):
    """Detect filler words in the transcript."""
    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    transcript, source = _get_best_transcript(project_dir)
    result = detect_fillers(transcript["segments"])

    return {
        "total_fillers": result["total_fillers"],
        "total_duration": round(result["total_duration"], 2),
        "stats": result["stats"],
        "fillers": result["fillers"],
        "source": source,
    }


@router.post("/remove")
async def remove(req: FillerRemoveRequest):
    """Remove detected fillers from the transcript and save."""
    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    transcript, source = _get_best_transcript(project_dir)

    # First detect fillers
    detected = detect_fillers(transcript["segments"])

    # Remove them
    types = req.types or ["filler_word", "filler_phrase", "contextual_filler"]
    cleaned = remove_fillers_from_transcript(detected["segments"], types)

    # Save as cleaned transcript
    transcript["segments"] = cleaned
    transcript["fillers_removed"] = detected["total_fillers"]

    save_path = project_dir / "transcripts" / "cleaned.json"
    save_transcript(transcript, str(save_path))

    return {
        "removed": detected["total_fillers"],
        "duration_saved": round(detected["total_duration"], 2),
        "stats": detected["stats"],
        "segments_remaining": len(cleaned),
    }
