"""Studio: the one-command local app.

A dead-simple drag-and-drop surface over the recordings pipeline. No Supabase,
no Vercel, no flags - drop a recording, get the transcripts, trim it, download.
Everything is served from this same FastAPI process, so the page and the API are
same-origin and there is nothing else to run.
"""

import json
import re
import shutil
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse

from ..services import recordings_pipeline as rp
from ..services import task_manager as tm

router = APIRouter(prefix="/api/studio", tags=["studio"])

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"
STATIC_DIR = Path(__file__).parent.parent / "static"
SUBDIRS = ["input", "processing", "transcripts", "captions", "metadata", "exports", "clips"]
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "recording"


def _project_dir(name: str) -> Path:
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(422, "Invalid project")
    d = (PROJECTS_DIR / name).resolve()
    if not d.is_relative_to(PROJECTS_DIR.resolve()):
        raise HTTPException(403, "Access denied")
    return d


def _find_input(project_dir: Path) -> Path:
    for ext in list(VIDEO_EXTS) + list(AUDIO_EXTS):
        p = project_dir / "input" / f"main{ext}"
        if p.exists():
            return p
    raise HTTPException(404, "No input media")


def _do_process(task_id: str, project_dir: Path, media: str, title: str):
    result = rp.process_recording(
        media, title=title, quality="standard", out_dir=str(project_dir / "transcripts"),
        readable_llm=True,
        on_progress=lambda pct, msg: tm.update_task(task_id, progress=pct, message=msg),
    )
    return {
        "title": result["title"],
        "duration": result["duration"],
        "segment_count": result["segment_count"],
        "review_flags": result["review_flags"],
        "edit_sheet": result["edit_sheet"],
        "readable_backend": result["readable_backend"],
    }


@router.post("/process")
async def process(file: UploadFile = File(...), title: str = Form("")):
    """Create a project from an uploaded recording and run the pipeline."""
    orig = file.filename or "recording"
    ext = Path(orig).suffix.lower()
    if ext not in VIDEO_EXTS and ext not in AUDIO_EXTS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    name = _slug(title or Path(orig).stem)
    project_dir = _project_dir(name)
    for sub in SUBDIRS:
        (project_dir / sub).mkdir(parents=True, exist_ok=True)
    (project_dir / "project.json").write_text(json.dumps({
        "name": name, "title": title or Path(orig).stem,
        "created_at": datetime.now().isoformat(), "source": "studio",
    }, indent=2), encoding="utf-8")

    dest = project_dir / "input" / f"main{ext}"
    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    task_id = tm.create_task(name, "studio_process")
    tm.run_in_background(task_id, _do_process, project_dir, str(dest), title or Path(orig).stem)
    return {"project": name, "task_id": task_id}


@router.get("/{project}/result")
async def result(project: str):
    """Read the written pipeline outputs for a project."""
    project_dir = _project_dir(project)
    tdir = project_dir / "transcripts"
    if not tdir.exists():
        raise HTTPException(404, "Not processed yet")
    slug = project
    out = {"project": project}
    readable = next(tdir.glob("*.readable.md"), None)
    sheet = next(tdir.glob("*.edit-sheet.json"), None)
    flags = next(tdir.glob("*.review-flags.json"), None)
    out["readable"] = readable.read_text(encoding="utf-8") if readable else ""
    out["edit_sheet"] = json.loads(sheet.read_text()) if sheet else {"cuts": []}
    out["review_flags"] = json.loads(flags.read_text()) if flags else []
    out["has_trimmed"] = (project_dir / "processing" / "trimmed.mp4").exists()
    return out


def _do_render(task_id: str, project_dir: Path, media: str, sheet: dict):
    from ..services.render_service import render_cuts
    out = project_dir / "processing" / "trimmed.mp4"
    tm.update_task(task_id, progress=15, message="Rendering trimmed video...")
    stats = render_cuts(media, sheet, str(out))
    tm.update_task(task_id, progress=95, message="Trimmed video ready")
    return stats


@router.post("/{project}/render")
async def render(project: str):
    """Render a trimmed video from the saved edit sheet (non-destructive)."""
    project_dir = _project_dir(project)
    sheet_file = next((project_dir / "transcripts").glob("*.edit-sheet.json"), None)
    if not sheet_file:
        raise HTTPException(404, "No edit sheet - process first")
    sheet = json.loads(sheet_file.read_text())
    media = _find_input(project_dir)
    existing = tm.get_active_task(project, "studio_render")
    if existing:
        return tm.task_to_dict(existing)
    task_id = tm.create_task(project, "studio_render")
    tm.run_in_background(task_id, _do_render, project_dir, str(media), sheet)
    return {"task_id": task_id}


@router.get("/{project}/download/{kind}")
async def download(project: str, kind: str):
    """Download an output: readable | cut | trimmed | editsheet."""
    project_dir = _project_dir(project)
    tdir = project_dir / "transcripts"
    mapping = {
        "readable": (next(tdir.glob("*.readable.md"), None), "text/markdown"),
        "cut": (next(tdir.glob("*.cut.md"), None), "text/markdown"),
        "editsheet": (next(tdir.glob("*.edit-sheet.json"), None), "application/json"),
        "trimmed": (project_dir / "processing" / "trimmed.mp4", "video/mp4"),
    }
    entry = mapping.get(kind)
    if not entry or not entry[0] or not Path(entry[0]).exists():
        raise HTTPException(404, "File not available")
    path = Path(entry[0])
    return FileResponse(str(path), media_type=entry[1], filename=path.name)


@router.get("/page", response_class=HTMLResponse)
async def page():
    html = STATIC_DIR / "studio.html"
    if not html.exists():
        raise HTTPException(404, "Studio page missing")
    return HTMLResponse(html.read_text(encoding="utf-8"))
