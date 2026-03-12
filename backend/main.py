import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path

from .routers import projects, assembly, transcription, transcript, captions, metadata, export

app = FastAPI(title="ZAO Video Editor", version="0.1.0")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Return detailed error messages instead of generic 500."""
    tb = traceback.format_exc()
    print(f"ERROR: {exc}\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
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

# Serve video files from projects directory
PROJECTS_DIR = Path(__file__).parent.parent / "projects"


@app.get("/api/serve-video/{project_name}/{subpath:path}")
async def serve_video(project_name: str, subpath: str):
    """Serve video files for the player."""
    file_path = PROJECTS_DIR / project_name / subpath
    if not file_path.exists():
        return {"error": "File not found"}
    return FileResponse(
        str(file_path),
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


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
