#!/usr/bin/env bash
# ZAO Recordings Studio - one command to set up and run the local app.
# First run installs into a local venv; later runs just start the server and
# open your browser. No Node, no Supabase, no cloud.
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
PORT="${PORT:-8000}"

# --- ffmpeg check (the one thing we can't install for you) ---
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required and was not found on your PATH."
  echo "  macOS:  brew install ffmpeg"
  echo "  Ubuntu: sudo apt install ffmpeg"
  exit 1
fi

# --- python venv + deps (only when missing) ---
if [ ! -d venv ]; then
  echo "First run: creating a Python environment (this takes a couple of minutes)..."
  python3 -m venv venv
  ./venv/bin/pip install --quiet --upgrade pip
  ./venv/bin/pip install --quiet -r backend/requirements.txt
  echo "Setup done."
fi

# install marker so we don't reinstall every run, but do catch a changed reqs file
if [ backend/requirements.txt -nt venv/.deps-installed ]; then
  echo "Updating dependencies..."
  ./venv/bin/pip install --quiet -r backend/requirements.txt
  touch venv/.deps-installed
fi

URL="http://localhost:${PORT}"
echo ""
echo "Starting ZAO Recordings Studio at ${URL}"
echo "Drag a recording into the page. Press Ctrl+C to stop."
echo ""

# open the browser shortly after the server comes up
( sleep 2; (command -v open >/dev/null && open "$URL") || (command -v xdg-open >/dev/null && xdg-open "$URL") || true ) &

exec ./venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port "${PORT}"
