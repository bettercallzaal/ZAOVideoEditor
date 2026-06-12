"""Studio: the one-command local app.

A dead-simple drag-and-drop surface over the recordings pipeline. No Supabase,
no Vercel, no flags - drop a recording, get the transcripts, trim it, download.
Everything is served from this same FastAPI process, so the page and the API are
same-origin and there is nothing else to run.
"""

import json
import re
import shutil
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from ..services import recordings_pipeline as rp
from ..services import task_manager as tm

router = APIRouter(prefix="/api/studio", tags=["studio"])

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"
STATIC_DIR = Path(__file__).parent.parent / "static"
SUBDIRS = ["input", "processing", "transcripts", "captions", "metadata", "exports", "clips"]
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "recording"


def _project_dir(name: str) -> Path:
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(422, "Invalid project")
    d = (PROJECTS_DIR / name).resolve()
    if not d.is_relative_to(PROJECTS_DIR.resolve()):
        raise HTTPException(403, "Access denied")
    return d


def _find_input(project_dir: Path) -> Path:
    for ext in list(VIDEO_EXTS) + list(AUDIO_EXTS):
        p = project_dir / "input" / f"main{ext}"
        if p.exists():
            return p
    raise HTTPException(404, "No input media")


def _make_project(name: str, title: str, source: str) -> Path:
    project_dir = _project_dir(name)
    for sub in SUBDIRS:
        (project_dir / sub).mkdir(parents=True, exist_ok=True)
    (project_dir / "project.json").write_text(json.dumps({
        "name": name, "title": title,
        "created_at": datetime.now().isoformat(), "source": source,
    }, indent=2), encoding="utf-8")
    return project_dir


def _do_process(task_id: str, project_dir: Path, media: str, title: str,
                speakers: bool, quality: str = "fast"):
    result = rp.process_recording(
        media, title=title, quality=quality, engine="auto",
        out_dir=str(project_dir / "transcripts"), readable_llm=True,
        detect_speakers=speakers,
        on_progress=lambda pct, msg: tm.update_task(task_id, progress=pct, message=msg),
    )
    return {
        "title": result["title"],
        "duration": result["duration"],
        "segment_count": result["segment_count"],
        "review_flags": result["review_flags"],
        "edit_sheet": result["edit_sheet"],
        "readable_backend": result["readable_backend"],
    }


@router.post("/process")
async def process(file: UploadFile = File(...), title: str = Form(""),
                  speakers: bool = Form(False), quality: str = Form("fast")):
    """Create a project from an uploaded recording and run the pipeline."""
    orig = file.filename or "recording"
    ext = Path(orig).suffix.lower()
    if ext not in VIDEO_EXTS and ext not in AUDIO_EXTS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    disp = title or Path(orig).stem
    name = _slug(disp)
    project_dir = _make_project(name, disp, "studio")

    dest = project_dir / "input" / f"main{ext}"
    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    task_id = tm.create_task(name, "studio_process")
    tm.run_in_background(task_id, _do_process, project_dir, str(dest), disp, speakers, quality)
    return {"project": name, "task_id": task_id}


def _do_ingest_process(task_id: str, project_dir: Path, url: str, title: str,
                       speakers: bool, quality: str = "fast"):
    from ..services import ingest_service
    tm.update_task(task_id, progress=2, message="Fetching from link...")
    ingest_service.download_to_project(
        url, project_dir,
        on_progress=lambda pct, msg: tm.update_task(task_id, progress=min(int(pct * 0.4), 40), message=msg),
    )
    media = _find_input(project_dir)
    return _do_process(task_id, project_dir, str(media), title, speakers, quality)


@router.post("/ingest")
async def ingest_link(url: str = Form(...), title: str = Form(""),
                      speakers: bool = Form(False), quality: str = Form("fast")):
    """Pull a recording from a URL (YouTube / Twitch / Restream / HLS) and process it."""
    from ..services import ingest_service
    if not ingest_service.yt_dlp_available():
        raise HTTPException(400, "yt-dlp is not installed - run: pip install yt-dlp")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(422, "Provide a valid http(s) URL")

    disp = title or "link recording"
    name = _slug(disp)
    project_dir = _make_project(name, disp, "studio-link")
    task_id = tm.create_task(name, "studio_process")
    tm.run_in_background(task_id, _do_ingest_process, project_dir, url, disp, speakers, quality)
    return {"project": name, "task_id": task_id}


