"""Audiogram: give an audio-only recording a video stream.

Audio spaces (Juke, X Spaces, Zuke) have no video track. Every visual stage in
this repo routes through ffmpeg_service.get_video_params(), which raises
"No video stream found" on audio-only input. So a space recording transcribes
fine and then dies at captions, clips, reframe, and render.

This module is the bridge. It composites a branded card and a live waveform
into a real 1920x1080 h264 stream, muxed with the source audio. Everything
downstream then works unchanged.

Captions are burned in the same ffmpeg pass when an .ass file is supplied, so a
full-length space is encoded exactly once.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

# ZAO brand palette, matching the brand_dark caption style in caption_gen.py.
BRAND_BG = "#141e27"
BRAND_FG = "#e0ddaa"

WIDTH = 1920
HEIGHT = 1080

# Waveform geometry within the 1920x1080 frame.
WAVE_W = 1600
WAVE_H = 220
WAVE_Y = 700


def probe_streams(media_path: str) -> dict:
    """Return {'has_video': bool, 'has_audio': bool, 'duration': float}.

    Unlike get_video_params(), this never raises on audio-only input. That is
    the whole point: callers need to *detect* audio-only, not crash on it.
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type",
        "-show_entries", "format=duration",
        "-of", "json", media_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {media_path}: {result.stderr.strip()}")

    import json
    info = json.loads(result.stdout)
    kinds = {s.get("codec_type") for s in info.get("streams", [])}
    try:
        duration = float(info.get("format", {}).get("duration", 0.0))
    except (TypeError, ValueError):
        duration = 0.0

    return {
        "has_video": "video" in kinds,
        "has_audio": "audio" in kinds,
        "duration": duration,
    }


def is_audio_only(media_path: str) -> bool:
    """True for a recording with sound but no picture, whatever the extension.

    A Juke space export is often a .mp4 containing a single AAC stream and no
    video stream at all, so extension sniffing is not enough.
    """
    info = probe_streams(media_path)
    return info["has_audio"] and not info["has_video"]


def _fit_text(draw, text: str, font_path: Optional[str], max_width: int,
              start_size: int, min_size: int = 24):
    """Largest font size at which text fits max_width. Returns (font, width)."""
    from PIL import ImageFont

    size = start_size
    while size > min_size:
        font = (ImageFont.truetype(font_path, size) if font_path
                else ImageFont.load_default())
        width = draw.textlength(text, font=font)
        if width <= max_width:
            return font, width
        size -= 2

    font = (ImageFont.truetype(font_path, min_size) if font_path
            else ImageFont.load_default())
    return font, draw.textlength(text, font=font)


def build_card(out_png: str, title: str, subtitle: str = "", footer: str = "",
               bg: str = BRAND_BG, fg: str = BRAND_FG) -> str:
    """Render the static 1920x1080 branded background card.

    Drawn with Pillow rather than ffmpeg's drawtext so the card renders
    identically on builds without freetype, and so a long title can be
    auto-fitted instead of overflowing the frame.
    """
    from PIL import Image, ImageDraw

    from .ffmpeg_service import _find_font

    img = Image.new("RGB", (WIDTH, HEIGHT), bg)
    draw = ImageDraw.Draw(img)

    bold_font_path = _find_font(bold=True)
    plain_font_path = _find_font(bold=False)

    margin = 160
    max_text_w = WIDTH - (margin * 2)

    # Accent rule above the title.
    draw.rectangle([margin, 300, margin + 120, 308], fill=fg)

    title_font, _ = _fit_text(draw, title, bold_font_path, max_text_w, 96)
    draw.text((margin, 360), title, font=title_font, fill=fg)

    if subtitle:
        sub_font, _ = _fit_text(draw, subtitle, plain_font_path, max_text_w, 44)
        draw.text((margin, 480), subtitle, font=sub_font, fill=fg)

    if footer:
        foot_font, _ = _fit_text(draw, footer, plain_font_path, max_text_w, 34)
        draw.text((margin, HEIGHT - 130), footer, font=foot_font, fill=fg)

    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)
    return out_png


def _hex_to_ffmpeg_color(hex_color: str) -> str:
    return "0x" + hex_color.lstrip("#").upper()


