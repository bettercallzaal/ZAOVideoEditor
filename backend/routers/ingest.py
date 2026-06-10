"""Ingest endpoints — pull a livestream recording / VOD by URL into a project.

Turns "here is the stream URL" into a ready-to-edit project, so the existing
transcribe -> caption -> clip pipeline runs unchanged.
"""

import json
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from ..models.schemas import ProjectName
from ..services.project_utils import validate_project_name, is_within
from ..services import ingest_service
from ..services import task_manager as tm

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"

PROJECT_SUBDIRS = ["input", "processing", "transcripts", "captions", "metadata", "exports"]


class IngestRequest(BaseModel):
    url: HttpUrl
    project_name: ProjectName
    description: str = ""


class ProbeRequest(BaseModel):
    url: HttpUrl


@router.get("/sources")
async def list_sources():
    """List advertised ingest sources and whether yt-dlp is installed."""
    return {
        "available": ingest_service.yt_dlp_available(),
        "sources": ingest_service.SUPPORTED_SOURCES,
    }


@router.post("/probe")
async def probe(req: ProbeRequest):
    """Resolve a URL's metadata (title, duration, live status) without downloading."""
    if not ingest_service.yt_dlp_available():
        raise HTTPException(400, "yt-dlp is not installed. Install it to ingest from URLs.")
    try:
        return ingest_service.probe_url(str(req.url))
    except RuntimeError as e:
        raise HTTPException(400, str(e))


def _ensure_project(name: str, description: str) -> Path:
    """Create the project skeleton if it does not exist; return its directory."""
    project_dir = (PROJECTS_DIR / name).resolve()
    if not is_within(project_dir, PROJECTS_DIR):
        raise HTTPException(403, "Access denied")
    if not project_dir.exists():
        for subdir in PROJECT_SUBDIRS:
            (project_dir / subdir).mkdir(parents=True, exist_ok=True)
        info = {
            "name": name,
            "description": description or "",
            "created_at": datetime.now().isoformat(),
            "source": "ingest",
        }
        with open(project_dir / "project.json", "w") as f:
            json.dump(info, f, indent=2)
    return project_dir


def _do_ingest(task_id: str, url: str, project_dir: Path) -> dict:
    """Background ingest worker."""
    def progress(pct: int, message: str):
        tm.update_task(task_id, progress=pct, message=message)

    result = ingest_service.download_to_project(url, project_dir, on_progress=progress)
    return result


@router.post("")
async def ingest(req: IngestRequest):
    """Create (or reuse) a project and download the URL into it in the background."""
    validate_project_name(req.project_name)
    if not ingest_service.yt_dlp_available():
        raise HTTPException(400, "yt-dlp is not installed. Install it to ingest from URLs.")

    project_dir = _ensure_project(req.project_name, req.description)

    existing = tm.get_active_task(req.project_name, "ingest")
    if existing:
        return tm.task_to_dict(existing)

    task_id = tm.create_task(req.project_name, "ingest")
    tm.run_in_background(task_id, _do_ingest, str(req.url), project_dir)
    return tm.task_to_dict(tm.get_task(task_id))