@router.get("/{project}/result")
async def result(project: str):
    """Read the written pipeline outputs for a project."""
    project_dir = _project_dir(project)
    tdir = project_dir / "transcripts"
    if not tdir.exists():
        raise HTTPException(404, "Not processed yet")
    slug = project
    out = {"project": project}
    readable = next(tdir.glob("*.readable.md"), None)
    sheet = next(tdir.glob("*.edit-sheet.json"), None)
    flags = next(tdir.glob("*.review-flags.json"), None)
    out["readable"] = readable.read_text(encoding="utf-8") if readable else ""
    out["edit_sheet"] = json.loads(sheet.read_text()) if sheet else {"cuts": []}
    out["review_flags"] = json.loads(flags.read_text()) if flags else []
    out["has_trimmed"] = (project_dir / "processing" / "trimmed.mp4").exists()
    return out


def _do_render(task_id: str, project_dir: Path, media: str, sheet: dict):
    from ..services.render_service import render_cuts
    out = project_dir / "processing" / "trimmed.mp4"
    tm.update_task(task_id, progress=15, message="Rendering trimmed video...")
    stats = render_cuts(media, sheet, str(out))
    tm.update_task(task_id, progress=95, message="Trimmed video ready")
    return stats


@router.post("/{project}/render")
async def render(project: str):
    """Render a trimmed video from the saved edit sheet (non-destructive)."""
    project_dir = _project_dir(project)
    sheet_file = next((project_dir / "transcripts").glob("*.edit-sheet.json"), None)
    if not sheet_file:
        raise HTTPException(404, "No edit sheet - process first")
    sheet = json.loads(sheet_file.read_text())
    media = _find_input(project_dir)
    existing = tm.get_active_task(project, "studio_render")
    if existing:
        return tm.task_to_dict(existing)
    task_id = tm.create_task(project, "studio_render")
    tm.run_in_background(task_id, _do_render, project_dir, str(media), sheet)
    return {"task_id": task_id}


@router.get("/{project}/download/{kind}")
async def download(project: str, kind: str):
    """Download an output: readable | cut | trimmed | editsheet."""
    project_dir = _project_dir(project)
    tdir = project_dir / "transcripts"
    mapping = {
        "readable": (next(tdir.glob("*.readable.md"), None), "text/markdown"),
        "cut": (next(tdir.glob("*.cut.md"), None), "text/markdown"),
        "editsheet": (next(tdir.glob("*.edit-sheet.json"), None), "application/json"),
        "trimmed": (project_dir / "processing" / "trimmed.mp4", "video/mp4"),
    }
    entry = mapping.get(kind)
    if not entry or not entry[0] or not Path(entry[0]).exists():
        raise HTTPException(404, "File not available")
    path = Path(entry[0])
    return FileResponse(str(path), media_type=entry[1], filename=path.name)


def _load_segments(project_dir: Path) -> list:
    cut = next((project_dir / "transcripts").glob("*.cut.json"), None)
    if not cut:
        raise HTTPException(404, "No transcript - process first")
    return json.loads(cut.read_text())


def _do_clips(task_id: str, project_dir: Path, aspects: list):
    from ..services import recordings_export as rx
    segments = _load_segments(project_dir)
    master = project_dir / "processing" / "trimmed.mp4"
    if not master.exists():
        master = Path(_find_input(project_dir))
    tm.update_task(task_id, progress=15, message="Finding the best moments...")
    res = rx.render_clips(
        str(master), segments, project_dir / "clips",
        aspects=aspects, project_name=project_dir.name,
    )
    tm.update_task(task_id, progress=95, message="Clips ready")
    return res


@router.post("/{project}/clips")
async def make_clips(project: str, aspects: str = Form("9:16")):
    """Render captioned highlight clips in the requested aspect ratios + per-clip copy."""
    project_dir = _project_dir(project)
    asp = [a.strip() for a in aspects.split(",") if a.strip()] or ["9:16"]
    existing = tm.get_active_task(project, "studio_clips")
    if existing:
        return tm.task_to_dict(existing)
    task_id = tm.create_task(project, "studio_clips")
    tm.run_in_background(task_id, _do_clips, project_dir, asp)
    return {"task_id": task_id}


@router.get("/{project}/clips")
async def list_clips(project: str):
    """List rendered clips with their copy."""
    project_dir = _project_dir(project)
    cdir = project_dir / "clips"
    if not cdir.exists():
        return []
    out = []
    for mp4 in sorted(cdir.glob("*.mp4")):
        stem = mp4.stem
        base = stem.rsplit("_", 1)[0] if stem.rsplit("_", 1)[-1] in {"9x16", "1x1", "16x9"} else stem
        copy_path = cdir / f"{base}.copy.json"
        copy = None
        if copy_path.exists():
            try:
                copy = json.loads(copy_path.read_text())
            except (ValueError, OSError):
                copy = None
        out.append({"filename": mp4.name, "base": base, "copy": copy})
    return out


