"""YouTube transcript extraction endpoints."""

from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..services import task_manager as tm
from ..services.youtube_service import extract_video_id, get_video_info
from ..services.project_utils import PROJECTS_DIR

router = APIRouter(prefix="/api/youtube", tags=["youtube"])


class YouTubeTranscriptRequest(BaseModel):
    url: str
    project_name: str
    quality: str = 'standard'


class YouTubeInfoRequest(BaseModel):
    url: str


@router.post("/info")
async def video_info(req: YouTubeInfoRequest):
    """Get YouTube video metadata without downloading."""
    try:
        video_id = extract_video_id(req.url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    try:
        info = get_video_info(video_id)
        info['video_id'] = video_id
        return info
    except Exception as e:
        raise HTTPException(400, f"Could not fetch video info: {e}")


def _do_youtube_transcribe(task_id: str, video_id: str, project_dir: str, quality: str):
    """Background worker for YouTube transcription."""
    from ..services.youtube_service import transcribe_youtube

    result = transcribe_youtube(
        video_id=video_id,
        project_dir=project_dir,
        quality=quality,
        on_progress=lambda p, m: tm.update_task(task_id, progress=p, message=m),
    )
    return result


@router.post("/transcribe")
async def youtube_transcribe(req: YouTubeTranscriptRequest):
    """Download and transcribe a YouTube video."""
    try:
        video_id = extract_video_id(req.url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    # Check for existing active task
    existing = tm.get_active_task(req.project_name, "youtube_transcribe")
    if existing:
        return tm.task_to_dict(existing)

    task_id = tm.create_task(req.project_name, "youtube_transcribe")
    tm.run_in_background(
        task_id, _do_youtube_transcribe,
        video_id, str(project_dir), req.quality,
    )
    return tm.task_to_dict(tm.get_task(task_id))
