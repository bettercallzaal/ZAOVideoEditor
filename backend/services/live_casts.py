"""Day-of livestream casts for ZABAL Gamez sessions.

Generates the two-beat the team posts for every session (a 15-minute warning,
then "live now") in their exact templates from docs/distribution-casts-2026-06-11.md,
filled from the real data/workshop-leads.json schedule. Brand-clean by template
(no emojis, hyphens only). This is the "livestream is happening" promo piece.
"""

import json
import os
from pathlib import Path
from typing import Optional

LIVE_URL = "http://zabalgames.com/live"


def _leads_path() -> Optional[Path]:
    p = os.environ.get("STUDIO_WORKSHOP_LEADS", "").strip()
    if p:
        return Path(p)
    repo = os.environ.get("STUDIO_ZABALGAMES_PATH", "").strip()
    if repo:
        cand = Path(repo) / "data" / "workshop-leads.json"
        if cand.exists():
            return cand
    return None


def list_sessions() -> list:
    """The session lineup from workshop-leads.json (for the picker)."""
    p = _leads_path()
    if not p or not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
    except (ValueError, OSError):
        return []
    leads = data.get("leads", []) if isinstance(data, dict) else (data or [])
    luma_cal = data.get("luma_calendar", "") if isinstance(data, dict) else ""
    out = []
    for s in leads:
        out.append({
            "id": s.get("id", ""), "name": s.get("name", ""), "org": s.get("org", ""),
            "topic": s.get("topic", ""), "track": s.get("track", ""),
            "status": s.get("status", ""), "handle": s.get("handle", ""),
            "luma": s.get("luma", "") or luma_cal,
        })
    return out


def _leads_raw() -> list:
    """Raw lead records (all fields), for the schedule-driven casts."""
    p = _leads_path()
    if not p or not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
    except (ValueError, OSError):
        return []
    return data.get("leads", []) if isinstance(data, dict) else (data or [])


def _short(text: str, limit: int = 60) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def upcoming_cast(leads: list, today: str, window_days: int = 7,
                  calendar: str = "luma.com/zao") -> str:
    """The "this week at ZABAL Gamez" cast, built from dated, confirmed leads.

    `today` is an ISO date string (YYYY-MM-DD). Only confirmed leads with a
    parseable date in [today, today+window] are listed; never invents times.
    Returns "" when there is nothing dated to announce.
    """
    from datetime import date, timedelta
    try:
        t0 = date.fromisoformat((today or "").strip())
    except ValueError:
        return ""
    t1 = t0 + timedelta(days=window_days)

    rows = []
    for s in leads:
        if str(s.get("status", "")).lower() not in ("confirmed", "scheduled"):
            continue
        ds = (s.get("date") or s.get("confirmed_date") or "").strip()
        try:
            d = date.fromisoformat(ds)
        except ValueError:
            continue
        if not (t0 <= d <= t1):
            continue
        rows.append((d, s))

    if not rows:
        return ""
    rows.sort(key=lambda r: r[0])
    lines = ["This week at ZABAL Gamez:"]
    for d, s in rows:
        name = (s.get("name") or "").strip()
        org = (s.get("org") or "").strip()
        topic = _short(s.get("topic", ""))
        when = (s.get("when") or "").strip()
        org_part = f" ({org})" if org else ""
        when_part = f", {when}" if when else f", {d.isoformat()}"
        lines.append(f"- {name}{org_part} - {topic}{when_part}")
    lines += ["", f"Free, recorded, any harness. RSVP on the calendar: {calendar}"]
    return _clean("\n".join(lines))


def static_casts() -> dict:
    """The fixed announce casts (verbatim from docs/distribution-casts-2026-06-11.md)."""
    speakers = (
        "Every ZABAL Gamez speaker and what they delivered, in one place. The recording, "
        "the transcript, and the video for each session - and you can click any name for "
        "their profile.\n\nzabalgamez.com/speakers"
    )
    builder = (
        "ZABAL Gamez now has a live speakers board: every session that has run, the "
        "recording, the transcript, and the video, all generated from the season data so "
        "it stays current on its own. The build is the application.\n\nzabalgamez.com/speakers"
    )
    return {"speakers": _clean(speakers), "builder": _clean(builder)}


def _of_org(org: str) -> str:
    return f" of {org}" if org and org.strip() else ""


def day_of_casts(name: str, org: str = "", topic: str = "", time: str = "",
                 luma: str = "", handle: str = "") -> dict:
    """The 15-minute-warning and live-now casts, in the team's exact templates."""
    name = (name or "").strip()
    topic = (topic or "").strip()
    handle = (handle or "").strip().lstrip("@") or _slugish(name)
    luma = (luma or "").strip()
    rsvp = f"RSVP: {luma}  " if luma else ""

    warning = (
        "zm\n\n"
        f"15 minutes out. {name}{_of_org(org)} is up next at the ZABAL Gamez - {topic}."
        f"{(' ' + time + ' EST.') if time else ''}\n\n"
        f"{rsvp}watch live at {LIVE_URL}"
    ).strip()

    live_now = (
        "zm\n\n"
        f"Live now: @{handle}{_of_org(org)} for a ZABAL Gamez Workshop - {topic}.\n\n"
        f"Watch live: {LIVE_URL}" + (f"  RSVP: {luma}" if luma else "")
    ).strip()

    return {"warning": _clean(warning), "live_now": _clean(live_now)}


def _slugish(name: str) -> str:
    return "".join(c for c in (name or "").lower() if c.isalnum()) or "guest"


def _clean(text: str) -> str:
    return text.replace("—", "-").replace("–", "-")
