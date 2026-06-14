"""YouTube package: a ready-to-paste title, description, and tags for a VOD.

Assembles the already-generated insights (recap + chapters) into a YouTube
description with clickable chapter timestamps (first forced to 0:00, as YouTube
requires), plus tags derived from ZAO brand mentions. Pure formatting over
insights.json - no extra LLM call.
"""

import re

BRAND_TAGS = {
    "wavewarz": "WaveWarZ", "songjam": "SongJam", "zabal": "ZABAL Gamez",
    "zaostock": "ZAOstock", "the zao": "The ZAO", "coc concertz": "COC Concertz",
    "stilo world": "Stilo World", "bettercallzaal": "BetterCallZaal",
}
BASE_TAGS = ["The ZAO", "ZABAL Gamez", "web3 music", "creators"]


def _yt_ts(sec) -> str:
    try:
        s = int(float(sec))
    except (TypeError, ValueError):
        return "0:00"
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def build_chapters(chapters: list) -> list:
    """Chapter lines for the description. Forces a 0:00 first chapter (YouTube rule)."""
    rows = []
    for c in chapters or []:
        title = (c.get("title") or "").strip()
        if not title:
            continue
        rows.append((float(c.get("start", 0) or 0), title))
    rows.sort(key=lambda r: r[0])
    if not rows:
        return []
    if rows[0][0] > 0:
        rows.insert(0, (0.0, "Intro"))
    else:
        rows[0] = (0.0, rows[0][1])
    return [f"{_yt_ts(t)} {title}" for t, title in rows]


def build_tags(insights: dict, extra: list = None) -> list:
    text = " ".join([
        insights.get("recap", ""),
        " ".join(c.get("title", "") for c in insights.get("chapters", []) or []),
    ]).lower()
    tags = list(BASE_TAGS)
    for key, tag in BRAND_TAGS.items():
        if key in text and tag not in tags:
            tags.append(tag)
    for t in (extra or []):
        if t and t not in tags:
            tags.append(t)
    return tags


def build_description(insights: dict, footer: str = "") -> str:
    parts = []
    recap = (insights.get("recap") or "").strip()
    if recap:
        parts.append(recap)
    chapters = build_chapters(insights.get("chapters", []))
    if chapters:
        parts.append("Chapters:\n" + "\n".join(chapters))
    notes = (insights.get("show_notes") or "").strip()
    if notes and notes not in recap:
        parts.append(notes)
    if footer:
        parts.append(footer.strip())
    return _clean("\n\n".join(parts).strip())


def build_package(insights: dict, title: str = "", footer: str = "",
                  extra_tags: list = None) -> dict:
    return {
        "title": _clean((title or "").strip()),
        "description": build_description(insights, footer=footer),
        "tags": build_tags(insights, extra=extra_tags),
        "chapters": build_chapters(insights.get("chapters", [])),
    }


def _clean(text: str) -> str:
    return re.sub(r"[–—]", "-", text)
