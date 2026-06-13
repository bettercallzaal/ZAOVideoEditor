"""Live clip-marking: flag hot moments while a stream runs.

Start a live session (records the wall-clock start), then hit "mark" whenever
something clippable happens - each mark stores its seconds-from-start. After the
stream, ingest the VOD into the same project and the marks become clip ranges
(a window around each mark). Bridges "the livestream is happening" to the clip
pipeline.
"""

import json
import time
from pathlib import Path
from typing import Optional

MARKS_FILE = "marks.json"


def _path(project_dir: Path) -> Path:
    return project_dir / MARKS_FILE


def start_session(project_dir: Path, started_at: Optional[float] = None) -> dict:
    state = {"started_at": started_at if started_at is not None else time.time(), "marks": []}
    _path(project_dir).write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def _load(project_dir: Path) -> dict:
    p = _path(project_dir)
    if not p.exists():
        return {"started_at": None, "marks": []}
    try:
        return json.loads(p.read_text())
    except (ValueError, OSError):
        return {"started_at": None, "marks": []}


def add_mark(project_dir: Path, note: str = "", now: Optional[float] = None,
             at: Optional[float] = None) -> dict:
    """Add a mark. `at` (explicit seconds-from-start) wins; else compute from now."""
    state = _load(project_dir)
    if state.get("started_at") is None and at is None:
        state["started_at"] = now if now is not None else time.time()
    if at is None:
        at = max(0.0, (now if now is not None else time.time()) - state["started_at"])
    mark = {"at": round(float(at), 1), "note": (note or "").strip()}
    state["marks"].append(mark)
    state["marks"].sort(key=lambda m: m["at"])
    _path(project_dir).write_text(json.dumps(state, indent=2), encoding="utf-8")
    return mark


def get_state(project_dir: Path) -> dict:
    return _load(project_dir)


def marks_to_highlights(marks: list, duration: float, pre: float = 20.0,
                        post: float = 40.0, offset: float = 0.0) -> list:
    """Turn marks into clip ranges: [mark-pre, mark+post], clamped to the video.

    offset adjusts for drift between when "start" was hit and the VOD's t=0
    (positive = the VOD started after you hit start).
    """
    highlights = []
    for i, m in enumerate(marks):
        center = m["at"] + offset
        start = max(0.0, center - pre)
        end = min(duration, center + post) if duration else center + post
        if end - start < 2:
            continue
        highlights.append({
            "start": round(start, 1), "end": round(end, 1),
            "duration": round(end - start, 1),
            "title": m.get("note") or f"Marked moment {i + 1}",
            "source": "live-mark",
        })
    return highlights
