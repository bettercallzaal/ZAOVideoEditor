"""Highlight detection and clip extraction endpoints."""

import subprocess
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from ..services.highlights import detect_highlights, export_clip_timestamps
from ..services.project_utils import find_video, find_best_transcript, PROJECTS_DIR
from ..services import task_manager as tm

router = APIRouter(prefix="/api/clips", tags=["clips"])


class HighlightRequest(BaseModel):
    project_name: str
    count: int = 5
    min_duration: float = 30.0
    max_duration: float = 90.0


class ClipExportRequest(BaseModel):
    project_name: str
    start: float
    end: float
    title: Optional[str] = ""
    vertical: bool = False  # Crop to 9:16 for shorts


def _get_best_transcript(project_dir: Path):
    return find_best_transcript(project_dir)


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


def _do_export_clip(task_id: str, project_dir: Path, start: float, end: float,
                    title: str, vertical: bool, clip_idx: int):
    """Background clip extraction worker."""
    tm.update_task(task_id, progress=10, message="Finding source video...")

    video_path = find_video(project_dir, include_captioned=True)

    clips_dir = project_dir / "clips"
    clips_dir.mkdir(exist_ok=True)

    # Generate output filename
    safe_title = "".join(c for c in (title or f"clip_{clip_idx}") if c.isalnum() or c in " _-").strip()
    safe_title = safe_title[:50] or f"clip_{clip_idx}"
    output_path = clips_dir / f"{safe_title}.mp4"

    duration = end - start

    tm.update_task(task_id, progress=20, message=f"Extracting {duration:.0f}s clip...")

    # Build ffmpeg command
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(video_path),
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
    ]

    if vertical:
        # Crop to 9:16 center crop
        cmd.extend([
            "-vf", "crop=ih*9/16:ih,scale=1080:1920",
        ])

    cmd.append(str(output_path))

    tm.update_task(task_id, progress=40, message="Encoding clip...")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ffmpeg clip export failed: {result.stderr[-500:]}")
        raise RuntimeError("Clip export encoding failed")

    tm.update_task(task_id, progress=95, message="Clip ready")

    return {
        "filename": output_path.name,
        "duration": round(duration, 1),
        "vertical": vertical,
    }


@router.post("/export")
async def export_clip(req: ClipExportRequest):
    """Export a specific clip from the video."""
    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    existing = tm.get_active_task(req.project_name, "clip_export")
    if existing:
        return tm.task_to_dict(existing)

    task_id = tm.create_task(req.project_name, "clip_export")
    tm.run_in_background(
        task_id, _do_export_clip, project_dir,
        req.start, req.end, req.title, req.vertical, 0,
    )
    return tm.task_to_dict(tm.get_task(task_id))


@router.get("/{project_name}/list")
async def list_clips(project_name: str):
    """List exported clips for a project."""
    clips_dir = PROJECTS_DIR / project_name / "clips"
    if not clips_dir.exists():
        return []
    return [f.name for f in clips_dir.iterdir() if f.suffix == ".mp4"]


@router.get("/{project_name}/download/{filename}")
async def download_clip(project_name: str, filename: str):
    """Download an exported clip."""
    file_path = (PROJECTS_DIR / project_name / "clips" / filename).resolve()
    if not str(file_path).startswith(str((PROJECTS_DIR).resolve())):
        raise HTTPException(403, "Access denied")
    if not file_path.exists():
        raise HTTPException(404, "Clip not found")
    return FileResponse(str(file_path), filename=filename)
