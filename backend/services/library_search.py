"""Cross-recording search: find a moment across every processed recording.

Scans each project's timestamped transcript (`*.cut.json`) for a phrase and
returns the matching lines with their timestamps, grouped by recording. Lets the
library answer "where did anyone talk about WaveWarZ" and jump straight to the
moment (and from there, clip it).
"""

import json
from pathlib import Path


def _project_meta(project_dir: Path) -> dict:
    pj = project_dir / "project.json"
    if pj.exists():
        try:
            info = json.loads(pj.read_text())
            return {"title": info.get("title", project_dir.name),
                    "created_at": info.get("created_at", "")}
        except (ValueError, OSError):
            pass
    return {"title": project_dir.name, "created_at": ""}


def _segments(project_dir: Path) -> list:
    cut = next((project_dir / "transcripts").glob("*.cut.json"), None) \
        if (project_dir / "transcripts").exists() else None
    if not cut:
        return []
    try:
        return json.loads(cut.read_text())
    except (ValueError, OSError):
        return []


def search_transcripts(projects_dir: Path, query: str, limit_per_project: int = 5,
                       max_results: int = 100) -> list:
    """Find segments matching `query` (case-insensitive substring) across all projects.

    Returns a list of {project, title, created_at, count, matches:[{start,end,text}]},
    newest recording first, only recordings with at least one hit.
    """
    q = (query or "").strip().lower()
    if not q or not projects_dir.exists():
        return []
    results = []
    total = 0
    for d in projects_dir.iterdir():
        if total >= max_results:
            break
        if not d.is_dir() or not (d / "project.json").exists():
            continue
        matches = []
        for seg in _segments(d):
            text = seg.get("text", "") or ""
            if q in text.lower():
                matches.append({
                    "start": round(float(seg.get("start", 0.0)), 1),
                    "end": round(float(seg.get("end", 0.0)), 1),
                    "text": text.strip(),
                })
                if len(matches) >= limit_per_project:
                    break
        if matches:
            meta = _project_meta(d)
            results.append({
                "project": d.name, "title": meta["title"],
                "created_at": meta["created_at"], "count": len(matches),
                "matches": matches,
            })
            total += len(matches)
    results.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return results
