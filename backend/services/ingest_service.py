"""Livestream / VOD ingest via yt-dlp.

Pulls a finished stream or video by URL (Restream recording, YouTube Live VOD,
Twitch VOD, generic HLS .m3u8, direct mp4) into a project's input/ folder as
main.mp4, so the existing transcribe -> caption -> clip pipeline runs unchanged.

yt-dlp is an optional tool. Availability is checked via
services.tool_availability.check_tool("yt_dlp").
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional


# yt-dlp emits lines like "[download]  45.2% of 12.34MiB at ..." with --newline.
_PROGRESS_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")

# Hosts we explicitly advertise as supported. yt-dlp handles far more (1000+
# extractors); this list is only for the UI / docs, not an allowlist.
SUPPORTED_SOURCES = [
    {"id": "youtube", "label": "YouTube / YouTube Live VOD"},
    {"id": "twitch", "label": "Twitch VOD"},
    {"id": "restream", "label": "Restream recording (public URL)"},
    {"id": "hls", "label": "HLS stream (.m3u8)"},
    {"id": "direct", "label": "Direct video URL (.mp4/.mov/.webm)"},
]


def yt_dlp_available() -> bool:
    """True if the yt-dlp CLI is on PATH."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"], capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def probe_url(url: str) -> dict:
    """Return basic metadata for a URL without downloading it.

    Raises RuntimeError if yt-dlp cannot resolve the URL.
    """
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-single-json", "--no-playlist", "--no-warnings", url],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        raise RuntimeError("yt-dlp is not installed")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Timed out resolving the URL")

    if result.returncode != 0:
        # yt-dlp prints the real reason on stderr; surface a trimmed version.
        reason = (result.stderr or "").strip().splitlines()
        msg = reason[-1] if reason else "could not resolve URL"
        raise RuntimeError(f"yt-dlp could not resolve the URL: {msg}")

    data = json.loads(result.stdout)
    return {
        "title": data.get("title", ""),
        "duration": data.get("duration"),
        "uploader": data.get("uploader", ""),
        "extractor": data.get("extractor_key", data.get("extractor", "")),
        "is_live": bool(data.get("is_live", False)),
        "webpage_url": data.get("webpage_url", url),
    }


def download_to_project(url: str, project_dir: Path,
                        on_progress: Optional[Callable[[int, str], None]] = None) -> dict:
    """Download a URL into project_dir/input/main.mp4.

    on_progress(pct, message) is called with 0-100 download progress.
    Returns {"filename", "size", "title"} on success; raises RuntimeError on failure.
    """
    input_dir = project_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    # Clear any prior main video so re-ingest is clean.
    for existing in input_dir.glob("main.*"):
        existing.unlink()

    title = ""
    if on_progress:
        on_progress(2, "Resolving source...")
    try:
        info = probe_url(url)
        title = info.get("title", "")
        if info.get("is_live"):
            raise RuntimeError(
                "URL is a live stream still in progress. Ingest the recording/VOD after it ends."
            )
    except RuntimeError:
        # Probe is best-effort; the download below will surface a hard failure.
        pass

    out_template = str(input_dir / "main.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--newline",
        "--no-warnings",
        "-o", out_template,
        url,
    ]

    if on_progress:
        on_progress(5, "Starting download...")

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    last_pct = 5
    assert proc.stdout is not None
    for line in proc.stdout:
        m = _PROGRESS_RE.search(line)
        if m and on_progress:
            # Map download 0-100% onto 5-90% of the task.
            pct = 5 + int(float(m.group(1)) * 0.85)
            if pct > last_pct:
                last_pct = pct
                on_progress(pct, f"Downloading... {m.group(1)}%")
    proc.wait()

    if proc.returncode != 0:
        raise RuntimeError("yt-dlp download failed. Check the URL is a valid public video/VOD.")

    # Locate the produced file and normalise to main.mp4.
    produced = sorted(input_dir.glob("main.*"))
    if not produced:
        raise RuntimeError("Download finished but no output file was produced")

    main_file = produced[0]
    if main_file.suffix.lower() != ".mp4":
        if on_progress:
            on_progress(92, "Remuxing to mp4...")
        main_file = _remux_to_mp4(main_file, input_dir)

    if on_progress:
        on_progress(98, "Ingest complete")

    return {
        "filename": main_file.name,
        "size": main_file.stat().st_size,
        "title": title,
    }


def _remux_to_mp4(src: Path, input_dir: Path) -> Path:
    """Remux a non-mp4 download to main.mp4 (stream copy, re-encode fallback)."""
    dest = input_dir / "main.mp4"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-c", "copy",
             "-movflags", "+faststart", str(dest)],
            check=True, capture_output=True, timeout=600,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(src), "-c:v", "libx264",
                 "-preset", "ultrafast", "-crf", "20", "-c:a", "aac",
                 "-movflags", "+faststart", str(dest)],
                check=True, capture_output=True, timeout=1800,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # Keep the original if both remux attempts fail.
            return src
    if src.exists() and src != dest:
        src.unlink()
    return dest
