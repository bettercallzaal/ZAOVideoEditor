"""Shared utilities for locating project files."""

from pathlib import Path
from fastapi import HTTPException


PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"


def get_project_dir(name: str) -> Path:
    d = PROJECTS_DIR / name
    if not d.exists():
        raise HTTPException(404, "Project not found")
    return d


def find_video(project_dir: Path, include_captioned: bool = False) -> Path:
    """Find the best available video file in a project.

    Args:
        project_dir: Path to the project directory.
        include_captioned: If True, prefer captioned.mp4 first.
    """
    candidates = []
    if include_captioned:
        candidates.append(project_dir / "processing" / "captioned.mp4")
        candidates.append(project_dir / "processing" / "trimmed.mp4")
    candidates.append(project_dir / "processing" / "assembled.mp4")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    for ext in [".mp4", ".mov", ".mkv", ".webm"]:
        p = project_dir / "input" / f"main{ext}"
        if p.exists():
            return p
    raise HTTPException(404, "No video found in project")


def find_best_transcript(project_dir: Path) -> dict:
    """Load the best available transcript for a project."""
    from .whisper_service import load_transcript
    for name in ["edited.json", "cleaned.json", "corrected.json", "raw.json"]:
        path = project_dir / "transcripts" / name
        if path.exists():
            return load_transcript(str(path))
    raise HTTPException(404, "No transcript found")