def _escape_for_filter(path: str) -> str:
    """Escape a path for use inside an ffmpeg filtergraph argument."""
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def build_filtergraph(ass_path: Optional[str] = None, fps: int = 30,
                      wave_color: str = BRAND_FG) -> str:
    """Compose card + waveform (+ optional burned captions) into one graph.

    Input 0 is the looped card image, input 1 is the audio.
    """
    color = _hex_to_ffmpeg_color(wave_color)

    chain = [
        # scale=sqrt lifts conversational speech off the baseline; on a linear
        # scale a talking voice draws an almost flat line at this height.
        f"[1:a]showwaves=s={WAVE_W}x{WAVE_H}:mode=cline:rate={fps}:scale=sqrt:colors={color}[wave]",
        f"[0:v][wave]overlay=(W-w)/2:{WAVE_Y}:shortest=1[bg]",
    ]

    if ass_path:
        chain.append(f"[bg]ass='{_escape_for_filter(ass_path)}'[styled]")
        chain.append("[styled]format=yuv420p[v]")
    else:
        chain.append("[bg]format=yuv420p[v]")

    return ";".join(chain)


def render_audiogram(audio_path: str, out_path: str, title: str,
                     subtitle: str = "", footer: str = "",
                     ass_path: Optional[str] = None, fps: int = 30,
                     hwaccel: bool = False, card_path: Optional[str] = None,
                     duration_limit: Optional[float] = None,
                     on_progress=None) -> str:
    """Turn audio into a 1920x1080 h264 mp4. The bridge.

    ass_path: burn these captions in the same pass (needs an ffmpeg with libass).
    hwaccel:  use h264_videotoolbox on Apple silicon. Much faster, slightly larger.
    duration_limit: cap output length, for smoke tests.
    """
    info = probe_streams(audio_path)
    if not info["has_audio"]:
        raise RuntimeError(f"No audio stream in {audio_path}; nothing to render.")
    if info["has_video"]:
        raise RuntimeError(
            f"{audio_path} already has a video stream. "
            "Use the normal video pipeline; the audiogram bridge is for audio-only input."
        )

    if ass_path and not _has_ass_filter():
        raise RuntimeError(
            "Captions requested but this ffmpeg has no 'ass' filter (libass missing). "
            "Rebuild ffmpeg (brew reinstall ffmpeg) or render without captions."
        )

    tmp_card = None
    if card_path is None:
        tmp_card = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp_card.close()
        card_path = tmp_card.name
        build_card(card_path, title, subtitle, footer)

    if on_progress:
        on_progress(10, "Rendering audiogram...")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = ["ffmpeg", "-y", "-loop", "1", "-framerate", str(fps), "-i", card_path,
           "-i", audio_path]
    if duration_limit:
        cmd += ["-t", str(duration_limit)]

    cmd += ["-filter_complex", build_filtergraph(ass_path, fps), "-map", "[v]", "-map", "1:a"]

    if hwaccel:
        cmd += ["-c:v", "h264_videotoolbox", "-b:v", "6M"]
    else:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]

    cmd += [
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-pix_fmt", "yuv420p", "-shortest", "-movflags", "+faststart",
        out_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if tmp_card and os.path.exists(tmp_card.name):
        os.unlink(tmp_card.name)

    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-12:])
        raise RuntimeError(f"audiogram render failed:\n{tail}")

    if on_progress:
        on_progress(100, "Audiogram complete")

    return out_path


def ensure_video_track(project_dir, media_path: str, title: str = "",
                       subtitle: str = "", footer: str = "", fps: int = 30,
                       hwaccel: bool = False, on_progress=None):
    """Guarantee the project has a file with a real video stream. Returns its path.

    A video input is returned untouched. An audio-only input is rendered once
    into processing/audiogram.mp4 and cached, so re-running the pipeline does
    not re-encode a two-hour space.

    Call this at ingest/upload time, on a background task. Never call it from a
    request handler: rendering a long recording takes minutes.
    """
    from pathlib import Path as _Path

    media = _Path(media_path)
    if not is_audio_only(str(media)):
        return media

    audiogram = _Path(project_dir) / "processing" / "audiogram.mp4"
    if audiogram.exists() and audiogram.stat().st_size > 0:
        if on_progress:
            on_progress(100, "Reusing cached audiogram")
        return audiogram

    audiogram.parent.mkdir(parents=True, exist_ok=True)
    render_audiogram(
        str(media), str(audiogram),
        title=title or media.stem,
        subtitle=subtitle, footer=footer,
        fps=fps, hwaccel=hwaccel, on_progress=on_progress,
    )
    return audiogram


def _has_ass_filter() -> bool:
    """Whether this ffmpeg exposes the libass 'ass' filter.

    Probing the filter directly beats scanning `-filters` output, whose help
    text contains the substring "ass" in unrelated filter names and
    descriptions ("allpass", "bandpass", "Pass the source unchanged").
    """
    if not shutil.which("ffmpeg"):
        return False
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-h", "filter=ass"],
        capture_output=True, text=True,
    )
    return "Unknown filter" not in (result.stdout + result.stderr)
