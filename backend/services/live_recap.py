"""End-of-stream recap: recap + chapters + suggested clips from the LIVE transcript.

When a live session wraps, you can get a recap straight from the words that
scrolled by - no need to wait for the VOD to download and re-transcribe. Reuses
the same recap generator as the finished-recording path and writes to the same
metadata/insights.json, so the result shows up in the editor either way.
"""

import json
from pathlib import Path
from typing import Callable, Optional


def _default_generator(segments, project_name):
    from .content_gen import generate_recap_and_clips
    return generate_recap_and_clips(segments, project_name=project_name)


def build_live_recap(project_dir: Path, project_name: str = "",
                     generator: Optional[Callable] = None) -> dict:
    """Generate a recap from the live transcript and persist it to insights.json.

    Raises ValueError if there is no live transcript yet.
    """
    project_dir = Path(project_dir)
    lt = project_dir / "live_transcript.json"
    segs = []
    if lt.exists():
        try:
            segs = json.loads(lt.read_text()).get("segments", [])
        except (ValueError, OSError):
            segs = []
    if not segs:
        raise ValueError("No live transcript yet - start the live transcript first")

    res = (generator or _default_generator)(segs, project_name or project_dir.name)
    insights = {
        "recap": res.get("recap", ""),
        "chapters": res.get("chapters", []),
        "quotes": res.get("quotes", []),
        "show_notes": res.get("show_notes", ""),
        "clips": res.get("clips", []),
        "source": "live-transcript",
    }
    (project_dir / "metadata").mkdir(parents=True, exist_ok=True)
    (project_dir / "metadata" / "insights.json").write_text(
        json.dumps(insights, indent=2), encoding="utf-8")
    return insights
