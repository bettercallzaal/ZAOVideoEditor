"""Shared utilities for locating project files."""

import re
from pathlib import Path
from fastapi import HTTPException


PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"

# A project name must start with an alphanumeric and contain only
# alphanumerics, space, dot, dash, underscore. This blocks path separators
# ("/", "\") and traversal sequences ("..", which starts with a dot).
_PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]*$")


def validate_project_name(name: str) -> str:
    """Validate a project name is safe to use as a path segment.

    Raises HTTPException(422) on any name that could escape PROJECTS_DIR via
    path separators or traversal sequences. Returns the name unchanged on success.
    """
    if not isinstance(name, str) or not name or len(name) > 100:
        raise HTTPException(422, "Invalid project name")
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(422, "Invalid project name")
    if not _PROJECT_NAME_RE.match(name):
        raise HTTPException(422, "Invalid project name")
    return name


def is_within(path: Path, base: Path) -> bool:
    """True if ``path`` is the same as or nested inside ``base`` (resolved).

    Correct containment check - avoids the sibling-prefix bypass of
    ``str(path).startswith(str(base))`` (e.g. /projects-evil vs /projects).
    """
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def project_dir_for(name: str) -> Path:
    """Resolve a validated project directory, asserting containment in PROJECTS_DIR.

    Use for path-parameter routes that build raw ``PROJECTS_DIR / name`` paths.
    Does NOT require the directory to exist (create flows rely on that).
    """
    validate_project_name(name)
    d = (PROJECTS_DIR / name).resolve()
    if not is_within(d, PROJECTS_DIR):
        raise HTTPException(403, "Access denied")
    return d


def get_project_dir(name: str) -> Path:
    validate_project_name(name)
    d = (PROJECTS_DIR / name).resolve()
    if not is_within(d, PROJECTS_DIR):
        raise HTTPException(403, "Access denied")
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
