"""Capabilities report: what the running instance can do, and how to turn on more.

Powers the in-app "Setup" panel so anyone running the Studio (especially someone
it was shared with) can see at a glance which features are live and exactly what
to set to enable the rest. Pure reads of env + installed tools.
"""

import os
import shutil

from .tool_availability import check_tool


def _env(*names: str) -> bool:
    return any((os.environ.get(n) or "").strip() for n in names)


def _bin(name: str) -> bool:
    return shutil.which(name) is not None


def _pymod(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None


def _bonfire_configured() -> bool:
    if _env("BONFIRE_API_KEY"):
        return True
    # The opt-in Bonfire button also reads ~/.zao/zao.env.
    try:
        from pathlib import Path
        z = Path.home() / ".zao" / "zao.env"
        return z.exists() and "BONFIRE_API_KEY" in z.read_text()
    except Exception:
        return False


def llm_backend() -> str:
    if _bin("claude"):
        return "claude CLI (Hermes)"
    if _env("OPENAI_API_KEY"):
        return "OpenAI"
    return "deterministic fallback"


def get_capabilities() -> dict:
    """Structured report: always-on core + toggleable integrations with hints."""
    groq = check_tool("groq")
    ytdlp = check_tool("yt_dlp")
    claude = _bin("claude")
    openai = _env("OPENAI_API_KEY")

    core = [
        {"label": "Transcribe recordings", "detail":
         "Groq (fast cloud)" if groq else "local Whisper (base model)"},
        {"label": "Edit, trim, and clip", "detail": "ffmpeg - clips, reframe, captions"},
        {"label": "Recaps, chapters, social drafts", "detail": llm_backend()},
        {"label": "Subtitles, YouTube package, bundle, search", "detail": "always on"},
    ]

    integrations = [
        {"key": "groq", "label": "Instant transcription (Groq)", "on": groq,
         "hint": "Set GROQ_API_KEY (free at console.groq.com)"},
        {"key": "llm", "label": "Polished AI writing", "on": claude or openai,
         "hint": "Install the claude CLI, or set OPENAI_API_KEY"},
        {"key": "ingest", "label": "Import from a link (YouTube/Twitch/Restream)", "on": ytdlp,
         "hint": "pip install yt-dlp"},
        {"key": "speakers", "label": "Speaker detection + talk-time", "on": _pymod("pyannote"),
         "hint": "pip install pyannote.audio and set HF_TOKEN"},
        {"key": "farcaster", "label": "Publish to Farcaster", "on": _env("NEYNAR_API_KEY", "FARCASTER_SIGNER_UUID"),
         "hint": "Set NEYNAR_API_KEY + FARCASTER_SIGNER_UUID"},
        {"key": "x", "label": "Publish to X", "on": _env("X_API_KEY", "X_ACCESS_TOKEN"),
         "hint": "Set X_API_KEY/SECRET + X_ACCESS_TOKEN/SECRET"},
        {"key": "youtube", "label": "Upload to YouTube", "on": _env("YOUTUBE_TOKEN") or _yt_token_file(),
         "hint": "Add backend/credentials.json then run scripts/youtube_auth.py"},
        {"key": "songid", "label": "Identify now-playing track", "on": _env("AUDD_API_TOKEN"),
         "hint": "Set AUDD_API_TOKEN (audd.io)"},
        {"key": "zabalgames", "label": "Export into the ZABAL Gamez repo", "on": _env("STUDIO_ZABALGAMES_PATH"),
         "hint": "Set STUDIO_ZABALGAMES_PATH to a local checkout"},
        {"key": "bonfire", "label": "Push recaps to Bonfire memory", "on": _bonfire_configured(),
         "hint": "Set BONFIRE_API_KEY (opt-in button, never automatic)"},
        {"key": "password", "label": "Shared-instance access password", "on": _env("STUDIO_PASSWORD"),
         "hint": "Set STUDIO_PASSWORD to gate a shared instance"},
    ]
    on_count = sum(1 for i in integrations if i["on"])
    return {
        "core": core,
        "integrations": integrations,
        "summary": {"integrations_on": on_count, "integrations_total": len(integrations),
                    "llm": llm_backend()},
    }


def _yt_token_file() -> bool:
    from pathlib import Path
    return (Path(__file__).parent.parent / "youtube_token.json").exists()
