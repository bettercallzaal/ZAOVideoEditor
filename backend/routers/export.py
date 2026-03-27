import os
import json
import shutil
from datetime import date
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from ..models.schemas import ExportRequest
from ..services.whisper_service import load_transcript

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


@router.get("/gdrive-status")
async def gdrive_status():
    """Check whether Google Drive credentials are configured."""
    from ..services.gdrive_service import is_gdrive_configured
    return {"configured": is_gdrive_configured()}


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


def _get_best_transcript(project_dir: Path) -> tuple[dict, str]:
    """Return the best available transcript data and its source name."""
    for name in ["edited.json", "cleaned.json", "corrected.json", "raw.json"]:
        path = project_dir / "transcripts" / name
        if path.exists():
            return load_transcript(str(path)), name
    return None, None


def _format_notebooklm(project_name: str, transcript: dict) -> str:
    """Format transcript as plain text optimized for NotebookLM ingestion."""
    segments = transcript.get("segments", [])

    # Calculate duration from last segment
    duration_str = "Unknown"
    if segments:
        last_end = max(seg.get("end", 0) for seg in segments)
        hours = int(last_end // 3600)
        minutes = int((last_end % 3600) // 60)
        seconds = int(last_end % 60)
        if hours > 0:
            duration_str = f"{hours}h {minutes}m {seconds}s"
        else:
            duration_str = f"{minutes}m {seconds}s"

    lines = []
    lines.append(f"Title: {project_name}")
    lines.append(f"Date: {date.today().isoformat()}")
    lines.append(f"Duration: {duration_str}")
    lines.append("")
    lines.append("[TRANSCRIPT]")
    lines.append("")

    for seg in segments:
        m = int(seg["start"] // 60)
        s = int(seg["start"] % 60)
        timestamp = f"[{m:02d}:{s:02d}]"
        speaker = seg.get("speaker", "")
        if speaker:
            lines.append(f"{timestamp} {speaker}: {seg['text']}")
        else:
            lines.append(f"{timestamp} {seg['text']}")

    return "\n".join(lines)


@router.post("/{project_name}/notebooklm")
async def export_notebooklm(project_name: str):
    """Export transcript as a .txt file optimized for NotebookLM."""
    project_dir = PROJECTS_DIR / project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    transcript, source = _get_best_transcript(project_dir)
    if not transcript:
        raise HTTPException(404, "No transcript found")

    text = _format_notebooklm(project_name, transcript)

    # Save to exports folder
    exports_dir = project_dir / "exports"
    exports_dir.mkdir(exist_ok=True)
    out_path = exports_dir / f"{project_name}_notebooklm.txt"
    out_path.write_text(text, encoding="utf-8")

    return FileResponse(
        str(out_path),
        filename=f"{project_name}_notebooklm.txt",
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{project_name}_notebooklm.txt"'},
    )


@router.post("/{project_name}/gdrive")
async def upload_to_gdrive(project_name: str):
    """Upload transcript/caption/metadata files to Google Drive."""
    from ..services.gdrive_service import is_gdrive_configured, upload_project_to_drive

    if not is_gdrive_configured():
        raise HTTPException(400, "Google Drive not configured — place credentials.json in backend/")

    project_dir = PROJECTS_DIR / project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    try:
        uploaded = upload_project_to_drive(project_name, str(project_dir))
    except Exception as e:
        raise HTTPException(500, f"Google Drive upload failed: {e}")

    return {"status": "complete", "files": uploaded}


@router.get("/{project_name}/notebooklm-text")
async def get_notebooklm_text(project_name: str):
    """Return the NotebookLM-formatted transcript as plain text (for clipboard copy)."""
    project_dir = PROJECTS_DIR / project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    transcript, source = _get_best_transcript(project_dir)
    if not transcript:
        raise HTTPException(404, "No transcript found")

    text = _format_notebooklm(project_name, transcript)
    return PlainTextResponse(text)
