"""Stage H: build the publishable artifacts for a recording.

Produces the bundle that lands in the zabalgames repo for a /recordings/N page:
  - the clean readable transcript (Markdown)
  - a recap entry (for data/recaps.json)
  - a recordings index entry (for recordings/index.json)
  - a page stub (recordings/N.md)

Writing them INTO zabalgames is a separate, repo-aware step (publish_via_pr) that
needs the repo checked out + push rights. build_bundle is pure + testable; it does
not touch any external repo.
"""

import json
import re
from pathlib import Path
from typing import Optional


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "untitled"


def transcript_filename(date: str, presenter: str, topic: str) -> str:
    """Match the zabalgames convention: YYYY-MM-DD-presenter-topic.md."""
    return f"{date}-{slugify(presenter)}-{slugify(topic)}.md"


def build_recap_entry(number: int, title: str, date: str, summary: str,
                      youtube_id: Optional[str] = None) -> dict:
    entry = {
        "id": number,
        "title": title,
        "date": date,
        "summary": summary.strip(),
    }
    if youtube_id:
        entry["youtube"] = youtube_id
    return entry


def build_index_entry(number: int, title: str, date: str, slug: str) -> dict:
    return {"id": number, "title": title, "date": date, "slug": slug, "path": f"/recordings/{number}"}


def build_page_md(number: int, title: str, date: str, readable_markdown: str,
                  youtube_id: Optional[str] = None, clips: Optional[list] = None) -> str:
    lines = [f"# Recording {number}: {title}", "", f"Date: {date}", ""]
    if youtube_id:
        lines += [f"Video: https://youtu.be/{youtube_id}", ""]
    if clips:
        lines += ["## Clips", ""]
        for c in clips:
            copy = c.get("copy") or {}
            title_line = copy.get("title") or c.get("base", "clip")
            lines.append(f"- {title_line}")
        lines.append("")
    lines += ["## Transcript", "", readable_markdown.strip(), ""]
    return "\n".join(lines)


def build_bundle(result: dict, number: int, date: str, presenter: str = "",
                 topic: str = "", youtube_id: Optional[str] = None,
                 out_dir: Optional[str] = None) -> dict:
    """Assemble the publish bundle from a pipeline result.

    `result` is the dict from recordings_pipeline.process_recording (needs at
    least title + readable_markdown; review_flags + clips optional).
    """
    title = result.get("title") or topic or "Recording"
    readable = result.get("readable_markdown", "")
    summary = _first_paragraph(readable)
    clips = result.get("clips") or []

    bundle = {
        "number": number,
        "date": date,
        "transcript_filename": transcript_filename(date, presenter or title, topic or title),
        "transcript_markdown": readable,
        "recap_entry": build_recap_entry(number, title, date, summary, youtube_id),
        "index_entry": build_index_entry(number, title, date, slugify(title)),
        "page_md": build_page_md(number, title, date, readable, youtube_id, clips),
    }

    if out_dir:
        out = Path(out_dir)
        (out / "transcripts").mkdir(parents=True, exist_ok=True)
        (out / "recordings").mkdir(parents=True, exist_ok=True)
        (out / "transcripts" / bundle["transcript_filename"]).write_text(readable, encoding="utf-8")
        (out / "recordings" / f"{number}.md").write_text(bundle["page_md"], encoding="utf-8")
        (out / f"recap-{number}.json").write_text(json.dumps(bundle["recap_entry"], indent=2), encoding="utf-8")
        (out / f"index-entry-{number}.json").write_text(json.dumps(bundle["index_entry"], indent=2), encoding="utf-8")
        bundle["output_dir"] = str(out)

    return bundle


def _first_paragraph(markdown: str) -> str:
    for block in markdown.split("\n\n"):
        b = block.strip()
        if b and not b.startswith("#"):
            return b
    return ""


def merge_into_index(index_path: Path, entry: dict) -> list:
    """Insert/replace an entry in a recordings index.json by id. Returns the list."""
    data = []
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text())
        except (ValueError, OSError):
            data = []
    data = [e for e in data if e.get("id") != entry["id"]]
    data.append(entry)
    data.sort(key=lambda e: e.get("id", 0))
    return data
