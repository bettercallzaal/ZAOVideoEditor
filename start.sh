#!/bin/bash
# ZAO Video Editor - Start Script
# Starts both backend (FastAPI) and frontend (Vite) servers

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Starting ZAO Video Editor..."
echo ""

# Create projects directory if needed
mkdir -p "$DIR/projects"

# Start backend
echo "Starting backend on http://localhost:8000..."
cd "$DIR"
source venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Start frontend
echo "Starting frontend on http://localhost:5173..."
cd "$DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "ZAO Video Editor is running!"
echo "  Frontend: http://localhost:5173"
echo "  Backend:  http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers."

# Handle shutdown
trap "echo 'Shutting down...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM

wait
