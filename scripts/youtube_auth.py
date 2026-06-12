#!/usr/bin/env python3
"""One-time YouTube OAuth so the Studio can upload videos headlessly afterward.

Prereq: a Google OAuth client at backend/credentials.json (Google Cloud Console
-> APIs & Services -> Credentials -> OAuth client ID -> Desktop app), with the
YouTube Data API v3 enabled.

Run once: python scripts/youtube_auth.py
It opens a browser, you grant access, and a backend/youtube_token.json is saved.
After that, the "Upload to YouTube" button works without any prompt.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.publishers import GOOGLE_CREDENTIALS, _youtube_service  # noqa: E402


def main():
    if not GOOGLE_CREDENTIALS.exists():
        sys.exit(f"Missing {GOOGLE_CREDENTIALS} - download a Google OAuth client (Desktop app) there first.")
    print("Opening a browser for YouTube authorization...")
    _youtube_service()  # triggers the flow + writes youtube_token.json
    print("Done. backend/youtube_token.json saved. Upload to YouTube is now enabled.")


if __name__ == "__main__":
    main()
