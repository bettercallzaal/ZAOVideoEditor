"""Distribution bundle: pack a finished recording into one zip to hand off.

Gathers everything postable for a project - the clips, their copy, the recap and
chapters, the social drafts, and the transcripts - plus a manifest, into a single
`exports/<name>-bundle.zip`. Tolerant: includes whatever exists, never fails on a
missing piece, so it works on a barely-processed project or a fully-finished one.
"""

import json
import zipfile
from pathlib import Path


def _read_json(p: Path):
    try:
        return json.loads(p.read_text())
    except (ValueError, OSError):
        return None


def _fmt_ts(sec) -> str:
    try:
        s = int(float(sec))
    except (TypeError, ValueError):
        return "0:00"
    return f"{s // 60}:{s % 60:02d}"


def _recap_md(insights: dict) -> str:
    lines = ["# Recap", "", (insights.get("recap") or "").strip(), ""]
    chapters = insights.get("chapters") or []
    if chapters:
        lines += ["## Chapters", ""]
        for c in chapters:
            lines.append(f"- [{_fmt_ts(c.get('start', 0))}] {c.get('title', '').strip()}")
        lines.append("")
    quotes = insights.get("quotes") or []
    if quotes:
        lines += ["## Quotes", ""]
        for q in quotes:
            text = q.get("text", q) if isinstance(q, dict) else q
            lines.append(f"> {str(text).strip()}")
        lines.append("")
    actions = insights.get("action_items") or insights.get("actions") or []
    if actions:
        lines += ["## Action items", ""]
        for a in actions:
            lines.append(f"- {str(a).strip()}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _posts_md(socials: dict) -> str:
    lines = ["# Social posts", ""]
    ep = socials.get("episode") or {}
    if ep:
        lines += ["## Episode", "", f"**Farcaster:** {ep.get('farcaster', '')}", "",
                  f"**X:** {ep.get('x', '')}", ""]
    clips = socials.get("clips") or []
    if clips:
        lines += ["## Clips", ""]
        for c in clips:
            post = c.get("post", c) if isinstance(c, dict) else c
            lines.append(f"- {str(post).strip()}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _clips_md(clip_copies: list) -> str:
    lines = ["# Clip copy", ""]
    for c in clip_copies:
        title = c.get("title", "").strip()
        caption = c.get("caption", "").strip()
        tags = c.get("hashtags") or c.get("tags") or []
        lines.append(f"## {title or 'Clip'}")
        if caption:
            lines.append(caption)
        if tags:
            lines.append(" ".join(t if t.startswith("#") else f"#{t}" for t in tags))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_bundle(project_dir: Path) -> dict:
    """Assemble exports/<name>-bundle.zip. Returns {zip, manifest, entries}."""
    project_dir = Path(project_dir)
    name = project_dir.name
    exports = project_dir / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    zip_path = exports / f"{name}-bundle.zip"

    info = _read_json(project_dir / "project.json") or {}
    tdir = project_dir / "transcripts"
    cdir = project_dir / "clips"
    mdir = project_dir / "metadata"

    file_entries = []  # (arcname, source path)
    readable = next(tdir.glob("*.readable.md"), None) if tdir.exists() else None
    if readable:
        file_entries.append(("transcript.md", readable))
    cutmd = next(tdir.glob("*.cut.md"), None) if tdir.exists() else None
    if cutmd:
        file_entries.append(("transcript-timestamped.md", cutmd))

    clip_copies = []
    clip_count = 0
    if cdir.exists():
        for mp4 in sorted(cdir.glob("*.mp4")):
            file_entries.append((f"clips/{mp4.name}", mp4))
            clip_count += 1
        for cj in sorted(cdir.glob("*.copy.json")):
            data = _read_json(cj)
            if data:
                clip_copies.append(data)

    text_entries = {}  # arcname -> text
    insights = _read_json(mdir / "insights.json") if mdir.exists() else None
    if insights:
        text_entries["recap.md"] = _recap_md(insights)
    socials = _read_json(mdir / "socials.json") if mdir.exists() else None
    if socials:
        text_entries["posts.md"] = _posts_md(socials)
    if clip_copies:
        text_entries["clip-copy.md"] = _clips_md(clip_copies)

    manifest = {
        "title": info.get("title", name),
        "project": name,
        "created_at": info.get("created_at", ""),
        "source": info.get("source", ""),
        "clips": clip_count,
        "has_recap": bool(insights),
        "has_posts": bool(socials),
        "has_transcript": bool(readable),
    }
    text_entries["manifest.json"] = json.dumps(manifest, indent=2)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for arcname, src in file_entries:
            z.write(src, arcname)
        for arcname, text in text_entries.items():
            z.writestr(arcname, text)

    entries = [a for a, _ in file_entries] + list(text_entries.keys())
    return {"zip": str(zip_path), "manifest": manifest, "entries": sorted(entries)}
