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


import os as _os
_MAX_UPLOAD_BYTES = int(float(_os.environ.get("STUDIO_MAX_UPLOAD_GB", "10")) * 1024 * 1024 * 1024)


async def _save_upload(file, dest: Path):
    """Stream an upload to disk, enforcing the configured size cap."""
    total = 0
    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > _MAX_UPLOAD_BYTES:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"File too large (limit {_MAX_UPLOAD_BYTES // (1024**3)} GB)")
            f.write(chunk)


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
                speakers: bool, quality: str = "fast", captions_url: str = ""):
    result = rp.process_recording(
        media, title=title, quality=quality, engine="auto",
        out_dir=str(project_dir / "transcripts"), readable_llm=True,
        detect_speakers=speakers, captions_url=captions_url or None,
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
    await _save_upload(file, dest)

    task_id = tm.create_task(name, "studio_process")
    tm.run_in_background(task_id, _do_process, project_dir, str(dest), disp, speakers, quality)
    return {"project": name, "task_id": task_id}


def _do_ingest_process(task_id: str, project_dir: Path, url: str, title: str,
                       speakers: bool, quality: str = "fast", use_captions: bool = False):
    from ..services import ingest_service
    tm.update_task(task_id, progress=2, message="Fetching from link...")
    ingest_service.download_to_project(
        url, project_dir,
        on_progress=lambda pct, msg: tm.update_task(task_id, progress=min(int(pct * 0.4), 40), message=msg),
    )
    media = _find_input(project_dir)
    # When asked, use the YouTube VOD's own captions (fast) instead of Whisper.
    cap = url if (use_captions and ("youtube.com" in url or "youtu.be" in url)) else ""
    return _do_process(task_id, project_dir, str(media), title, speakers, quality, captions_url=cap)


@router.post("/ingest")
async def ingest_link(url: str = Form(...), title: str = Form(""),
                      speakers: bool = Form(False), quality: str = Form("fast"),
                      use_captions: bool = Form(False)):
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
    tm.run_in_background(task_id, _do_ingest_process, project_dir, url, disp, speakers, quality, use_captions)
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
        await _save_upload(file, dest)
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


@router.get("/projects")
async def list_projects():
    """The recordings library - every project, newest first."""
    if not PROJECTS_DIR.exists():
        return []
    out = []
    for d in PROJECTS_DIR.iterdir():
        if not d.is_dir() or not (d / "project.json").exists():
            continue
        try:
            info = json.loads((d / "project.json").read_text())
        except (ValueError, OSError):
            info = {}
        has_transcript = bool(next((d / "transcripts").glob("*.cut.json"), None)) if (d / "transcripts").exists() else False
        out.append({
            "project": d.name,
            "title": info.get("title", d.name),
            "created_at": info.get("created_at", ""),
            "source": info.get("source", ""),
            "ready": has_transcript,
            "has_trimmed": (d / "processing" / "trimmed.mp4").exists(),
            "clips": len(list((d / "clips").glob("*.mp4"))) if (d / "clips").exists() else 0,
        })
    out.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return out


@router.get("/search")
async def search_library(q: str = "", limit: int = 5):
    """Find a phrase across every processed recording, with timestamps."""
    from ..services import library_search
    return library_search.search_transcripts(
        PROJECTS_DIR, q, limit_per_project=max(1, min(limit, 25)))


def _do_insights(task_id: str, project_dir: Path):
    """Recap + chapters + quotes + action items from the transcript (one LLM call)."""
    from ..services.content_gen import generate_recap_and_clips
    segs = json.loads(_cut_json_path(project_dir).read_text())
    tm.update_task(task_id, progress=40, message="Reading the recording...")
    try:
        res = generate_recap_and_clips(segs, project_name=_project_title(project_dir))
    except Exception as e:
        raise RuntimeError(f"Insights need an LLM (claude CLI or OPENAI/GROQ key): {e}")
    insights = {
        "recap": res.get("recap", ""),
        "chapters": res.get("chapters", []),
        "quotes": res.get("quotes", []),
        "show_notes": res.get("show_notes", ""),
    }
    (project_dir / "metadata").mkdir(parents=True, exist_ok=True)
    (project_dir / "metadata" / "insights.json").write_text(json.dumps(insights, indent=2), encoding="utf-8")
    tm.update_task(task_id, progress=95, message="Insights ready")
    return insights


@router.post("/{project}/insights")
async def make_insights(project: str):
    """Extract a recap, chapters, and key quotes from the recording."""
    project_dir = _project_dir(project)
    existing = tm.get_active_task(project, "studio_insights")
    if existing:
        return tm.task_to_dict(existing)
    task_id = tm.create_task(project, "studio_insights")
    tm.run_in_background(task_id, _do_insights, project_dir)
    return {"task_id": task_id}


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


@router.get("/publishers")
async def publishers_status():
    """Which publish targets are configured (so the UI can show/hide buttons)."""
    from ..services import publishers
    return publishers.status()


class PostText(BaseModel):
    text: str


@router.post("/{project}/publish/farcaster")
async def publish_farcaster(project: str, body: PostText):
    _project_dir(project)
    from ..services import publishers
    try:
        return publishers.post_farcaster(body.text)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.post("/{project}/publish/x")
async def publish_x(project: str, body: PostText):
    _project_dir(project)
    from ..services import publishers
    try:
        return publishers.post_x(body.text)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


class YouTubePublish(BaseModel):
    title: str = ""
    description: str = ""
    privacy: str = "unlisted"


def _do_youtube(task_id: str, project_dir: Path, title: str, description: str, privacy: str):
    from ..services import publishers
    trimmed = project_dir / "processing" / "trimmed.mp4"
    video = str(trimmed) if trimmed.exists() else str(_find_input(project_dir))
    tm.update_task(task_id, progress=20, message="Uploading to YouTube...")
    res = publishers.upload_youtube(video, title or _project_title(project_dir), description, privacy=privacy)
    tm.update_task(task_id, progress=95, message="Uploaded")
    return res


@router.post("/{project}/publish/youtube")
async def publish_youtube(project: str, body: YouTubePublish):
    project_dir = _project_dir(project)
    from ..services import publishers
    if not publishers.youtube_configured():
        raise HTTPException(400, "YouTube not configured: place a Google OAuth credentials.json in backend/")
    existing = tm.get_active_task(project, "studio_youtube")
    if existing:
        return tm.task_to_dict(existing)
    task_id = tm.create_task(project, "studio_youtube")
    tm.run_in_background(task_id, _do_youtube, project_dir, body.title, body.description, body.privacy)
    return {"task_id": task_id}


@router.get("/bonfire-status")
async def bonfire_status():
    """Whether Bonfire memory is configured (controls the opt-in button)."""
    from ..services import bonfire
    return {"configured": bonfire.configured()}


@router.post("/{project}/bonfire")
async def push_bonfire(project: str):
    """OPT-IN: post this recording's recap to the ZAO Bonfire knowledge graph.

    Only fires on an explicit request. Requires that key moments were extracted
    first (uses the saved recap). Never runs automatically.
    """
    project_dir = _project_dir(project)
    from ..services import bonfire
    insights_file = project_dir / "metadata" / "insights.json"
    if not insights_file.exists():
        raise HTTPException(400, "Extract key moments first - there is no recap to save yet")
    insights = json.loads(insights_file.read_text())
    date = ""
    pj = project_dir / "project.json"
    if pj.exists():
        try:
            date = (json.loads(pj.read_text()).get("created_at", "") or "")[:10]
        except (ValueError, OSError):
            pass
    try:
        return bonfire.post_recording(_project_title(project_dir), insights, date=date)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


class ZabalExport(BaseModel):
    number: int = 0
    presenter: str = ""
    handle: str = ""
    org: str = ""
    track: str = "builder"
    type: str = "workshop"
    youtube: str = ""
    episode: int = 0
    write_to_repo: bool = False


@router.post("/{project}/zabal-export")
async def zabal_export(project: str, body: ZabalExport):
    """Emit the ZABAL Gamez repo formats: a data/recaps.json entry + transcript .md.

    Requires that key moments were extracted (the recap/chapters drive the entry).
    """
    project_dir = _project_dir(project)
    from ..services import zabalgames_export as zx
    segments = _load_segments(project_dir)
    insights_file = project_dir / "metadata" / "insights.json"
    if not insights_file.exists():
        raise HTTPException(400, "Extract key moments first - the recap drives the recaps entry")
    insights = json.loads(insights_file.read_text())

    title = _project_title(project_dir)
    date = ""
    pj = project_dir / "project.json"
    if pj.exists():
        try:
            date = (json.loads(pj.read_text()).get("created_at", "") or "")[:10]
        except (ValueError, OSError):
            pass

    opts = {
        "title": title, "date": date or "0000-00-00",
        "presenter": body.presenter or title, "handle": body.handle, "org": body.org,
        "track": body.track, "type": body.type, "youtube": body.youtube,
        "number": body.number, "episode": body.episode or None,
    }
    bundle = zx.build_export(opts, segments, insights, out_dir=project_dir / "zabal")

    # If a local zabalgames checkout is configured, also write into it (for review).
    repo = _os.environ.get("STUDIO_ZABALGAMES_PATH", "").strip()
    if body.write_to_repo and repo:
        try:
            bundle["repo_write"] = zx.write_into_repo(repo, bundle)
        except (RuntimeError, OSError) as e:
            bundle["repo_write"] = {"error": str(e)}
    elif body.write_to_repo:
        bundle["repo_write"] = {"error": "Set STUDIO_ZABALGAMES_PATH to a local zabalgames checkout"}
    return bundle


@router.get("/sessions")
async def sessions():
    """The ZABAL Gamez session lineup (from workshop-leads.json) for the casts picker."""
    from ..services import live_casts
    return live_casts.list_sessions()


class DayOfCasts(BaseModel):
    name: str = ""
    org: str = ""
    topic: str = ""
    time: str = ""
    luma: str = ""
    handle: str = ""
    session_id: str = ""


@router.post("/casts/day-of")
async def casts_day_of(body: DayOfCasts):
    """Generate the 15-min-warning + live-now casts for a session."""
    from ..services import live_casts
    name, org, topic, handle, luma = body.name, body.org, body.topic, body.handle, body.luma
    if body.session_id:
        for s in live_casts.list_sessions():
            if s["id"] == body.session_id:
                name = name or s["name"]
                org = org or s["org"]
                topic = topic or s["topic"]
                handle = handle or s["handle"]
                luma = luma or s["luma"]
                break
    if not name:
        raise HTTPException(422, "A session name (or session_id) is required")
    return live_casts.day_of_casts(name, org, topic, body.time, luma, handle)


# --- Live clip-marking ---------------------------------------------------
# Mark hot moments while the stream is running; each mark stores its
# seconds-from-start. After the stream, attach the VOD to the same project and
# the marks become clip ranges around each moment.

class LiveStart(BaseModel):
    title: str = ""


@router.post("/live/start")
async def live_start(body: LiveStart):
    """Start a live session: create a project and stamp the wall-clock start."""
    from ..services import live_marks
    import time as _t
    disp = (body.title or "live session").strip() or "live session"
    name = _slug(disp)
    project_dir = _make_project(name, disp, "studio-live")
    state = live_marks.start_session(project_dir, started_at=_t.time())
    return {"project": name, "started_at": state["started_at"], "marks": []}


class LiveMark(BaseModel):
    note: str = ""
    at: float | None = None


@router.post("/{project}/live/mark")
async def live_mark(project: str, body: LiveMark):
    """Mark a hot moment. Uses server time unless `at` (seconds-from-start) is given."""
    from ..services import live_marks
    import time as _t
    project_dir = _project_dir(project)
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")
    mark = live_marks.add_mark(project_dir, note=body.note, now=_t.time(), at=body.at)
    state = live_marks.get_state(project_dir)
    return {"mark": mark, "count": len(state["marks"]), "marks": state["marks"]}


@router.get("/{project}/marks")
async def live_marks_list(project: str):
    """The marks recorded for a project."""
    from ..services import live_marks
    project_dir = _project_dir(project)
    state = live_marks.get_state(project_dir)
    return {"started_at": state.get("started_at"), "marks": state.get("marks", []),
            "count": len(state.get("marks", []))}


def _do_live_vod(task_id: str, project_dir: Path, url: str, title: str,
                 quality: str, use_captions: bool):
    """Pull the VOD into an EXISTING live project, then run the pipeline."""
    from ..services import ingest_service
    tm.update_task(task_id, progress=2, message="Fetching the VOD...")
    ingest_service.download_to_project(
        url, project_dir,
        on_progress=lambda pct, msg: tm.update_task(task_id, progress=min(int(pct * 0.4), 40), message=msg),
    )
    media = _find_input(project_dir)
    cap = url if (use_captions and ("youtube.com" in url or "youtu.be" in url)) else ""
    return _do_process(task_id, project_dir, str(media), title, False, quality, captions_url=cap)


class LiveVod(BaseModel):
    url: str
    quality: str = "fast"
    use_captions: bool = False


@router.post("/{project}/live/vod")
async def live_vod(project: str, body: LiveVod):
    """Attach the recorded VOD to a live project and process it (so marks can become clips)."""
    from ..services import ingest_service
    project_dir = _project_dir(project)
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")
    if not ingest_service.yt_dlp_available():
        raise HTTPException(400, "yt-dlp is not installed - run: pip install yt-dlp")
    if not (body.url.startswith("http://") or body.url.startswith("https://")):
        raise HTTPException(422, "Provide a valid http(s) URL")
    title = project_dir.name
    pj = project_dir / "project.json"
    if pj.exists():
        try:
            title = json.loads(pj.read_text()).get("title", title)
        except (ValueError, OSError):
            pass
    task_id = tm.create_task(project, "studio_process")
    tm.run_in_background(task_id, _do_live_vod, project_dir, body.url, title,
                         body.quality, body.use_captions)
    return {"task_id": task_id}


def _master_duration(master: Path) -> float:
    try:
        from ..services.ffmpeg_service import get_video_info
        info = get_video_info(str(master))
        return float(info.get("format", {}).get("duration", 0) or 0)
    except Exception:
        return 0.0


def _do_clips_from_marks(task_id: str, project_dir: Path, pre: float, post: float,
                         offset: float, aspects: list):
    from ..services import recordings_export as rx
    from ..services import live_marks
    state = live_marks.get_state(project_dir)
    marks = state.get("marks", [])
    master = project_dir / "processing" / "trimmed.mp4"
    if not master.exists():
        master = Path(_find_input(project_dir))
    tm.update_task(task_id, progress=10, message="Turning marks into clip ranges...")
    duration = _master_duration(master)
    highlights = live_marks.marks_to_highlights(marks, duration, pre=pre, post=post, offset=offset)
    if not highlights:
        return {"rendered": False, "reason": "No marks to clip", "plan": []}
    try:
        segments = _load_segments(project_dir)
    except HTTPException:
        segments = []
    tm.update_task(task_id, progress=25, message=f"Rendering {len(highlights)} marked clips...")
    res = rx.render_clips(
        str(master), segments, project_dir / "clips",
        highlights=highlights, aspects=aspects, project_name=project_dir.name,
    )
    tm.update_task(task_id, progress=95, message="Marked clips ready")
    return res


class ClipsFromMarks(BaseModel):
    pre: float = 20.0
    post: float = 40.0
    offset: float = 0.0
    aspects: str = "9:16"


@router.post("/{project}/clips-from-marks")
async def clips_from_marks(project: str, body: ClipsFromMarks):
    """Render a clip around each live mark, in the requested aspect ratios."""
    project_dir = _project_dir(project)
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")
    try:
        _find_input(project_dir)
    except HTTPException:
        raise HTTPException(409, "No VOD attached yet - POST the recording to /live/vod first")
    asp = [a.strip() for a in body.aspects.split(",") if a.strip()] or ["9:16"]
    existing = tm.get_active_task(project, "studio_clips")
    if existing:
        return tm.task_to_dict(existing)
    task_id = tm.create_task(project, "studio_clips")
    tm.run_in_background(task_id, _do_clips_from_marks, project_dir,
                         body.pre, body.post, body.offset, asp)
    return {"task_id": task_id}


# --- Live real-time transcription ---------------------------------------
# The browser records the stream's audio in short self-contained clips and
# POSTs them one at a time; each is transcribed, rebased to its offset, brand-
# corrected, and appended to a rolling live transcript.

@router.post("/{project}/live/audio-chunk")
async def live_audio_chunk(project: str, audio: UploadFile = File(...),
                           offset: float = Form(0.0), quality: str = Form("fast")):
    """Transcribe one audio clip and append it to the live transcript."""
    from ..services import live_transcribe
    project_dir = _project_dir(project)
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")
    chunks = project_dir / "live_chunks"
    chunks.mkdir(parents=True, exist_ok=True)
    ext = Path(audio.filename or "chunk.webm").suffix.lower() or ".webm"
    dest = chunks / f"chunk_{int(offset)}{ext}"
    await _save_upload(audio, dest)
    try:
        res = live_transcribe.append_chunk(project_dir, str(dest), offset=offset, quality=quality)
    except Exception as e:
        raise HTTPException(500, f"Transcription failed: {e}")
    return res


@router.get("/{project}/live/transcript")
async def live_transcript(project: str):
    """The rolling live transcript accumulated from chunks."""
    from ..services import live_transcribe
    project_dir = _project_dir(project)
    return live_transcribe.get_live_transcript(project_dir)


@router.get("/{project}/live/suggested-marks")
async def live_suggested_marks(project: str):
    """Suggest clippable moments from the live transcript (host accepts with one tap)."""
    from ..services import live_transcribe, auto_marks
    project_dir = _project_dir(project)
    segs = live_transcribe.get_live_transcript(project_dir).get("segments", [])
    return {"suggestions": auto_marks.suggest_marks(segs)}


@router.get("/page", response_class=HTMLResponse)
async def page():
    html = STATIC_DIR / "studio.html"
    if not html.exists():
        raise HTTPException(404, "Studio page missing")
    return HTMLResponse(html.read_text(encoding="utf-8"))
