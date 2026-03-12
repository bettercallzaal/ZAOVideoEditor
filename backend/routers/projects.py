import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from ..models.schemas import ProjectCreate, ProjectInfo

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

    dest = input_dir / f"main{ext}"
    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

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