@router.get("/{project}/clip/{filename}")
async def download_clip(project: str, filename: str):
    project_dir = _project_dir(project)
    cdir = project_dir / "clips"
    fp = (cdir / filename).resolve()
    if not fp.is_relative_to(cdir.resolve()) or not fp.exists():
        raise HTTPException(404, "Clip not found")
    return FileResponse(str(fp), media_type="video/mp4", filename=fp.name)


def _do_socials(task_id: str, project_dir: Path):
    from ..services import social_gen
    tdir = project_dir / "transcripts"
    readable = next(tdir.glob("*.readable.md"), None)
    title = project_dir.name
    pj = project_dir / "project.json"
    if pj.exists():
        try:
            title = json.loads(pj.read_text()).get("title", title)
        except (ValueError, OSError):
            pass
    tm.update_task(task_id, progress=30, message="Drafting episode posts...")
    episode = social_gen.episode_posts(readable.read_text() if readable else "", title=title)

    clip_posts = []
    cdir = project_dir / "clips"
    if cdir.exists():
        for copy_file in sorted(cdir.glob("*.copy.json")):
            try:
                copy = json.loads(copy_file.read_text())
            except (ValueError, OSError):
                continue
            text = (copy.get("title", "") + ". " + copy.get("caption", "")).strip(". ")
            post = social_gen.clip_post(text, title=copy.get("title", ""))
            clip_posts.append({"clip": copy_file.stem.replace(".copy", ""), "post": post["post"]})

    result = {"episode": episode, "clips": clip_posts}
    (project_dir / "metadata").mkdir(parents=True, exist_ok=True)
    (project_dir / "metadata" / "socials.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    tm.update_task(task_id, progress=95, message="Posts drafted")
    return result


@router.post("/{project}/socials")
async def make_socials(project: str):
    """Draft Farcaster + X posts for the episode and each clip."""
    project_dir = _project_dir(project)
    existing = tm.get_active_task(project, "studio_socials")
    if existing:
        return tm.task_to_dict(existing)
    task_id = tm.create_task(project, "studio_socials")
    tm.run_in_background(task_id, _do_socials, project_dir)
    return {"task_id": task_id}


def _do_full(task_id: str, project_dir: Path, media: str, title: str,
             speakers: bool, quality: str, clips: bool, socials: bool, aspects: list):
    """One-call pipeline for external automation: process -> clips -> socials."""
    out = _do_process(task_id, project_dir, media, title, speakers, quality)
    result = {"project": project_dir.name, "process": out}
    if clips:
        from ..services import recordings_export as rx
        segs = json.loads(_cut_json_path(project_dir).read_text())
        master = project_dir / "processing" / "trimmed.mp4"
        src = str(master) if master.exists() else media
        tm.update_task(task_id, progress=70, message="Rendering clips...")
        result["clips"] = rx.render_clips(src, segs, project_dir / "clips",
                                          aspects=aspects, project_name=project_dir.name)
    if socials:
        tm.update_task(task_id, progress=88, message="Drafting social posts...")
        result["socials"] = _do_socials(task_id, project_dir)
    tm.update_task(task_id, progress=100, message="Done")
    return result


@router.post("/full")
async def full(file: UploadFile = File(None), url: str = Form(""), title: str = Form(""),
               speakers: bool = Form(False), quality: str = Form("fast"),
               clips: bool = Form(True), socials: bool = Form(True), aspects: str = Form("9:16")):
    """One call -> the whole pipeline. For automation / calling from other tools.

    Provide either an uploaded `file` or a `url`. Returns {project, task_id}; poll
    /api/tasks/{task_id} for {process, clips, socials} in the result.
    """
    asp = [a.strip() for a in aspects.split(",") if a.strip()] or ["9:16"]
    if file is not None and file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in VIDEO_EXTS and ext not in AUDIO_EXTS:
            raise HTTPException(400, f"Unsupported file type: {ext}")
        disp = title or Path(file.filename).stem
        project_dir = _make_project(_slug(disp), disp, "api")
        dest = project_dir / "input" / f"main{ext}"
        with open(dest, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)
        media = str(dest)
        run = lambda tid: _do_full(tid, project_dir, media, disp, speakers, quality, clips, socials, asp)  # noqa: E731
    elif url:
        from ..services import ingest_service
        if not ingest_service.yt_dlp_available():
            raise HTTPException(400, "yt-dlp not installed")
        disp = title or "api recording"
        project_dir = _make_project(_slug(disp), disp, "api-link")

        def run(tid):
            ingest_service.download_to_project(
                url, project_dir,
                on_progress=lambda pct, msg: tm.update_task(tid, progress=min(int(pct * 0.3), 30), message=msg))
            return _do_full(tid, project_dir, str(_find_input(project_dir)), disp, speakers, quality, clips, socials, asp)
    else:
        raise HTTPException(422, "Provide a file or a url")

    task_id = tm.create_task(project_dir.name, "studio_full")
    tm.run_in_background(task_id, lambda tid: run(tid))
    return {"project": project_dir.name, "task_id": task_id}


def _cut_json_path(project_dir: Path):
    return next((project_dir / "transcripts").glob("*.cut.json"), None)


def _edit_sheet_path(project_dir: Path):
    return next((project_dir / "transcripts").glob("*.edit-sheet.json"), None)


@router.get("/{project}/segments")
async def get_segments(project: str):
    """The corrected, word-timestamped segments (for the editor) + speakers."""
    project_dir = _project_dir(project)
    cut = _cut_json_path(project_dir)
    if not cut:
        raise HTTPException(404, "No transcript - process first")
    segments = json.loads(cut.read_text())
    speakers = sorted({s["speaker"] for s in segments if s.get("speaker")})
    return {"segments": segments, "speakers": speakers}


class SaveTranscript(BaseModel):
    segments: list


@router.post("/{project}/transcript")
async def save_transcript(project: str, body: SaveTranscript):
    """Save edited segments (word fixes) and regenerate the readable transcript."""
    project_dir = _project_dir(project)
    cut = _cut_json_path(project_dir)
    if not cut:
        raise HTTPException(404, "No transcript")
    from ..services.recordings_pipeline import _cut_transcript_md
    from ..services.readable_pass import make_readable
    segs = body.segments
    cut.write_text(json.dumps(segs, indent=2), encoding="utf-8")
    slug = cut.stem.replace(".cut", "")
    title = _project_title(project_dir)
    (project_dir / "transcripts" / f"{slug}.cut.md").write_text(
        _cut_transcript_md(segs, title), encoding="utf-8")
    readable = make_readable(segs, title=title, deterministic_only=True)
    (project_dir / "transcripts" / f"{slug}.readable.md").write_text(
        readable["markdown"], encoding="utf-8")
    return {"ok": True}


class RenameSpeakers(BaseModel):
    mapping: dict   # {"SPEAKER_00": "Zaal", ...}


@router.post("/{project}/speakers")
async def rename_speakers_ep(project: str, body: RenameSpeakers):
    """Rename speaker labels across the transcript."""
    project_dir = _project_dir(project)
    cut = _cut_json_path(project_dir)
    if not cut:
        raise HTTPException(404, "No transcript")
    from ..services.diarization import rename_speakers
    segs = rename_speakers(json.loads(cut.read_text()), body.mapping)
    cut.write_text(json.dumps(segs, indent=2), encoding="utf-8")
    return {"ok": True, "speakers": sorted({s["speaker"] for s in segs if s.get("speaker")})}


class SaveCuts(BaseModel):
    cuts: list


@router.post("/{project}/cuts")
async def save_cuts(project: str, body: SaveCuts):
    """Persist the cut enabled/disabled states (the review decisions)."""
    project_dir = _project_dir(project)
    sheet_file = _edit_sheet_path(project_dir)
    if not sheet_file:
        raise HTTPException(404, "No edit sheet")
    sheet = json.loads(sheet_file.read_text())
    sheet["cuts"] = body.cuts
    sheet_file.write_text(json.dumps(sheet, indent=2), encoding="utf-8")
    return {"ok": True}


class TeachTerm(BaseModel):
    wrong: str
    right: str


@router.post("/glossary")
async def teach_glossary(body: TeachTerm):
    """Add a brand correction so every future recording gets it right."""
    from ..services.glossary import add_safe_correction
    try:
        add_safe_correction(body.wrong, body.right)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True, "added": {body.wrong: body.right}}


@router.get("/{project}/video")
async def serve_input_video(project: str):
    """Serve the source recording for the in-page player."""
    project_dir = _project_dir(project)
    media = _find_input(project_dir)
    suffix = media.suffix.lower()
    types = {".mp4": "video/mp4", ".mov": "video/quicktime", ".mkv": "video/x-matroska",
             ".webm": "video/webm", ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4"}
    return FileResponse(str(media), media_type=types.get(suffix, "application/octet-stream"),
                        headers={"Accept-Ranges": "bytes"})


def _project_title(project_dir: Path) -> str:
    pj = project_dir / "project.json"
    if pj.exists():
        try:
            return json.loads(pj.read_text()).get("title", project_dir.name)
        except (ValueError, OSError):
            pass
    return project_dir.name


@router.get("/page", response_class=HTMLResponse)
async def page():
    html = STATIC_DIR / "studio.html"
    if not html.exists():
        raise HTTPException(404, "Studio page missing")
    return HTMLResponse(html.read_text(encoding="utf-8"))
