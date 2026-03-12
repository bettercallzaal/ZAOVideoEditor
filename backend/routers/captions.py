import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from ..models.schemas import CaptionRequest, BurnCaptionRequest
from ..services.caption_gen import (
    generate_captions_from_segments, generate_srt, generate_ass, save_captions,
)
from ..services.ffmpeg_service import get_video_params, burn_captions
from ..services.whisper_service import load_transcript
from ..services import task_manager as tm

router = APIRouter(prefix="/api/captions", tags=["captions"])

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"


def get_best_transcript(project_dir: Path) -> dict:
    for name in ["edited.json", "cleaned.json", "corrected.json", "raw.json"]:
        path = project_dir / "transcripts" / name
        if path.exists():
            return load_transcript(str(path))
    raise HTTPException(404, "No transcript found")


def find_source_video(project_dir: Path) -> Path:
    assembled = project_dir / "processing" / "assembled.mp4"
    if assembled.exists():
        return assembled
    for ext in [".mp4", ".mov", ".mkv", ".webm"]:
        p = project_dir / "input" / f"main{ext}"
        if p.exists():
            return p
    raise HTTPException(404, "No video found")


@router.post("/generate")
async def generate(req: CaptionRequest):
    """Generate captions from transcript."""
    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    transcript = get_best_transcript(project_dir)
    captions = generate_captions_from_segments(transcript["segments"])

    captions_dir = project_dir / "captions"
    save_captions(captions, str(captions_dir / "captions.json"))

    srt_content = generate_srt(captions)
    with open(captions_dir / "captions.srt", "w") as f:
        f.write(srt_content)

    video_path = find_source_video(project_dir)
    params = get_video_params(str(video_path))
    ass_content = generate_ass(
        captions,
        theme=req.theme.value,
        video_width=params["width"],
        video_height=params["height"],
    )
    with open(captions_dir / "captions.ass", "w") as f:
        f.write(ass_content)

    return {
        "status": "complete",
        "caption_count": len(captions),
        "theme": req.theme.value,
    }


@router.get("/{project_name}")
async def get_captions(project_name: str):
    captions_path = PROJECTS_DIR / project_name / "captions" / "captions.json"
    if not captions_path.exists():
        raise HTTPException(404, "Captions not generated yet")
    with open(captions_path) as f:
        return json.load(f)


@router.get("/{project_name}/srt")
async def get_srt(project_name: str):
    srt_path = PROJECTS_DIR / project_name / "captions" / "captions.srt"
    if not srt_path.exists():
        raise HTTPException(404, "SRT not generated yet")
    with open(srt_path) as f:
        return {"content": f.read()}


@router.get("/{project_name}/ass")
async def get_ass(project_name: str):
    ass_path = PROJECTS_DIR / project_name / "captions" / "captions.ass"
    if not ass_path.exists():
        raise HTTPException(404, "ASS not generated yet")
    with open(ass_path) as f:
        return {"content": f.read()}


def _do_burn(task_id: str, project_dir: Path):
    """Background caption burn worker."""
    tm.update_task(task_id, progress=5, message="Preparing to burn captions...")

    ass_path = project_dir / "captions" / "captions.ass"
    if not ass_path.exists():
        raise RuntimeError("ASS captions not found. Generate captions first.")

    video_path = project_dir / "processing" / "assembled.mp4"
    if not video_path.exists():
        for ext in [".mp4", ".mov", ".mkv", ".webm"]:
            p = project_dir / "input" / f"main{ext}"
            if p.exists():
                video_path = p
                break

    output_path = project_dir / "processing" / "captioned.mp4"

    tm.update_task(task_id, progress=10, message="Rendering captions onto video...")
    burn_captions(str(video_path), str(ass_path), str(output_path))

    return {"output": str(output_path)}


@router.post("/burn")
async def burn(req: BurnCaptionRequest):
    """Burn captions as a background task."""
    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    existing = tm.get_active_task(req.project_name, "burn")
    if existing:
        return tm.task_to_dict(existing)

    task_id = tm.create_task(req.project_name, "burn")
    tm.run_in_background(task_id, _do_burn, project_dir)
    return tm.task_to_dict(tm.get_task(task_id))
