"""Content generation endpoints — recap, clippable moments, show notes."""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.whisper_service import load_transcript

router = APIRouter(prefix="/api/content", tags=["content"])

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"


class ContentRequest(BaseModel):
    project_name: str


@router.post("/generate")
async def generate_content(req: ContentRequest):
    """Generate recap, clippable moments, show notes, and tweets from transcript."""
    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    # Find best transcript
    transcript = None
    for name in ["edited.json", "cleaned.json", "corrected.json", "raw.json"]:
        path = project_dir / "transcripts" / name
        if path.exists():
            transcript = load_transcript(str(path))
            break

    if not transcript or not transcript.get("segments"):
        raise HTTPException(404, "No transcript found — transcribe first")

    from ..services.content_gen import generate_recap_and_clips

    try:
        result = generate_recap_and_clips(
            transcript["segments"],
            project_name=req.project_name,
        )
    except RuntimeError as e:
        raise HTTPException(400, {
            "message": str(e),
            "action": "Install Ollama locally, or set OPENAI_API_KEY / GROQ_API_KEY in your environment and restart the backend.",
        })
    except Exception as e:
        raise HTTPException(500, {
            "message": f"Content generation failed: {e}",
            "action": "Check the backend server logs for the full traceback.",
        })

    # Save to project
    content_path = project_dir / "metadata" / "content.json"
    content_path.parent.mkdir(parents=True, exist_ok=True)
    with open(content_path, "w") as f:
        json.dump(result, f, indent=2)

    return result


@router.post("/{project_name}/audio-summary")
async def generate_audio_summary_endpoint(project_name: str):
    """Generate a podcast-style audio summary from the recap."""
    project_dir = PROJECTS_DIR / project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    # Load existing content (must have generated recap first)
    content_path = project_dir / "metadata" / "content.json"
    if not content_path.exists():
        raise HTTPException(400, "Generate content first — no recap available")

    with open(content_path) as f:
        content = json.load(f)

    recap_text = content.get("recap")
    if not recap_text:
        raise HTTPException(400, "No recap found in generated content")

    from ..services.audio_summary import generate_audio_summary

    try:
        output_path = generate_audio_summary(recap_text, str(project_dir))
    except ImportError as e:
        raise HTTPException(400, f"Missing dependency: {e}. Install with: pip install gtts")
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Audio summary generation failed: {e}")

    return {
        "status": "complete",
        "file": "audio_summary.mp3",
        "path": output_path,
    }


@router.get("/{project_name}")
async def get_content(project_name: str):
    """Get previously generated content."""
    content_path = PROJECTS_DIR / project_name / "metadata" / "content.json"
    if not content_path.exists():
        raise HTTPException(404, "No content generated yet")

    with open(content_path) as f:
        return json.load(f)
