# ZAO Recordings Studio - production image.
# Bundles Python + ffmpeg + yt-dlp + the app. Whisper models download on first
# transcription into /models (mount a volume to persist them across restarts).
FROM python:3.11-slim

# ffmpeg for all media work; git/curl for optional installs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first (layer cache), then the optional publish/ingest extras.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt \
    && pip install --no-cache-dir yt-dlp requests-oauthlib requests

COPY backend backend
COPY scripts scripts

# Persist downloaded Whisper models + project data outside the image.
ENV HF_HOME=/models XDG_CACHE_HOME=/models
RUN mkdir -p /app/projects /models

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
