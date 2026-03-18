import os
import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from ..models.schemas import ExportRequest

router = APIRouter(prefix="/api/export", tags=["export"])

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"


def _link_or_copy(src: Path, dest: Path):
    """Create a hardlink if possible, fall back to copy.

    Hardlinks share the same inode so they use zero extra disk space
    while still giving export/ its own directory entry.
    Symlinks are avoided because FileResponse follows the real path.
    """
    if dest.exists():
        dest.unlink()
    try:
        os.link(str(src), str(dest))
    except OSError:
        shutil.copy2(str(src), str(dest))


@router.post("/package")
async def create_export_package(req: ExportRequest):
    """Assemble all export files into the exports folder."""
    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    exports_dir = project_dir / "exports"
    exports_dir.mkdir(exist_ok=True)

    exported = []

    # Link captioned video (or assembled/main if no captions burned)
    captioned = project_dir / "processing" / "captioned.mp4"
    assembled = project_dir / "processing" / "assembled.mp4"
    if captioned.exists():
        _link_or_copy(captioned, exports_dir / "captioned.mp4")
        exported.append("captioned.mp4")

    # Also link source video for reference
    if assembled.exists():
        _link_or_copy(assembled, exports_dir / "source.mp4")
        exported.append("source.mp4")
    else:
        for ext in [".mp4", ".mov", ".mkv", ".webm"]:
            main = project_dir / "input" / f"main{ext}"
            if main.exists():
                _link_or_copy(main, exports_dir / f"source{ext}")
                exported.append(f"source{ext}")
                break

    # Small files — just copy (negligible size)
    srt = project_dir / "captions" / "captions.srt"
    if srt.exists():
        shutil.copy2(str(srt), str(exports_dir / "captions.srt"))
        exported.append("captions.srt")

    ass = project_dir / "captions" / "captions.ass"
    if ass.exists():
        shutil.copy2(str(ass), str(exports_dir / "captions.ass"))
        exported.append("captions.ass")

    for name in ["edited.json", "cleaned.json"]:
        transcript = project_dir / "transcripts" / name
        if transcript.exists():
            shutil.copy2(str(transcript), str(exports_dir / "transcript.json"))
            exported.append("transcript.json")
            break

    cleaned_txt = project_dir / "transcripts" / "cleaned.txt"
    if cleaned_txt.exists():
        shutil.copy2(str(cleaned_txt), str(exports_dir / "transcript.txt"))
        exported.append("transcript.txt")

    for name in ["description.txt", "chapters.txt", "tags.txt"]:
        src = project_dir / "metadata" / name
        if src.exists():
            shutil.copy2(str(src), str(exports_dir / name))
            exported.append(name)

    return {"status": "complete", "files": exported}


@router.get("/{project_name}/files")
async def list_export_files(project_name: str):
    """List files in the exports folder."""
    exports_dir = PROJECTS_DIR / project_name / "exports"
    if not exports_dir.exists():
        return []
    return [f.name for f in exports_dir.iterdir() if f.is_file()]


@router.get("/{project_name}/download/{filename}")
async def download_file(project_name: str, filename: str):
    """Download an export file."""
    file_path = (PROJECTS_DIR / project_name / "exports" / filename).resolve()
    if not str(file_path).startswith(str((PROJECTS_DIR).resolve())):
        raise HTTPException(403, "Access denied")
    if not file_path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(str(file_path), filename=filename)
