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

import json
import os
import re
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

# A vertical clip cannot be produced by cropping a 16:9 card - the title and the
# waveform were laid out for a wide frame and the crop cuts straight through
# them. Render natively at the target aspect instead.
ASPECTS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
}

# Layout ratios, taken from the reference 1920x1080 card. Everything scales off
# the frame WIDTH (not height), so a 9:16 frame gets proportionate type rather
# than absurdly large type.
_MARGIN_R = 160 / 1920
_TITLE_R = 96 / 1920
_SUB_R = 44 / 1920
_FOOT_R = 34 / 1920
_WAVE_W_R = 1600 / 1920
_WAVE_H_R = 220 / 1920

# Waveform baseline, as a fraction of frame height. A portrait frame reserves its
# bottom third for burned captions, so the waveform sits nearer the middle and the
# title moves to the top. Reusing the landscape ratio leaves the top 60% of a
# Short empty and drops the waveform behind the caption band.
_WAVE_Y_R_LANDSCAPE = 700 / 1080
_WAVE_Y_R_PORTRAIT = 0.42

# Waveform geometry for the default 16:9 frame. Kept as module constants because
# callers and tests reference them.
WAVE_W = int(WIDTH * _WAVE_W_R)
WAVE_H = int(WIDTH * _WAVE_H_R)
WAVE_Y = int(HEIGHT * _WAVE_Y_R_LANDSCAPE)


def aspect_size(aspect: str) -> tuple:
    if aspect not in ASPECTS:
        raise ValueError(f"Unsupported aspect {aspect!r}. Use one of {list(ASPECTS)}.")
    return ASPECTS[aspect]


def is_portrait(width: int, height: int) -> bool:
    return height > width


def _wave_geometry(width: int, height: int) -> tuple:
    """(wave_width, wave_height, wave_y) for any frame size."""
    portrait = is_portrait(width, height)
    # A narrow frame needs a proportionally taller waveform or it reads as a line.
    height_ratio = 0.20 if portrait else _WAVE_H_R
    y_ratio = _WAVE_Y_R_PORTRAIT if portrait else _WAVE_Y_R_LANDSCAPE
    return (
        int(width * _WAVE_W_R),
        max(60, int(width * height_ratio)),
        int(height * y_ratio),
    )


# Elementary streams with no container index. ffprobe reports a duration for
# these, but it is a guess from the bitrate, not a fact.
_RAW_FORMATS = {"aac", "mp3", "ac3", "eac3", "dts", "flac", "h264", "hevc"}


def _decoded_duration(media_path: str) -> Optional[float]:
    """Decode the audio and read the clock. Slow-ish but exact (~1.6s for 54 min)."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", media_path,
         "-map", "0:a", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    times = re.findall(r"time=(\d+):(\d\d):(\d\d)\.(\d+)", result.stderr)
    if not times:
        return None
    h, m, s, frac = times[-1]
    return int(h) * 3600 + int(m) * 60 + int(s) + float(f"0.{frac}")


def probe_streams(media_path: str, exact_duration: bool = True) -> dict:
    """Return {'has_video': bool, 'has_audio': bool, 'duration': float}.

    Unlike get_video_params(), this never raises on audio-only input. That is
    the whole point: callers need to *detect* audio-only, not crash on it.

    A Juke space export is often a raw AAC elementary stream inside a .mp4 name.
    It carries no container index, so ffprobe estimates duration from the bitrate
    and can be minutes off - one real 54:10 recording reported 57:59. Every
    downstream number (the card footer, --minutes, the render verifier's expected
    duration) inherits that error, so decode to get the truth.

    That decode is O(file length) - 1.7s for 54 minutes. Pass exact_duration=False
    when you only need the stream kinds, so a request handler asking "is this
    audio-only?" does not decode an hour of audio to answer a yes/no question.
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type,duration",
        "-show_entries", "format=duration,format_name",
        "-of", "json", media_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {media_path}: {result.stderr.strip()}")

    info = json.loads(result.stdout)
    streams = info.get("streams", [])
    kinds = {s.get("codec_type") for s in streams}
    fmt = info.get("format", {})

    try:
        duration = float(fmt.get("duration", 0.0))
    except (TypeError, ValueError):
        duration = 0.0

    # A raw stream reports a duration on both the format and the stream, but both
    # come from the same bitrate estimate, so neither is evidence. The format name
    # is the only signal. (Checking "is the stream duration missing?" never fires.)
    formats = set((fmt.get("format_name") or "").split(","))
    if exact_duration and "audio" in kinds and formats & _RAW_FORMATS:
        exact = _decoded_duration(media_path)
        if exact:
            duration = exact

    return {
        "has_video": "video" in kinds,
        "has_audio": "audio" in kinds,
        "duration": duration,
    }


