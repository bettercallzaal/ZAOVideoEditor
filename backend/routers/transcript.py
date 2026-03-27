import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from ..models.schemas import TranscriptEditRequest, CleanupRequest, DictionaryEntry
from ..services.dictionary import (
    load_dictionary, add_correction, remove_correction,
    apply_corrections_to_segments, learn_from_edits,
)
from ..services.cleanup import cleanup_transcript
from ..services.whisper_service import load_transcript, save_transcript

router = APIRouter(prefix="/api/transcript", tags=["transcript"])

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"


@router.post("/correct")
async def apply_corrections(req: CleanupRequest):
    """Apply dictionary corrections to raw transcript."""
    project_dir = PROJECTS_DIR / req.project_name
    raw_path = project_dir / "transcripts" / "raw.json"
    if not raw_path.exists():
        raise HTTPException(404, "Raw transcript not found")

    transcript = load_transcript(str(raw_path))
    corrected_segments = apply_corrections_to_segments(transcript["segments"])

    corrected_data = {
        "segments": corrected_segments,
        "raw_text": " ".join(seg["text"] for seg in corrected_segments),
    }
    save_transcript(corrected_data, str(project_dir / "transcripts" / "corrected.json"))

    return {"status": "complete", "segments": len(corrected_segments)}


@router.post("/cleanup")
async def cleanup(req: CleanupRequest):
    """Clean and polish the transcript."""
    project_dir = PROJECTS_DIR / req.project_name

    # Use corrected if available, otherwise raw
    corrected_path = project_dir / "transcripts" / "corrected.json"
    raw_path = project_dir / "transcripts" / "raw.json"

    if corrected_path.exists():
        source_path = corrected_path
    elif raw_path.exists():
        source_path = raw_path
    else:
        raise HTTPException(404, "No transcript found")

    transcript = load_transcript(str(source_path))
    cleaned_segments = cleanup_transcript(transcript["segments"])

    cleaned_data = {
        "segments": cleaned_segments,
        "raw_text": " ".join(seg["text"] for seg in cleaned_segments),
    }
    save_transcript(cleaned_data, str(project_dir / "transcripts" / "cleaned.json"))

    # Also save cleaned text
    with open(project_dir / "transcripts" / "cleaned.txt", "w") as f:
        f.write(cleaned_data["raw_text"])

    return {"status": "complete", "segments": len(cleaned_segments)}


@router.get("/{project_name}/current")
async def get_current_transcript(project_name: str):
    """Get the best available transcript (edited > cleaned > corrected > raw)."""
    project_dir = PROJECTS_DIR / project_name

    for name in ["edited.json", "cleaned.json", "corrected.json", "raw.json"]:
        path = project_dir / "transcripts" / name
        if path.exists():
            data = load_transcript(str(path))
            return {"source": name, **data}

    raise HTTPException(404, "No transcript found")


@router.post("/save-edit")
async def save_edit(req: TranscriptEditRequest):
    """Save user edits to transcript and auto-learn corrections."""
    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    segments = [seg.model_dump() for seg in req.segments]

    # Auto-learn: diff against the previous best transcript to find corrections
    before_segments = None
    for name in ["edited.json", "cleaned.json", "corrected.json", "raw.json"]:
        path = project_dir / "transcripts" / name
        if path.exists():
            before_data = load_transcript(str(path))
            before_segments = before_data.get("segments", [])
            break

    edited_data = {
        "segments": segments,
        "raw_text": " ".join(seg["text"] for seg in segments),
    }
    save_transcript(edited_data, str(project_dir / "transcripts" / "edited.json"))

    # Learn from the diff (runs after save so it doesn't block)
    if before_segments:
        try:
            learn_from_edits(before_segments, segments)
        except Exception:
            pass  # Don't fail the save if learning fails

    return {"status": "saved", "segments": len(segments)}


# Dictionary management endpoints
@router.get("/dictionary")
async def get_dictionary():
    """Get the correction dictionary."""
    return load_dictionary()


@router.post("/dictionary/add")
async def add_dict_entry(entry: DictionaryEntry):
    """Add a correction to the dictionary."""
    add_correction(entry.wrong, entry.correct)
    return {"status": "added", "wrong": entry.wrong, "correct": entry.correct}


@router.delete("/dictionary/{wrong}")
async def remove_dict_entry(wrong: str):
    """Remove a correction from the dictionary."""
    remove_correction(wrong)
    return {"status": "removed"}
