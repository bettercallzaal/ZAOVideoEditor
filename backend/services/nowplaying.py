"""Now playing: post the track on the DJ deck to social, live.

Three ways to know what is playing, in order of how little they need:
1. Type it in (always works).
2. Point at a now-playing source - the text file or URL that OBS / Serato /
   rekordbox already write the current track to (no keys).
3. Identify it from the captured audio via AudD (needs AUDD_API_TOKEN).

Whichever path, it formats a brand-clean "now playing" post (no emojis, the
[MUSIC] label, exact ZAO casing) ready to copy or publish.
"""

import os
import re
from typing import Callable, Optional

LIVE_URL = "http://zabalgames.com/live"


def parse_track(raw: str) -> dict:
    """Pull {artist, title} out of a now-playing string.

    Handles "Artist - Title", "Title by Artist", and a bare title.
    """
    s = (raw or "").strip()
    if not s:
        return {"artist": "", "title": ""}
    # strip common prefixes some tools prepend
    s = re.sub(r"^(now playing|np|playing)\s*[:\-]\s*", "", s, flags=re.I).strip()
    if " - " in s:
        left, right = s.split(" - ", 1)
        return {"artist": left.strip(), "title": right.strip()}
    m = re.match(r"^(.*?)\s+by\s+(.*)$", s, flags=re.I)
    if m:
        return {"artist": m.group(2).strip(), "title": m.group(1).strip()}
    return {"artist": "", "title": s}


def now_playing_post(title: str, artist: str = "", live_url: str = "",
                     handle: str = "") -> dict:
    """Brand-clean Farcaster + X posts for the current track."""
    title = (title or "").strip()
    artist = (artist or "").strip()
    live_url = (live_url or "").strip() or LIVE_URL
    if not title:
        return {"farcaster": "", "x": "", "error": "No track to post"}
    track = f"{title} by {artist}" if artist else title
    by = f" by @{handle.lstrip('@')}" if handle else ""
    fc = f"[MUSIC] Now playing: {track}{by}\n\nLive now at {live_url}"
    x = f"[MUSIC] Now playing: {track}. Live at {live_url}"
    return {"farcaster": _clean(fc)[:320], "x": _clean(x)[:280], "track": track}


def fetch_source(source: str, fetcher: Optional[Callable[[str], str]] = None) -> dict:
    """Read the current track from a now-playing file path or URL."""
    source = (source or "").strip()
    if not source:
        return {"raw": "", "artist": "", "title": "", "error": "No source set"}
    try:
        if source.startswith("http://") or source.startswith("https://"):
            raw = (fetcher or _http_get)(source)
        else:
            from pathlib import Path
            raw = Path(source).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"raw": "", "artist": "", "title": "", "error": str(e)}
    raw = (raw or "").strip().splitlines()[0].strip() if raw else ""
    return {"raw": raw, **parse_track(raw)}


def _http_get(url: str) -> str:
    import urllib.request
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read().decode("utf-8", errors="replace")


def recognize(audio_path: str, token: Optional[str] = None,
              poster: Optional[Callable] = None) -> dict:
    """Identify the track from an audio clip via AudD. Needs AUDD_API_TOKEN.

    Returns {artist, title} on a hit, else {error}. Never raises.
    """
    token = token or os.environ.get("AUDD_API_TOKEN", "").strip()
    if not token:
        return {"error": "Song ID needs AUDD_API_TOKEN (audd.io)"}
    try:
        data = (poster or _audd_post)(audio_path, token)
    except Exception as e:
        return {"error": str(e)}
    result = (data or {}).get("result") if isinstance(data, dict) else None
    if not result:
        return {"error": "No match"}
    return {"artist": result.get("artist", ""), "title": result.get("title", "")}


def _audd_post(audio_path: str, token: str) -> dict:
    import requests
    with open(audio_path, "rb") as f:
        resp = requests.post("https://api.audd.io/",
                             data={"api_token": token, "return": "apple_music"},
                             files={"file": f}, timeout=30)
    return resp.json()


def _clean(text: str) -> str:
    return text.replace("—", "-").replace("–", "-")
