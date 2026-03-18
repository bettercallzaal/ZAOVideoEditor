"""Silence/dead-air removal router using auto-editor."""

from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..services import task_manager as tm
from ..services.project_utils import find_video as _find_video, PROJECTS_DIR

router = APIRouter(prefix="/api/silence", tags=["silence"])


class SilenceRemovalRequest(BaseModel):
    project_name: str
    margin: float = 0.1
    threshold: float = 0.04


class SilencePreviewRequest(BaseModel):
    project_name: str
    margin: float = 0.1
    threshold: float = 0.04


@router.post("/preview")
async def preview_cuts(req: SilencePreviewRequest):
    """Preview what auto-editor would cut without applying."""
    from ..services.tool_availability import require_tool
    require_tool("auto_editor")

    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    video_path = _find_video(project_dir)

    from ..services.auto_editor_service import preview_silence_cuts
    return preview_silence_cuts(
        str(video_path), margin=req.margin, threshold=req.threshold,
    )


def _do_remove_silence(task_id: str, project_dir: Path,
                       margin: float, threshold: float):
    """Background worker for silence removal."""
    tm.update_task(task_id, progress=5, message="Starting silence removal...")

    video_path = None
    assembled = project_dir / "processing" / "assembled.mp4"
    if assembled.exists():
        video_path = assembled
    else:
        for ext in [".mp4", ".mov", ".mkv", ".webm"]:
            p = project_dir / "input" / f"main{ext}"
            if p.exists():
                video_path = p
                break

    if not video_path:
        raise RuntimeError("No video found")

    output_path = project_dir / "processing" / "trimmed.mp4"

    from ..services.auto_editor_service import remove_silence
    result = remove_silence(
        str(video_path), str(output_path),
        margin=margin, threshold=threshold,
        on_progress=lambda p, m: tm.update_task(task_id, progress=p, message=m),
    )

    return result


@router.post("/remove")
async def remove_silence_endpoint(req: SilenceRemovalRequest):
    """Remove silence from video as a background task."""
    from ..services.tool_availability import require_tool
    require_tool("auto_editor")

    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    existing = tm.get_active_task(req.project_name, "silence")
    if existing:
        return tm.task_to_dict(existing)

    task_id = tm.create_task(req.project_name, "silence")
    tm.run_in_background(
        task_id, _do_remove_silence, project_dir,
        req.margin, req.threshold,
    )
    return tm.task_to_dict(tm.get_task(task_id))
