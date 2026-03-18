import os
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse
from ..models.schemas import ProjectCreate, ProjectInfo
from ..services.storage import (
    get_project_storage, get_all_projects_storage,
    get_cleanable_files, cleanup_project, verify_file_integrity,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"


def get_project_dir(name: str) -> Path:
    return PROJECTS_DIR / name


def get_stage_status(project_dir: Path) -> dict:
    """Check which stages are complete for a project."""
    stages = {
        "upload": "not_started",
        "assembly": "not_started",
        "transcription": "not_started",
        "correction": "not_started",
        "cleanup": "not_started",
        "editing": "not_started",
        "captions": "not_started",
        "burn_captions": "not_started",
        "metadata": "not_started",
        "export": "not_started",
    }

    input_dir = project_dir / "input"
    processing_dir = project_dir / "processing"
    transcripts_dir = project_dir / "transcripts"
    captions_dir = project_dir / "captions"
    metadata_dir = project_dir / "metadata"
    exports_dir = project_dir / "exports"

    # Check upload
    if input_dir.exists() and any(input_dir.glob("main.*")):
        stages["upload"] = "complete"

    # Check assembly
    if (processing_dir / "assembled.mp4").exists():
        stages["assembly"] = "complete"
    elif stages["upload"] == "complete":
        # If uploaded but no assembly, mark as complete (no intro/outro needed)
        stages["assembly"] = "complete"

    # Check transcription
    if (transcripts_dir / "raw.json").exists():
        stages["transcription"] = "complete"

    # Check correction
    if (transcripts_dir / "corrected.json").exists():
        stages["correction"] = "complete"

    # Check cleanup
    if (transcripts_dir / "cleaned.json").exists():
        stages["cleanup"] = "complete"

    # Check editing
    if (transcripts_dir / "edited.json").exists():
        stages["editing"] = "complete"

    # Check captions
    if (captions_dir / "captions.json").exists():
        stages["captions"] = "complete"

    # Check burn
    if (processing_dir / "captioned.mp4").exists():
        stages["burn_captions"] = "complete"

    # Check metadata
    if (metadata_dir / "description.txt").exists():
        stages["metadata"] = "complete"

    # Check export
    if (exports_dir / "final.mp4").exists() or (exports_dir / "captioned.mp4").exists():
        stages["export"] = "complete"

    return stages


@router.post("")
async def create_project(project: ProjectCreate):
    """Create a new project."""
    project_dir = get_project_dir(project.name)
    if project_dir.exists():
        raise HTTPException(400, "Project already exists")

    for subdir in ["input", "processing", "transcripts", "captions", "metadata", "exports"]:
        (project_dir / subdir).mkdir(parents=True, exist_ok=True)

    # Save project info
    info = {
        "name": project.name,
        "description": project.description or "",
        "created_at": datetime.now().isoformat(),
    }
    with open(project_dir / "project.json", "w") as f:
        json.dump(info, f, indent=2)

    return {"status": "created", "name": project.name}


@router.get("")
async def list_projects():
    """List all projects."""
    if not PROJECTS_DIR.exists():
        return []
    projects = []
    for d in sorted(PROJECTS_DIR.iterdir()):
        if d.is_dir() and (d / "project.json").exists():
            with open(d / "project.json") as f:
                info = json.load(f)
            info["stages"] = get_stage_status(d)
            projects.append(info)
    return projects


@router.get("/{name}")
async def get_project(name: str):
    """Get project details."""
    project_dir = get_project_dir(name)
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    with open(project_dir / "project.json") as f:
        info = json.load(f)
    info["stages"] = get_stage_status(project_dir)
    return info


@router.delete("/{name}")
async def delete_project(name: str):
    """Delete a project."""
    project_dir = get_project_dir(name)
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")
    shutil.rmtree(project_dir)
    return {"status": "deleted"}


@router.post("/{name}/upload")
async def upload_main_video(name: str, file: UploadFile = File(...)):
    """Upload the main video file."""
    project_dir = get_project_dir(name)
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    ext = Path(file.filename).suffix.lower()
    if ext not in [".mp4", ".mov", ".mkv", ".webm"]:
        raise HTTPException(400, f"Unsupported format: {ext}")

    # Remove any existing main video
    input_dir = project_dir / "input"
    for existing in input_dir.glob("main.*"):
        existing.unlink()

    # Check available disk space (require at least 1GB free)
    import shutil as _shutil
    disk_usage = _shutil.disk_usage(str(input_dir))
    if disk_usage.free < 1024 * 1024 * 1024:
        raise HTTPException(507, "Insufficient disk space (need at least 1GB free)")

    MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10 GB limit
    dest = input_dir / f"main{ext}"
    total_written = 0
    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            total_written += len(chunk)
            if total_written > MAX_FILE_SIZE:
                f.close()
                dest.unlink()
                raise HTTPException(413, "File too large (max 10 GB)")
            f.write(chunk)

    # Remux non-mp4 formats to mp4 container for browser compatibility
    # Uses stream copy (no re-encode) so it's fast even for large files
    if ext != ".mp4":
        mp4_dest = input_dir / "main.mp4"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(dest), "-c", "copy",
                 "-movflags", "+faststart", str(mp4_dest)],
                check=True, capture_output=True, timeout=120,
            )
            dest.unlink()  # Remove original non-mp4
            dest = mp4_dest
            ext = ".mp4"
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # If stream copy fails (incompatible codec), do a fast re-encode
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(dest), "-c:v", "libx264",
                     "-preset", "ultrafast", "-crf", "18", "-c:a", "aac",
                     "-movflags", "+faststart", str(mp4_dest)],
                    check=True, capture_output=True, timeout=600,
                )
                dest.unlink()
                dest = mp4_dest
                ext = ".mp4"
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass  # Keep original if all else fails

    return {"status": "uploaded", "filename": f"main{ext}", "size": dest.stat().st_size}