def is_audio_only(media_path: str) -> bool:
    """True for a recording with sound but no picture, whatever the extension.

    A Juke space export is often a .mp4 containing a single AAC stream and no
    video stream at all, so extension sniffing is not enough.

    Never decodes. find_video() calls this on every captions/clips/silence request,
    and decoding an hour of audio to answer a yes/no question turns a cheap request
    into seconds of CPU.
    """
    info = probe_streams(media_path, exact_duration=False)
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
               bg: str = BRAND_BG, fg: str = BRAND_FG,
               width: int = WIDTH, height: int = HEIGHT) -> str:
    """Render the static branded background card at any frame size.

    Drawn with Pillow rather than ffmpeg's drawtext so the card renders
    identically on builds without freetype, and so a long title can be
    auto-fitted instead of overflowing the frame.

    The title block sits above the waveform baseline, and the caption band at the
    bottom of a vertical frame is left clear, so burned captions never collide
    with the footer.
    """
    from PIL import Image, ImageDraw

    from .ffmpeg_service import _find_font

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    bold_font_path = _find_font(bold=True)
    plain_font_path = _find_font(bold=False)

    margin = int(width * _MARGIN_R)
    max_text_w = width - (margin * 2)
    _, wave_h, wave_y = _wave_geometry(width, height)
    portrait = is_portrait(width, height)

    title_size = int(width * (_TITLE_R * 1.3 if portrait else _TITLE_R))
    sub_size = int(width * _SUB_R)
    foot_size = int(width * _FOOT_R)

    title_font, _ = _fit_text(draw, title, bold_font_path, max_text_w, title_size)
    sub_font = None
    if subtitle:
        sub_font, _ = _fit_text(draw, subtitle, plain_font_path, max_text_w, sub_size)

    gap = int(height * (0.035 if portrait else 0.06))
    title_h = title_font.size
    sub_h = sub_font.size if sub_font else 0
    block_h = title_h + (int(sub_h * 1.6) if sub_font else 0)

    if portrait:
        # Title up top, waveform in the middle, bottom third left clear for captions.
        title_y = int(height * 0.12)
    else:
        title_y = max(margin, wave_y - gap - block_h)

    rule_h = max(4, int(height * 0.0074))
    draw.rectangle(
        [margin, title_y - gap, margin + int(width * 0.0625), title_y - gap + rule_h],
        fill=fg,
    )
    draw.text((margin, title_y), title, font=title_font, fill=fg)
    if sub_font:
        draw.text((margin, title_y + int(title_h * 1.25)), subtitle, font=sub_font, fill=fg)

    if footer:
        foot_font, _ = _fit_text(draw, footer, plain_font_path, max_text_w, foot_size)
        # Sit the footer just under the waveform on portrait, so it never lands in
        # the caption band; keep it pinned near the bottom on landscape.
        foot_y = (wave_y + wave_h + gap) if portrait else (height - int(height * 0.12))
        draw.text((margin, foot_y), footer, font=foot_font, fill=fg)

    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)
    return out_png


def _hex_to_ffmpeg_color(hex_color: str) -> str:
    return "0x" + hex_color.lstrip("#").upper()


def _escape_for_filter(path: str) -> str:
    """Escape a path for use inside an ffmpeg filtergraph argument."""
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


AUDIO_LABEL = "a_out"


