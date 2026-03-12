import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from ..models.schemas import MetadataRequest, MetadataDraft
from ..services.metadata_gen import generate_description, generate_chapters, generate_tags
from ..services.whisper_service import load_transcript

router = APIRouter(prefix="/api/metadata", tags=["metadata"])

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"


def get_best_transcript(project_dir: Path) -> dict:
    for name in ["edited.json", "cleaned.json", "corrected.json", "raw.json"]:
        path = project_dir / "transcripts" / name
        if path.exists():
            return load_transcript(str(path))
    raise HTTPException(404, "No transcript found")


@router.post("/generate")
async def generate(req: MetadataRequest):
    """Generate YouTube metadata drafts."""
    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    transcript = get_best_transcript(project_dir)
    segments = transcript["segments"]

    description = generate_description(segments, req.project_name)
    chapters = generate_chapters(segments)
    tags = generate_tags(segments, req.project_name)

    metadata_dir = project_dir / "metadata"
    metadata_dir.mkdir(exist_ok=True)

    with open(metadata_dir / "description.txt", "w") as f:
        f.write(description)
    with open(metadata_dir / "chapters.txt", "w") as f:
        f.write(chapters)
    with open(metadata_dir / "tags.txt", "w") as f:
        f.write(tags)

    return {
        "status": "complete",
        "description": description,
        "chapters": chapters,
        "tags": tags,
    }


@router.get("/{project_name}")
async def get_metadata(project_name: str):
    """Get generated metadata."""
    metadata_dir = PROJECTS_DIR / project_name / "metadata"
    result = {}

    for name in ["description", "chapters", "tags"]:
        path = metadata_dir / f"{name}.txt"
        if path.exists():
            with open(path) as f:
                result[name] = f.read()
        else:
            result[name] = ""

    if not any(result.values()):
        raise HTTPException(404, "Metadata not generated yet")

    return result


@router.post("/{project_name}/save")
async def save_metadata(project_name: str, draft: MetadataDraft):
    """Save edited metadata."""
    metadata_dir = PROJECTS_DIR / project_name / "metadata"
    metadata_dir.mkdir(exist_ok=True)

    with open(metadata_dir / "description.txt", "w") as f:
        f.write(draft.description)
    with open(metadata_dir / "chapters.txt", "w") as f:
        f.write(draft.chapters)
    with open(metadata_dir / "tags.txt", "w") as f:
        f.write(draft.tags)

    return {"status": "saved"}