@router.post("/{name}/upload-intro")
async def upload_intro(name: str, file: UploadFile = File(...)):
    """Upload a custom intro video."""
    project_dir = get_project_dir(name)
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    ext = Path(file.filename).suffix.lower()
    dest = project_dir / "input" / f"intro{ext}"

    # Remove existing intros
    for existing in (project_dir / "input").glob("intro.*"):
        existing.unlink()

    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    return {"status": "uploaded", "type": "intro"}


@router.post("/{name}/upload-outro")
async def upload_outro(name: str, file: UploadFile = File(...)):
    """Upload a custom outro video."""
    project_dir = get_project_dir(name)
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    ext = Path(file.filename).suffix.lower()
    dest = project_dir / "input" / f"outro{ext}"

    # Remove existing outros
    for existing in (project_dir / "input").glob("outro.*"):
        existing.unlink()

    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    return {"status": "uploaded", "type": "outro"}


@router.get("/{name}/video-url")
async def get_video_url(name: str, stage: str = "source"):
    """Get the video file path for serving."""
    project_dir = get_project_dir(name)
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    if stage == "captioned":
        video = project_dir / "processing" / "captioned.mp4"
    elif stage == "assembled":
        video = project_dir / "processing" / "assembled.mp4"
    else:
        # Find main video
        video = None
        for ext in [".mp4", ".mov", ".mkv", ".webm"]:
            candidate = project_dir / "input" / f"main{ext}"
            if candidate.exists():
                video = candidate
                break

    if not video or not video.exists():
        raise HTTPException(404, "Video not found")

    return {"path": str(video), "filename": video.name}


@router.get("/{name}/video-stream")
async def stream_video(name: str, stage: str = "source"):
    """Serve the actual video file for the player."""
    project_dir = get_project_dir(name)
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    if stage == "captioned":
        video = project_dir / "processing" / "captioned.mp4"
    elif stage == "assembled":
        video = project_dir / "processing" / "assembled.mp4"
    else:
        video = None
        for ext in [".mp4", ".mov", ".mkv", ".webm"]:
            candidate = project_dir / "input" / f"main{ext}"
            if candidate.exists():
                video = candidate
                break

    if not video or not video.exists():
        raise HTTPException(404, "Video not found")

    media_types = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
    }
    media_type = media_types.get(video.suffix.lower(), "video/mp4")

    return FileResponse(
        str(video),
        media_type=media_type,
        headers={"Accept-Ranges": "bytes"},
    )


# --- Storage endpoints ---

@router.get("/{name}/storage")
async def project_storage(name: str):
    """Get disk usage breakdown for a project."""
    project_dir = get_project_dir(name)
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")
    return get_project_storage(name)


@router.get("/{name}/cleanable")
async def project_cleanable(name: str):
    """List intermediate files that can be safely removed."""
    project_dir = get_project_dir(name)
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")
    return get_cleanable_files(name)


@router.post("/{name}/cleanup")
async def project_cleanup(name: str):
    """Remove all cleanable intermediate files to free disk space."""
    project_dir = get_project_dir(name)
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")
    return cleanup_project(name)


