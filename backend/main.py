import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from pathlib import Path

from .routers import projects, assembly, transcription, transcript, captions, metadata, export, speakers, fillers, clips, silence, ai_tools, youtube, content, batch, templates, pipeline, ingest, recordings, studio

app = FastAPI(title="ZAO Video Editor", version="0.1.0")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Log full error details but return sanitized message to client."""
    tb = traceback.format_exc()
    print(f"ERROR: {exc}\n{tb}")
    # Don't leak internal details (ffmpeg stderr, file paths, etc.)
    msg = str(exc)
    if any(kw in msg.lower() for kw in ["stderr", "traceback", "/users/", "/home/", "errno"]):
        msg = "An internal error occurred. Check server logs for details."
    return JSONResponse(
        status_code=500,
        content={"detail": msg},
    )

# Optional access password for shared/public deploys (no-op when unset).
from .auth import AccessPasswordMiddleware
app.add_middleware(AccessPasswordMiddleware)

# CORS. Defaults to local dev origins; override with STUDIO_CORS_ORIGINS
# (comma-separated, or "*") for a deployed instance.
import os as _os
_cors = _os.environ.get("STUDIO_CORS_ORIGINS", "").strip()
_origins = ["http://localhost:5173", "http://localhost:3000", "http://localhost:8000"]
if _cors:
    _origins = ["*"] if _cors == "*" else [o.strip() for o in _cors.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(projects.router)
app.include_router(assembly.router)
app.include_router(transcription.router)
app.include_router(transcript.router)
app.include_router(captions.router)
app.include_router(metadata.router)
app.include_router(export.router)
app.include_router(speakers.router)
app.include_router(fillers.router)
app.include_router(clips.router)
app.include_router(silence.router)
app.include_router(ai_tools.router)
app.include_router(youtube.router)
app.include_router(content.router)
app.include_router(batch.router)
app.include_router(templates.router)
app.include_router(pipeline.router)
app.include_router(ingest.router)
app.include_router(recordings.router)
app.include_router(studio.router)

# Serve video files from projects directory
PROJECTS_DIR = Path(__file__).parent.parent / "projects"
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", response_class=HTMLResponse)
async def studio_home():
    """The one-command Studio app - drag a recording, get transcripts + a trim."""
    page = STATIC_DIR / "studio.html"
    if page.exists():
        return HTMLResponse(page.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>ZAO Video Editor</h1><p>Studio page not found.</p>")


@app.get("/api/serve-video/{project_name}/{subpath:path}")
async def serve_video(project_name: str, subpath: str):
    """Serve video files for the player."""
    from fastapi import HTTPException
    from .services.project_utils import validate_project_name, is_within
    validate_project_name(project_name)
    file_path = (PROJECTS_DIR / project_name / subpath).resolve()
    # Prevent path traversal (relative_to containment, not a string-prefix check
    # which would allow a sibling like /projects-evil to pass)
    if not is_within(file_path, PROJECTS_DIR):
        raise HTTPException(403, "Access denied")
    if not file_path.exists():
        raise HTTPException(404, "File not found")
    suffix = file_path.suffix.lower()
    media_types = {
        ".mp4": "video/mp4", ".mov": "video/quicktime",
        ".mkv": "video/x-matroska", ".webm": "video/webm",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    }
    return FileResponse(
        str(file_path),
        media_type=media_types.get(suffix, "application/octet-stream"),
        headers={"Accept-Ranges": "bytes"},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}


@app.get("/api/tools")
async def get_tools():
    """Return which optional tools are installed."""
    from .services.tool_availability import get_available_tools
    return get_available_tools()


@app.get("/api/storage")
async def all_storage():
    """Get disk usage across all projects."""
    from .services.storage import get_all_projects_storage
    return get_all_projects_storage()


# Task status polling
from .services import task_manager as tm


@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Poll a background task for status."""
    task = tm.get_task(task_id)
    if not task:
        return JSONResponse(status_code=404, content={"detail": "Task not found"})
    return tm.task_to_dict(task)


@app.get("/api/tasks/project/{project_name}")
async def get_project_tasks(project_name: str):
    """Get all tasks for a project."""
    tasks = tm.get_project_tasks(project_name)
    return [tm.task_to_dict(t) for t in tasks]
