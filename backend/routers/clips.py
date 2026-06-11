"""Highlight detection and clip extraction endpoints."""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from ..models.schemas import ProjectName
from ..services.highlights import detect_highlights
from ..services.project_utils import find_video, find_best_transcript, PROJECTS_DIR, validate_project_name, is_within
from ..services import clip_service
from ..services.reframe_service import SUPPORTED_ASPECTS
from ..services.content_gen import generate_clip_copy
from ..services import task_manager as tm

router = APIRouter(prefix="/api/clips", tags=["clips"])


class HighlightRequest(BaseModel):
    project_name: ProjectName
    count: int = 5
    min_duration: float = 30.0
    max_duration: float = 90.0


class ClipExportRequest(BaseModel):
    project_name: ProjectName
    start: float
    end: float
    title: Optional[str] = ""
    aspects: list[str] = ["9:16"]   # 9:16, 1:1, 16:9 - one render per aspect
    vertical: Optional[bool] = None  # deprecated: True -> aspects ["9:16"]
    burn_captions: bool = True
    style: str = "bold_pop"
    speaker_aware: bool = False
    generate_copy: bool = True


class BatchClipRequest(BaseModel):
    project_name: ProjectName
    count: int = 5
    min_duration: float = 30.0
    max_duration: float = 90.0
    aspects: list[str] = ["9:16"]
    burn_captions: bool = True
    style: str = "bold_pop"
    speaker_aware: bool = False
    generate_copy: bool = True
    highlights: Optional[list] = None  # if given, skip detection


def _get_best_transcript(project_dir: Path):
    return find_best_transcript(project_dir)


def _validate_aspects(aspects: list[str]) -> list[str]:
    bad = [a for a in aspects if a not in SUPPORTED_ASPECTS]
    if bad:
        raise HTTPException(422, f"Unsupported aspect(s): {bad}. Allowed: {SUPPORTED_ASPECTS}")
    return aspects


def _safe_title(title: str, idx: int) -> str:
    safe = "".join(c for c in (title or f"clip_{idx}") if c.isalnum() or c in " _-").strip()
    return safe[:50] or f"clip_{idx}"


@router.post("/detect")
async def detect(req: HighlightRequest):
    """Detect highlight moments in the transcript."""
    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    transcript = _get_best_transcript(project_dir)
    highlights = detect_highlights(
        transcript["segments"],
        min_duration=req.min_duration,
        max_duration=req.max_duration,
        count=req.count,
    )

    return {
        "highlights": highlights,
        "count": len(highlights),
    }


def _export_one(project_dir: Path, video_path: Path, segments: list,
                start: float, end: float, title: str, idx: int,
                aspects: list[str], burn_captions: bool, style: str,
                speaker_aware: bool, want_copy: bool,
                progress_cb=None) -> dict:
    """Render one highlight into every requested aspect, plus optional copy."""
    clips_dir = project_dir / "clips"
    clips_dir.mkdir(exist_ok=True)
    base = _safe_title(title, idx)

    renders = []
    for aspect in aspects:
        suffix = aspect.replace(":", "x")
        out_path = clips_dir / f"{base}_{suffix}.mp4"
        if progress_cb:
            progress_cb(f"Rendering {base} ({aspect})...")
        info = clip_service.export_clip(
            str(video_path), start, end, out_path,
            aspect=aspect, segments=segments, style=style,
            burn_captions=burn_captions, speaker_aware=speaker_aware,
        )
        renders.append(info)

    copy = None
    if want_copy:
        if progress_cb:
            progress_cb(f"Writing copy for {base}...")
        window = clip_service.segments_in_window(segments, start, end)
        copy = generate_clip_copy(window, project_name=project_dir.name, fallback_title=title)
        (clips_dir / f"{base}.copy.json").write_text(json.dumps(copy, indent=2), encoding="utf-8")

    return {
        "title": title,
        "base": base,
        "start": round(start, 2),
        "end": round(end, 2),
        "renders": renders,
        "copy": copy,
    }


def _do_export_clip(task_id: str, project_dir: Path, req_data: dict):
    """Background worker: single clip, one render per aspect."""
    tm.update_task(task_id, progress=10, message="Finding source video...")
    video_path = find_video(project_dir, include_captioned=False)
    transcript = _get_best_transcript(project_dir) if req_data["burn_captions"] or req_data["generate_copy"] else {"segments": []}
    segments = transcript.get("segments", [])

    tm.update_task(task_id, progress=30, message="Rendering clip...")
    result = _export_one(
        project_dir, video_path, segments,
        req_data["start"], req_data["end"], req_data["title"], 0,
        req_data["aspects"], req_data["burn_captions"], req_data["style"],
        req_data["speaker_aware"], req_data["generate_copy"],
        progress_cb=lambda m: tm.update_task(task_id, message=m),
    )
    tm.update_task(task_id, progress=95, message="Clip ready")
    return result


