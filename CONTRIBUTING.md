# Contributing

Thanks for helping build ZAO Video Editor.

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt        # runtime
pip install -r backend/requirements-dev.txt     # tests
cd frontend && npm install && cd ..
```

ffmpeg must be on your PATH. `yt-dlp` is optional (URL ingest).

## Before opening a PR

```bash
python -m pytest                 # backend tests
cd frontend && npm run build     # frontend must build
```

CI (`.github/workflows/ci.yml`) runs the same: backend byte-compile + pytest, and a frontend build. Lint runs non-blocking until the existing lint debt is cleared - new code should still lint clean (`cd frontend && npm run lint`).

## Conventions

- Backend: FastAPI routers under `backend/routers/`, logic in `backend/services/`. Validate every project name with `validate_project_name` / the `ProjectName` schema type before joining it onto a filesystem path. Long work goes through `services/task_manager` as a background task.
- Optional tools (ffmpeg extras, whisperx, yt-dlp, OpenCV) must be feature-detected via `services/tool_availability` and degrade gracefully when absent.
- Never write secrets to disk. `.env` is gitignored; document new env vars in `.env.example`.
- Frontend: React function components, Tailwind classes, the shared `api/client.js` for all requests.

## Tests

Tests live in `backend/tests/`, mock `subprocess` and the LLM client (no network, no ffmpeg, no GPU), and run in well under a second. Add a test with any new service-level logic.
