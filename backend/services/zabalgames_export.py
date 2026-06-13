"""Export a processed recording into the ZABAL Gamez repo's exact formats.

The team's #1 pain is hand-building /recordings/N.html pages. The fix that "wins
forever" (their words): emit the recap as DATA - a recaps.json block - so the
page renders from data, plus the transcript .md the archive + page link expect.
This module produces those, from the Studio's transcript + insights.

Field list confirmed by the ZABAL Gamez team:
  recaps block: date, presenter, track, summary, topics, takeaways, chapters,
                youtube, transcript
Brand rules (enforced): no emojis, no em dashes, exact casing.
"""

import json
import re
from pathlib import Path
from typing import Optional


TRANSCRIPT_DIR = "data/streams/zabal-games-workshops/raw/transcripts"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "recording"


def _clean(text: str) -> str:
    """Strip em dashes / decorative unicode per brand rules."""
    return (text or "").replace("—", "-").replace("–", "-").replace("•", "-")


def youtube_id(url_or_id: str) -> str:
    if not url_or_id:
        return ""
    m = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})", url_or_id)
    return m.group(1) if m else url_or_id


def transcript_filename(date: str, presenter: str, topic: str) -> str:
    return f"{date}-{_slug(presenter)}-{_slug(topic)}.md"


def transcript_md(segments: list, title: str, date: str, presenter: str,
                  track: str = "", youtube: str = "") -> str:
    """The clean transcript .md with frontmatter for the archive + page link."""
    fm = [
        "---",
        f"title: {title}",
        f"date: {date}",
        f"presenter: {presenter}",
    ]
    if track:
        fm.append(f"track: {track}")
    if youtube:
        fm.append(f"youtube: {youtube_id(youtube)}")
    fm.append("---")
    lines = ["\n".join(fm), "", f"# {title}", ""]
    for seg in segments:
        spk = seg.get("speaker")
        text = _clean((seg.get("text") or "").strip())
        if not text:
            continue
        lines.append(f"**{spk}:** {text}" if spk else text)
        lines.append("")
    return "\n".join(lines)


def recaps_block(number: int, title: str, date: str, presenter: str,
                 insights: dict, transcript_path: str, track: str = "",
                 youtube: str = "") -> dict:
    """The ready-to-paste recaps.json entry. Fields per the ZABAL Gamez spec."""
    chapters = [
        {"time": c.get("time", ""), "title": _clean(c.get("title", ""))}
        for c in insights.get("chapters", []) if c.get("title")
    ]
    topics = [c["title"] for c in chapters][:12]
    takeaways = [_clean(q.get("text", "")) for q in insights.get("quotes", []) if q.get("text")][:6]
    summary = _clean(insights.get("recap", "")).strip()

    block = {
        "id": number,
        "date": date,
        "presenter": presenter,
        "track": track,
        "title": title,
        "summary": summary,
        "topics": topics,
        "takeaways": takeaways,
        "chapters": chapters,
        "youtube": youtube_id(youtube),
        "transcript": transcript_path,
    }
    return block


def build_export(number: int, title: str, date: str, presenter: str,
                 segments: list, insights: dict, track: str = "",
                 youtube: str = "", out_dir: Optional[Path] = None) -> dict:
    """Assemble the full ZABAL Gamez export bundle for a recording."""
    fname = transcript_filename(date, presenter, title)
    transcript_rel = f"{TRANSCRIPT_DIR}/{fname}"
    md = transcript_md(segments, title, date, presenter, track, youtube)
    block = recaps_block(number, title, date, presenter, insights, transcript_rel, track, youtube)

    bundle = {
        "recaps_block": block,
        "transcript_path": transcript_rel,
        "transcript_md": md,
        "instructions": (
            f"1. Save the transcript to {transcript_rel}\n"
            f"2. Add the recaps_block to data/recaps.json (the /recordings/{number} page renders from it)\n"
            f"3. Rebuild the index (scripts/build-recordings-index.mjs); push to Bonfire if desired."
        ),
    }
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / fname).write_text(md, encoding="utf-8")
        (out / f"recaps-block-{number}.json").write_text(json.dumps(block, indent=2), encoding="utf-8")
        bundle["output_dir"] = str(out)
        bundle["files"] = {"transcript": fname, "recaps_block": f"recaps-block-{number}.json"}
    return bundle
