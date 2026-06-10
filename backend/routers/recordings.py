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
    suggest_falsestarts: bool = False

    @field_validator("project_name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not v or ".." in v or "/" in v or "\\" in v or not _NAME_RE.match(v):
            raise ValueError("Invalid project name")
        return v


class RenderRequest(BaseModel):
    project_name: str
    edit_sheet: dict  # {"duration": float, "cuts": [...]}

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
                quality: str, readable_llm: bool, suggest_falsestarts: bool) -> dict:
    out_dir = project_dir / "transcripts"
    result = rp.process_recording(
        media, title=title, quality=quality, out_dir=str(out_dir),
        readable_llm=readable_llm, suggest_falsestarts=suggest_falsestarts,
        on_progress=lambda pct, msg: tm.update_task(task_id, progress=pct, message=msg),
    )
    # keep only lightweight fields in the task result
    return {
        "title": result["title"],
        "segment_count": result["segment_count"],
        "duration": result["duration"],
        "readable_backend": result["readable_backend"],
        "review_flags": result["review_flags"],
        "edit_sheet": result["edit_sheet"],
        "files": result.get("files", {}),
    }


def _do_render(task_id: str, project_dir: Path, media: str, edit_sheet: dict) -> dict:
    from ..services.render_service import render_cuts
    out_path = project_dir / "processing" / "trimmed.mp4"
    tm.update_task(task_id, progress=20, message="Rendering trimmed master...")
    stats = render_cuts(media, edit_sheet, str(out_path))
    tm.update_task(task_id, progress=95, message="Render complete")
    return {"output": "processing/trimmed.mp4", **stats}


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
        req.title, req.quality, req.readable_llm, req.suggest_falsestarts,
    )
    return tm.task_to_dict(tm.get_task(task_id))


class ExportRequest(BaseModel):
    project_name: str
    style: str = "bold_pop"
    aspects: list[str] = ["9:16"]
    make_clips: bool = True

    @field_validator("project_name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not v or ".." in v or "/" in v or "\\" in v or not _NAME_RE.match(v):
            raise ValueError("Invalid project name")
        return v


class PublishRequest(BaseModel):
    project_name: str
    number: int
    date: str = ""
    presenter: str = ""
    title: str = ""
    youtube_id: str = ""

    @field_validator("project_name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not v or ".." in v or "/" in v or "\\" in v or not _NAME_RE.match(v):
            raise ValueError("Invalid project name")
        return v


def _load_segments(project_dir: Path) -> list:
    import json as _json
    tdir = project_dir / "transcripts"
    for name in ("edited.json", "cleaned.json", "corrected.json", "raw.json"):
        p = tdir / name
        if p.exists():
            data = _json.loads(p.read_text())
            return data.get("segments", data) if isinstance(data, dict) else data
    # fall back to the recordings pipeline's <slug>.cut.json
    for p in tdir.glob("*.cut.json"):
        return _json.loads(p.read_text())
    raise HTTPException(404, "No transcript found - run /process first")


def _do_export(task_id: str, project_dir: Path, style: str, aspects: list, make_clips: bool) -> dict:
    from ..services import recordings_export as rx
    segments = _load_segments(project_dir)
    master = project_dir / "processing" / "trimmed.mp4"
    if not master.exists():
        master = Path(_find_input(project_dir))

    tm.update_task(task_id, progress=20, message="Generating + burning captions...")
    captions = rx.build_caption_data(segments, style=style)
    captioned = project_dir / "processing" / "captioned.mp4"
    burn = rx.burn_master_captions(str(master), captions, str(captioned), style=style)

    clips_res = {"rendered": False}
    if make_clips:
        tm.update_task(task_id, progress=60, message="Rendering clips...")
        clips_res = rx.render_clips(
            str(master), segments, project_dir / "clips",
            aspects=aspects, project_name=project_dir.name,
        )
    tm.update_task(task_id, progress=95, message="Export complete")
    return {"captions": burn, "clips": clips_res}


@router.post("/export")
async def export(req: ExportRequest):
    """Burn captions onto the master (non-destructive) and render highlight clips."""
    _safe_name(req.project_name)
    project_dir = (PROJECTS_DIR / req.project_name).resolve()
    if not project_dir.is_relative_to(PROJECTS_DIR.resolve()) or not project_dir.exists():
        raise HTTPException(404, "Project not found")
    existing = tm.get_active_task(req.project_name, "recordings_export")
    if existing:
        return tm.task_to_dict(existing)
    task_id = tm.create_task(req.project_name, "recordings_export")
    tm.run_in_background(task_id, _do_export, project_dir, req.style, req.aspects, req.make_clips)
    return tm.task_to_dict(tm.get_task(task_id))


@router.post("/publish")
async def publish(req: PublishRequest):
    """Build the /recordings/N publish bundle from the project's readable transcript."""
    _safe_name(req.project_name)
    project_dir = (PROJECTS_DIR / req.project_name).resolve()
    if not project_dir.is_relative_to(PROJECTS_DIR.resolve()) or not project_dir.exists():
        raise HTTPException(404, "Project not found")

    from ..services.publish_service import build_bundle
    tdir = project_dir / "transcripts"
    readable = ""
    for p in tdir.glob("*.readable.md"):
        readable = p.read_text()
        break
    if not readable:
        raise HTTPException(404, "No readable transcript - run /process first")

    result = {"title": req.title or req.project_name, "readable_markdown": readable}
    out_dir = project_dir / "publish"
    bundle = build_bundle(
        result, req.number, req.date or "0000-00-00",
        presenter=req.presenter, topic=req.title or req.project_name,
        youtube_id=req.youtube_id or None, out_dir=str(out_dir),
    )
    return {
        "number": bundle["number"],
        "transcript_filename": bundle["transcript_filename"],
        "output_dir": bundle["output_dir"],
    }


@router.post("/render")
async def render(req: RenderRequest):
    """Render a trimmed master from the edit sheet (non-destructive)."""
    _safe_name(req.project_name)
    project_dir = (PROJECTS_DIR / req.project_name).resolve()
    if not project_dir.is_relative_to(PROJECTS_DIR.resolve()) or not project_dir.exists():
        raise HTTPException(404, "Project not found")

    media = _find_input(project_dir)

    existing = tm.get_active_task(req.project_name, "recordings_render")
    if existing:
        return tm.task_to_dict(existing)

    task_id = tm.create_task(req.project_name, "recordings_render")
    tm.run_in_background(task_id, _do_render, project_dir, str(media), req.edit_sheet)
    return tm.task_to_dict(tm.get_task(task_id))
