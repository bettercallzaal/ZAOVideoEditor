"""Export a processed recording into the ZAODEVZ/zabalgames repo's exact formats.

The team's #1 pain is hand-building /recordings/N.html; the fix that "wins forever"
is emitting the recap as DATA - a data/recaps.json entry - so the page renders from
it. This module produces that entry + the clean transcript .md, matching the real
schemas in github.com/ZAODEVZ/zabalgames (verified 2026-06-13).

recaps.json entry fields (only emit links/files that exist):
  date, type, title, presenter, handle, org, track, format, thumbnail, summary,
  topics[], recording, youtube, page, transcript, link, link_label, takeaways[],
  share_topics[], okd
Brand rules enforced: no emojis, no em dashes, exact casing.
"""

import json
import re
from pathlib import Path
from typing import Optional

TRANSCRIPT_DIR = "data/streams/zabal-games-workshops/raw/transcripts"
SHOW = "ZABAL Gamez Workshops"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "recording"


def _clean(text: str) -> str:
    return (text or "").replace("—", "-").replace("–", "-").replace("•", "-")


def youtube_id(url_or_id: str) -> str:
    if not url_or_id:
        return ""
    m = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})", url_or_id)
    return m.group(1) if m else url_or_id


def transcript_filename(date: str, presenter: str, topic: str) -> str:
    return f"{date}-{_slug(presenter)}-{_slug(topic)}.md"


def _share_topics(title: str, topics: list) -> list:
    """Natural 'I'm watching ...' phrases for the randomized share buttons."""
    out = [f"{title}"]
    for t in topics[:3]:
        out.append(t)
    return [_clean(s) for s in out if s][:4]


def transcript_md(segments: list, title: str, date_iso: str, presenter: str,
                  track: str = "", youtube: str = "", episode: Optional[int] = None,
                  thumbnail: str = "") -> str:
    """Clean transcript .md with frontmatter matching the zabalgames shape."""
    fm = ["---", f"title: {title}", f"show: {SHOW}"]
    if episode:
        fm.append(f"episode: {episode}")
    fm += [f"guest: {presenter}", "host: Zaal", f"date: {date_iso}",
           "format: video-livestream-workshop"]
    if thumbnail:
        fm.append(f"thumbnail: {thumbnail}")
    fm.append("language: en")
    if track:
        fm.append(f"track: {track}")
    if youtube:
        fm.append(f"youtube: https://youtu.be/{youtube_id(youtube)}")
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


def recaps_entry(opts: dict, insights: dict, transcript_path: str) -> dict:
    """The data/recaps.json entry. Omits optional fields that are empty."""
    chapters = [c.get("title", "") for c in insights.get("chapters", []) if c.get("title")]
    topics = [_clean(t) for t in chapters][:8] or [_clean(opts.get("title", ""))]
    takeaways = [_clean(q.get("text", "")) for q in insights.get("quotes", []) if q.get("text")][:6]
    summary = _clean(insights.get("recap", "")).strip()

    entry = {
        "date": opts.get("date", ""),
        "type": opts.get("type", "workshop"),
        "title": opts.get("title", ""),
        "presenter": opts.get("presenter", ""),
        "track": opts.get("track", "builder"),
        "format": opts.get("format", "livestreamed and recorded"),
        "summary": summary,
        "topics": topics,
        "takeaways": takeaways,
        "share_topics": _share_topics(opts.get("title", ""), topics),
        "transcript": transcript_path,
    }
    # optional fields - only include when present (per the recaps.json _note)
    for k in ("handle", "org", "thumbnail", "recording", "link", "link_label", "okd"):
        if opts.get(k):
            entry[k] = opts[k]
    if opts.get("number"):
        entry["page"] = f"/recordings/{opts['number']}"
    if opts.get("youtube"):
        entry["youtube"] = f"https://youtu.be/{youtube_id(opts['youtube'])}"
    return entry


def build_export(opts: dict, segments: list, insights: dict,
                 out_dir: Optional[Path] = None) -> dict:
    """opts: title, date, presenter, track, type, handle, org, youtube, number,
    episode, thumbnail, recording, link, link_label, okd."""
    date = opts.get("date", "0000-00-00")
    date_iso = f"{date}T00:00:00.000Z" if re.match(r"^\d{4}-\d{2}-\d{2}$", date) else date
    fname = transcript_filename(date, opts.get("presenter", ""), opts.get("title", ""))
    transcript_rel = f"{TRANSCRIPT_DIR}/{fname}"

    md = transcript_md(segments, opts.get("title", ""), date_iso, opts.get("presenter", ""),
                       opts.get("track", ""), opts.get("youtube", ""),
                       opts.get("episode"), opts.get("thumbnail", ""))
    entry = recaps_entry(opts, insights, transcript_rel)

    bundle = {
        "recaps_entry": entry,
        "transcript_path": transcript_rel,
        "transcript_md": md,
        "instructions": (
            f"1. Save the transcript to {transcript_rel}\n"
            f"2. Add the recaps_entry to the top of the 'recaps' array in data/recaps.json\n"
            f"3. Run: node scripts/build-recordings-index.mjs (regenerates the AI index + JSON-LD)"
        ),
    }
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / fname).write_text(md, encoding="utf-8")
        n = opts.get("number", 0)
        (out / f"recaps-entry-{n}.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")
        bundle["output_dir"] = str(out)
        bundle["files"] = {"transcript": fname, "recaps_entry": f"recaps-entry-{n}.json"}
    return bundle


def write_into_repo(repo_path: str, bundle: dict) -> dict:
    """Drop the export straight into a local zabalgames checkout for review.

    Writes the transcript .md to its path and inserts the recaps entry at the top
    of data/recaps.json's `recaps` array (de-duped by transcript path, format
    preserved). Does NOT commit or push - the user reviews `git diff` and commits/
    PRs themselves. Returns what changed.
    """
    repo = Path(repo_path)
    recaps_file = repo / "data" / "recaps.json"
    transcript_dest = repo / bundle["transcript_path"]
    if not recaps_file.exists():
        raise RuntimeError(f"Not a zabalgames checkout (no {recaps_file})")

    transcript_dest.parent.mkdir(parents=True, exist_ok=True)
    transcript_dest.write_text(bundle["transcript_md"], encoding="utf-8")

    data = json.loads(recaps_file.read_text())
    recaps = data.get("recaps", [])
    entry = bundle["recaps_entry"]
    # replace an existing entry with the same transcript, else prepend (newest first)
    recaps = [r for r in recaps if r.get("transcript") != entry.get("transcript")]
    recaps.insert(0, entry)
    data["recaps"] = recaps
    recaps_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return {
        "wrote_transcript": str(transcript_dest.relative_to(repo)),
        "updated": "data/recaps.json",
        "next": "Review git diff, run `node scripts/build-recordings-index.mjs`, then commit + PR.",
    }
