"""Go-live detection: is this channel / stream URL live right now?

Wraps the yt-dlp probe and reports a clean live/not-live answer so the Studio can
prompt "the stream is live - start a session?" instead of the host watching for
it. Never raises: a probe failure comes back as {live: False, error: ...} so a
poller can keep trying.
"""

from typing import Callable, Optional


def _default_prober(url: str) -> dict:
    from .ingest_service import probe_url
    return probe_url(url)


def check_live(url: str, prober: Optional[Callable[[str], dict]] = None) -> dict:
    """Return {live, title, uploader, extractor, url, error}. Never raises."""
    url = (url or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return {"live": False, "error": "Provide a valid http(s) URL", "url": url}
    prober = prober or _default_prober
    try:
        data = prober(url)
    except Exception as e:
        return {"live": False, "error": str(e), "url": url}
    return {
        "live": bool(data.get("is_live", False)),
        "title": data.get("title", ""),
        "uploader": data.get("uploader", ""),
        "extractor": data.get("extractor", ""),
        "url": data.get("webpage_url", url),
        "error": "",
    }
