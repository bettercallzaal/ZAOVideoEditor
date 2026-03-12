import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException
from ..models.schemas import AssemblyRequest
from ..services.ffmpeg_service import get_video_params, assemble_videos, extract_audio
from ..services import task_manager as tm

router = APIRouter(prefix="/api/assembly", tags=["assembly"])

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"


def find_main_video(project_dir: Path) -> Path:
    for ext in [".mp4", ".mov", ".mkv", ".webm"]:
        p = project_dir / "input" / f"main{ext}"
        if p.exists():
            return p
    raise HTTPException(404, "Main video not found. Upload a video first.")


def _do_assemble(task_id: str, project_dir: Path, use_intro: bool, use_outro: bool):
    """Background assembly worker."""
    tm.update_task(task_id, progress=10, message="Finding video files...")

    main_video = None
    for ext in [".mp4", ".mov", ".mkv", ".webm"]:
        p = project_dir / "input" / f"main{ext}"
        if p.exists():
            main_video = p
            break
    if not main_video:
        raise RuntimeError("Main video not found")

    main_params = get_video_params(str(main_video))
    parts = []

    if use_intro:
        for ext in [".mp4", ".mov", ".mkv", ".webm"]:
            candidate = project_dir / "input" / f"intro{ext}"
            if candidate.exists():
                parts.append(str(candidate))
                break

    parts.append(str(main_video))

    if use_outro:
        for ext in [".mp4", ".mov", ".mkv", ".webm"]:
            candidate = project_dir / "input" / f"outro{ext}"
            if candidate.exists():
                parts.append(str(candidate))
                break

    output_path = project_dir / "processing" / "assembled.mp4"

    if len(parts) == 1:
        tm.update_task(task_id, progress=50, message="Copying video (no intro/outro)...")
        shutil.copy2(parts[0], str(output_path))
    else:
        tm.update_task(task_id, progress=20, message=f"Assembling {len(parts)} video parts...")
        assemble_videos(parts, str(output_path), main_params)

    tm.update_task(task_id, progress=80, message="Extracting audio...")
    audio_path = project_dir / "processing" / "audio.wav"
    extract_audio(str(output_path), str(audio_path))

    return {"params": main_params}


@router.post("/assemble")
async def assemble(req: AssemblyRequest):
    """Assemble video as a background task."""
    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    existing = tm.get_active_task(req.project_name, "assemble")
    if existing:
        return tm.task_to_dict(existing)

    task_id = tm.create_task(req.project_name, "assemble")
    tm.run_in_background(task_id, _do_assemble, project_dir, req.use_intro, req.use_outro)
    return tm.task_to_dict(tm.get_task(task_id))


@router.post("/extract-audio")
async def extract_audio_endpoint(project_name: str):
    """Extract audio from assembled/main video."""
    project_dir = PROJECTS_DIR / project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    video_path = project_dir / "processing" / "assembled.mp4"
    if not video_path.exists():
        video_path = find_main_video(project_dir)

    audio_path = project_dir / "processing" / "audio.wav"
    extract_audio(str(video_path), str(audio_path))
    return {"status": "complete", "audio_path": str(audio_path)}
