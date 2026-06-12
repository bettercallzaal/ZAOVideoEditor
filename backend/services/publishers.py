"""Publish to Farcaster, X, and YouTube.

Each publisher reads its credentials from the environment (or, for YouTube, the
Google OAuth files this repo already uses for Drive). When a credential is
missing the call raises a clear RuntimeError naming exactly what to set, so the
UI can tell you what is needed rather than failing silently.

Credentials:
  Farcaster: NEYNAR_API_KEY, FARCASTER_SIGNER_UUID
  X:         X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET
  YouTube:   backend/credentials.json (Google OAuth client) + token.json
             (created on first auth, must include the youtube.upload scope)
"""

import os
from pathlib import Path
from typing import Optional

BACKEND_DIR = Path(__file__).parent.parent
GOOGLE_CREDENTIALS = BACKEND_DIR / "credentials.json"
YOUTUBE_TOKEN = BACKEND_DIR / "youtube_token.json"
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def status() -> dict:
    """Which platforms are configured (for the UI)."""
    return {
        "farcaster": farcaster_configured(),
        "x": x_configured(),
        "youtube": youtube_configured(),
    }


# ---------------- Farcaster (Neynar) ----------------

def farcaster_configured() -> bool:
    return bool(_env("NEYNAR_API_KEY") and _env("FARCASTER_SIGNER_UUID"))


def post_farcaster(text: str, embed_urls: Optional[list] = None) -> dict:
    """Publish a cast via Neynar. embed_urls must be PUBLIC URLs to embed."""
    key, signer = _env("NEYNAR_API_KEY"), _env("FARCASTER_SIGNER_UUID")
    if not (key and signer):
        raise RuntimeError("Farcaster not configured: set NEYNAR_API_KEY and FARCASTER_SIGNER_UUID")
    import requests
    body = {"signer_uuid": signer, "text": text[:1024]}
    if embed_urls:
        body["embeds"] = [{"url": u} for u in embed_urls]
    r = requests.post(
        "https://api.neynar.com/v2/farcaster/cast",
        json=body, headers={"x-api-key": key, "Content-Type": "application/json"}, timeout=30,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"Farcaster post failed ({r.status_code}): {r.text[:200]}")
    cast = r.json().get("cast", {})
    return {"platform": "farcaster", "hash": cast.get("hash"),
            "url": f"https://warpcast.com/~/conversations/{cast.get('hash')}" if cast.get("hash") else None}


# ---------------- X / Twitter ----------------

def x_configured() -> bool:
    return all(_env(k) for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"))


def post_x(text: str) -> dict:
    """Post a tweet via the X v2 API (OAuth 1.0a user context)."""
    if not x_configured():
        raise RuntimeError("X not configured: set X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET")
    try:
        from requests_oauthlib import OAuth1Session
    except ImportError:
        raise RuntimeError("X posting needs requests-oauthlib: pip install requests-oauthlib")
    oauth = OAuth1Session(
        _env("X_API_KEY"), client_secret=_env("X_API_SECRET"),
        resource_owner_key=_env("X_ACCESS_TOKEN"), resource_owner_secret=_env("X_ACCESS_SECRET"),
    )
    r = oauth.post("https://api.twitter.com/2/tweets", json={"text": text[:280]})
    if r.status_code >= 300:
        raise RuntimeError(f"X post failed ({r.status_code}): {r.text[:200]}")
    data = r.json().get("data", {})
    return {"platform": "x", "id": data.get("id"),
            "url": f"https://x.com/i/web/status/{data.get('id')}" if data.get("id") else None}


# ---------------- YouTube ----------------

def youtube_configured() -> bool:
    # A token implies a completed OAuth; credentials.json alone needs a one-time
    # interactive auth (run scripts/youtube_auth.py) before headless upload works.
    return GOOGLE_CREDENTIALS.exists()


def _youtube_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if YOUTUBE_TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(YOUTUBE_TOKEN), YOUTUBE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif GOOGLE_CREDENTIALS.exists():
            flow = InstalledAppFlow.from_client_secrets_file(str(GOOGLE_CREDENTIALS), YOUTUBE_SCOPES)
            creds = flow.run_local_server(port=0)
        else:
            raise RuntimeError("YouTube not configured: place a Google OAuth credentials.json in backend/")
        YOUTUBE_TOKEN.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload_youtube(video_path: str, title: str, description: str = "",
                   tags: Optional[list] = None, privacy: str = "unlisted") -> dict:
    """Upload a video to YouTube. privacy: public | unlisted | private."""
    if not Path(video_path).exists():
        raise RuntimeError(f"Video not found: {video_path}")
    from googleapiclient.http import MediaFileUpload
    service = _youtube_service()
    body = {
        "snippet": {"title": title[:100], "description": description[:5000], "tags": tags or []},
        "status": {"privacyStatus": privacy if privacy in ("public", "unlisted", "private") else "unlisted"},
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    vid = response.get("id")
    return {"platform": "youtube", "id": vid,
            "url": f"https://youtu.be/{vid}" if vid else None}