def build_filtergraph(ass_path: Optional[str] = None, fps: int = 30,
                      wave_color: str = BRAND_FG,
                      width: int = WIDTH, height: int = HEIGHT,
                      start: float = 0.0, duration: Optional[float] = None) -> str:
    """Compose card + waveform (+ optional burned captions) into one graph.

    Input 0 is the looped card image, input 1 is the audio. Emits [v] and [a_out].

    A clip window is trimmed *inside* the graph rather than with `-ss` before
    `-i`. Input seek shifts the audio's timestamps while the looped card still
    starts at zero, and overlay pairs frames by PTS - so the waveform frames land
    outside the output window and the wave collapses to a flat centre line. The
    audio survives that (it is mapped directly), which makes the bug easy to miss:
    the clip sounds right and looks dead. atrim + asetpts keeps both aligned.
    """
    color = _hex_to_ffmpeg_color(wave_color)
    wave_w, wave_h, wave_y = _wave_geometry(width, height)

    trim = ""
    if start or duration is not None:
        parts = []
        if start:
            parts.append(f"start={start}")
        if duration is not None:
            parts.append(f"end={start + duration}")
        trim = f"atrim={':'.join(parts)},asetpts=PTS-STARTPTS,"

    chain = [
        # One audio branch feeds the waveform, the other is muxed out, so both see
        # exactly the same trimmed, PTS-reset stream.
        f"[1:a]{trim}asplit=2[{AUDIO_LABEL}][a_wave]",
        # scale=sqrt lifts conversational speech off the baseline; on a linear
        # scale a talking voice draws an almost flat line at this height.
        #
        # draw=full matters. The default (draw=scale) scales each drawn sample's
        # pixel value by how much of the column it covers, so when a frame's
        # samples do not divide evenly into the width the strokes come out
        # translucent and overlay blends them away to near-invisible. A 1920-wide
        # frame hides this by accident: 48000/30 = 1600 samples across a 1600px
        # waveform is exactly one sample per column, so nothing is antialiased.
        # A 9:16 waveform is 900px wide and disappears.
        f"[a_wave]showwaves=s={wave_w}x{wave_h}:mode=cline:rate={fps}:scale=sqrt:"
        f"draw=full:colors={color}[wave]",
        f"[0:v][wave]overlay=(W-w)/2:{wave_y}:shortest=1[bg]",
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
                     aspect: str = "16:9", start: float = 0.0,
                     on_progress=None) -> str:
    """Turn audio into an h264 mp4 at the given aspect. The bridge.

    ass_path: burn these captions in the same pass (needs an ffmpeg with libass).
    hwaccel:  use h264_videotoolbox on Apple silicon. Much faster, slightly larger.
    duration_limit: cap output length, for smoke tests and clip windows.
    aspect:   "16:9" (YouTube), "9:16" (Shorts/TikTok/Reels), or "1:1".
    start:    seek into the audio before rendering, for clip windows.
    """
    width, height = aspect_size(aspect)
    info = probe_streams(audio_path, exact_duration=False)  # only stream kinds needed
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
        build_card(card_path, title, subtitle, footer, width=width, height=height)

    if on_progress:
        on_progress(10, "Rendering audiogram...")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = ["ffmpeg", "-y", "-loop", "1", "-framerate", str(fps), "-i", card_path,
           "-i", audio_path]

    graph = build_filtergraph(ass_path, fps, width=width, height=height,
                              start=start, duration=duration_limit)
    cmd += ["-filter_complex", graph, "-map", "[v]", "-map", f"[{AUDIO_LABEL}]"]

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


def render_short(audio_path: str, out_path: str, start: float, end: float,
                 title: str, subtitle: str = "", segments: Optional[list] = None,
                 style: str = "bold_pop", aspect: str = "9:16",
                 fps: int = 30, hwaccel: bool = False, on_progress=None) -> dict:
    """Render one vertical clip straight from the audio, captions burned in.

    Deliberately does NOT crop the 16:9 audiogram: the card and waveform were
    laid out for a wide frame, and a centre crop cuts the title in half and
    reduces the waveform to a hairline. Rendering natively at 9:16 costs the same
    single ffmpeg pass and looks right.

    Falls back to the Pillow overlay burn when this ffmpeg lacks libass, so
    captions survive either way. Returns {"filename", "aspect", "duration",
    "captioned", "caption_error"}.
    """
    duration = end - start
    if duration <= 0:
        raise ValueError("Clip end must be after start")

    width, height = aspect_size(aspect)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    ass_path = None
    work_dir = None
    if segments:
        from .caption_gen import generate_ass, generate_captions_from_segments
        from .clip_service import segments_in_window

        window = segments_in_window(segments, start, end)
        if window:
            work_dir = Path(tempfile.mkdtemp(prefix="short_"))
            captions = generate_captions_from_segments(window, style=style)
            ass_path = work_dir / "captions.ass"
            ass_path.write_text(
                generate_ass(captions, style=style, video_width=width, video_height=height),
                encoding="utf-8",
            )
            (work_dir / "captions.json").write_text(json.dumps(captions), encoding="utf-8")

    burn_in_pass = bool(ass_path) and _has_ass_filter()

    render_audiogram(
        audio_path, out_path, title=title, subtitle=subtitle,
        ass_path=str(ass_path) if burn_in_pass else None,
        fps=fps, hwaccel=hwaccel, aspect=aspect,
        start=start, duration_limit=duration, on_progress=on_progress,
    )

    captioned = burn_in_pass
    caption_error = None

    if ass_path and not burn_in_pass:
        # No libass: composite the captions in a second pass via Pillow.
        from .ffmpeg_service import burn_captions

        tmp_out = str(Path(out_path).with_suffix(".captioned.mp4"))
        try:
            burn_captions(out_path, str(ass_path), tmp_out, style_name=style,
                          on_progress=on_progress)
            shutil.move(tmp_out, out_path)
            captioned = True
        except Exception as e:
            caption_error = str(e)
            if os.path.exists(tmp_out):
                os.unlink(tmp_out)

    if work_dir:
        shutil.rmtree(work_dir, ignore_errors=True)

    return {
        "filename": Path(out_path).name,
        "aspect": aspect,
        "duration": round(duration, 1),
        "captioned": captioned,
        "caption_error": caption_error,
    }


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

    Thin alias so tests can monkeypatch this module. The single implementation
    lives in ffmpeg_service, which the caption burn path also uses.
    """
    from .ffmpeg_service import _has_ass_filter as _impl
    return _impl()
