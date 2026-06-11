"""Recordings pipeline endpoints (Phase 1: headless transcript).

Exposes the transcript pipeline as a background job so the worker can be driven
by the future Next.js review UI, not only the CLI.
"""

import re
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from ..services import recordings_pipeline as rp
from ..services import task_manager as tm

router = APIRouter(prefix="/api/recordings", tags=["recordings"])

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"

# Local project-name guard (path-traversal safe). When PR #2's shared
# validate_project_name lands on main, this can delegate to it.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]*$")


def _safe_name(name: str) -> str:
    if not name or ".." in name or "/" in name or "\\" in name or not _NAME_RE.match(name):
        raise HTTPException(422, "Invalid project name")
    return name


class ProcessRequest(BaseModel):
    project_name: str
    title: str = ""
    quality: str = "standard"   # fast | standard | high
    readable_llm: bool = True

    @field_validator("project_name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not v or ".." in v or "/" in v or "\\" in v or not _NAME_RE.match(v):
            raise ValueError("Invalid project name")
        return v


def _find_input(project_dir: Path) -> Path:
    for ext in (".mp4", ".mov", ".mkv", ".webm", ".wav", ".mp3", ".m4a"):
        p = project_dir / "input" / f"main{ext}"
        if p.exists():
            return p
    raise HTTPException(404, "No input media found in project")


def _do_process(task_id: str, project_dir: Path, media: str, title: str,
                quality: str, readable_llm: bool) -> dict:
    out_dir = project_dir / "transcripts"
    result = rp.process_recording(
        media, title=title, quality=quality, out_dir=str(out_dir),
        readable_llm=readable_llm,
        on_progress=lambda pct, msg: tm.update_task(task_id, progress=pct, message=msg),
    )
    # keep only lightweight fields in the task result
    return {
        "title": result["title"],
        "segment_count": result["segment_count"],
        "readable_backend": result["readable_backend"],
        "review_flags": result["review_flags"],
        "files": result.get("files", {}),
    }


@router.post("/process")
async def process(req: ProcessRequest):
    """Transcribe + brand-correct a project's input media into two transcripts."""
    _safe_name(req.project_name)
    project_dir = (PROJECTS_DIR / req.project_name).resolve()
    if not project_dir.is_relative_to(PROJECTS_DIR.resolve()) or not project_dir.exists():
        raise HTTPException(404, "Project not found")

    media = _find_input(project_dir)

    existing = tm.get_active_task(req.project_name, "recordings_process")
    if existing:
        return tm.task_to_dict(existing)

    task_id = tm.create_task(req.project_name, "recordings_process")
    tm.run_in_background(
        task_id, _do_process, project_dir, str(media),
        req.title, req.quality, req.readable_llm,
    )
    return tm.task_to_dict(tm.get_task(task_id))
