"""Audiogram endpoints - give an audio-only project a video stream.

An audio space has no picture, so every visual stage (captions, clips,
reframe, thumbnails) fails on it. Rendering an audiogram turns the project
into an ordinary video project and the rest of the pipeline runs unchanged.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import audiogram_service as ag
from ..services import task_manager as tm
from ..services.project_utils import get_project_dir, is_within

router = APIRouter(prefix="/api/audiogram", tags=["audiogram"])

INPUT_EXTS = [".mp4", ".mov", ".mkv", ".webm", ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"]


class AudiogramRequest(BaseModel):
    title: str = ""
    subtitle: str = ""
    footer: str = ""
    fps: int = 30
    hwaccel: bool = False


def _find_input(project_dir: Path) -> Path:
    for ext in INPUT_EXTS:
        p = (project_dir / "input" / f"main{ext}").resolve()
        if p.exists():
            if not is_within(p, project_dir.resolve()):
                raise HTTPException(403, "Access denied")
            return p
    raise HTTPException(404, "No input media in project")


def _do_render(task_id: str, project_dir: Path, media: Path, req: AudiogramRequest):
    out = ag.ensure_video_track(
        project_dir, str(media),
        title=req.title, subtitle=req.subtitle, footer=req.footer,
        fps=req.fps, hwaccel=req.hwaccel,
        on_progress=lambda pct, msg: tm.update_task(task_id, progress=pct, message=msg),
    )
    return {"video": str(out), "cached": out.name == "audiogram.mp4"}


@router.get("/{project_name}/status")
async def status(project_name: str):
    """Whether this project is audio-only, and whether its audiogram exists yet."""
    project_dir = get_project_dir(project_name)

    media = _find_input(project_dir)
    # exact_duration decodes the file (O(length)); this endpoint exists to report it.
    info = ag.probe_streams(str(media))
    audiogram = project_dir / "processing" / "audiogram.mp4"

    return {
        "input": media.name,
        "audio_only": info["has_audio"] and not info["has_video"],
        "duration": info["duration"],
        "audiogram_exists": audiogram.exists(),
        "can_burn_captions": ag._has_ass_filter(),
    }


@router.post("/{project_name}")
async def render(project_name: str, req: AudiogramRequest):
    """Render the audiogram for an audio-only project. Returns a task id."""
    project_dir = get_project_dir(project_name)

    media = _find_input(project_dir)
    if not ag.is_audio_only(str(media)):
        raise HTTPException(400, f"{media.name} already has a video stream")

    task_id = tm.create_task(project_name, "audiogram")
    tm.run_in_background(task_id, _do_render, project_dir, media, req)
    return {"project": project_name, "task_id": task_id}
