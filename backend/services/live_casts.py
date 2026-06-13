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