def _do_batch_clips(task_id: str, project_dir: Path, req_data: dict):
    """Background worker: detect (or accept) highlights, render each clip."""
    tm.update_task(task_id, progress=5, message="Finding source video...")
    video_path = find_video(project_dir, include_captioned=False)
    transcript = _get_best_transcript(project_dir)
    segments = transcript.get("segments", [])

    highlights = req_data.get("highlights")
    if not highlights:
        tm.update_task(task_id, progress=10, message="Detecting highlights...")
        highlights = detect_highlights(
            segments, min_duration=req_data["min_duration"],
            max_duration=req_data["max_duration"], count=req_data["count"],
        )
    if not highlights:
        return {"clips": [], "count": 0, "message": "No highlights detected"}

    total = len(highlights)
    out_clips = []
    for i, h in enumerate(highlights):
        pct = 15 + int((i / total) * 80)
        tm.update_task(task_id, progress=pct, message=f"Clip {i + 1}/{total}...")
        try:
            res = _export_one(
                project_dir, video_path, segments,
                h["start"], h["end"], h.get("title", f"clip_{i + 1}"), i + 1,
                req_data["aspects"], req_data["burn_captions"], req_data["style"],
                req_data["speaker_aware"], req_data["generate_copy"],
                progress_cb=lambda m, p=pct: tm.update_task(task_id, message=m),
            )
            out_clips.append(res)
        except Exception as e:
            print(f"Batch clip {i + 1} failed: {e}")
            out_clips.append({"title": h.get("title", ""), "error": str(e)})

    return {"clips": out_clips, "count": len(out_clips)}


@router.post("/export")
async def export_clip(req: ClipExportRequest):
    """Export one clip, rendered into each requested aspect ratio."""
    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    aspects = ["9:16"] if req.vertical else req.aspects
    _validate_aspects(aspects)

    existing = tm.get_active_task(req.project_name, "clip_export")
    if existing:
        return tm.task_to_dict(existing)

    task_id = tm.create_task(req.project_name, "clip_export")
    tm.run_in_background(task_id, _do_export_clip, project_dir, {
        "start": req.start, "end": req.end, "title": req.title or "",
        "aspects": aspects, "burn_captions": req.burn_captions,
        "style": req.style, "speaker_aware": req.speaker_aware,
        "generate_copy": req.generate_copy,
    })
    return tm.task_to_dict(tm.get_task(task_id))


@router.post("/batch-export")
async def batch_export(req: BatchClipRequest):
    """Detect highlights (or use the ones provided) and render every clip.

    The one-click "stream -> clips" step: each highlight becomes a captioned,
    reframed clip in every requested aspect, with per-clip post copy.
    """
    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    _validate_aspects(req.aspects)

    existing = tm.get_active_task(req.project_name, "clip_batch")
    if existing:
        return tm.task_to_dict(existing)

    task_id = tm.create_task(req.project_name, "clip_batch")
    tm.run_in_background(task_id, _do_batch_clips, project_dir, {
        "count": req.count, "min_duration": req.min_duration,
        "max_duration": req.max_duration, "aspects": req.aspects,
        "burn_captions": req.burn_captions, "style": req.style,
        "speaker_aware": req.speaker_aware, "generate_copy": req.generate_copy,
        "highlights": req.highlights,
    })
    return tm.task_to_dict(tm.get_task(task_id))


@router.get("/{project_name}/list")
async def list_clips(project_name: str):
    """List exported clips with their post copy (if generated)."""
    validate_project_name(project_name)
    clips_dir = PROJECTS_DIR / project_name / "clips"
    if not clips_dir.exists():
        return []
    out = []
    for f in sorted(clips_dir.iterdir()):
        if f.suffix != ".mp4":
            continue
        # base name is the filename minus the _<aspect> suffix
        stem = f.stem
        base = stem.rsplit("_", 1)[0] if stem.rsplit("_", 1)[-1] in {"9x16", "1x1", "16x9"} else stem
        copy_path = clips_dir / f"{base}.copy.json"
        copy = None
        if copy_path.exists():
            try:
                copy = json.loads(copy_path.read_text())
            except (ValueError, OSError):
                copy = None
        out.append({"filename": f.name, "base": base, "copy": copy})
    return out


@router.get("/{project_name}/download/{filename}")
async def download_clip(project_name: str, filename: str):
    """Download an exported clip."""
    validate_project_name(project_name)
    clips_dir = PROJECTS_DIR / project_name / "clips"
    file_path = (clips_dir / filename).resolve()
    if not is_within(file_path, clips_dir):
        raise HTTPException(403, "Access denied")
    if not file_path.exists():
        raise HTTPException(404, "Clip not found")
    return FileResponse(str(file_path), filename=file_path.name)
