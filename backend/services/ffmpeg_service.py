import subprocess
import json
import os
import shutil
from pathlib import Path


def get_video_info(video_path: str) -> dict:
    """Get video metadata using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return json.loads(result.stdout)


def get_video_params(video_path: str) -> dict:
    """Extract resolution, fps, codec info from video."""
    info = get_video_info(video_path)
    video_stream = None
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            video_stream = s
            break
    if not video_stream:
        raise RuntimeError("No video stream found")

    fps_parts = video_stream.get("r_frame_rate", "30/1").split("/")
    fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 and float(fps_parts[1]) != 0 else 30.0

    return {
        "width": int(video_stream.get("width", 1920)),
        "height": int(video_stream.get("height", 1080)),
        "fps": fps,
        "codec": video_stream.get("codec_name", "h264"),
        "duration": float(info.get("format", {}).get("duration", 0)),
    }


def convert_to_match(input_path: str, output_path: str, target_params: dict):
    """Convert a video to match target resolution, fps, and codec."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"scale={target_params['width']}:{target_params['height']}:force_original_aspect_ratio=decrease,pad={target_params['width']}:{target_params['height']}:(ow-iw)/2:(oh-ih)/2",
        "-r", str(target_params["fps"]),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-pix_fmt", "yuv420p",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg convert failed: {result.stderr}")


def assemble_videos(parts: list[str], output_path: str, main_params: dict):
    """Concatenate video parts using ffmpeg concat demuxer."""
    processing_dir = os.path.dirname(output_path)
    prepared_parts = []

    for i, part in enumerate(parts):
        part_params = get_video_params(part)
        needs_convert = (
            part_params["width"] != main_params["width"] or
            part_params["height"] != main_params["height"] or
            abs(part_params["fps"] - main_params["fps"]) > 0.5
        )

        if needs_convert:
            converted = os.path.join(processing_dir, f"converted_part_{i}.mp4")
            convert_to_match(part, converted, main_params)
            prepared_parts.append(converted)
        else:
            # Re-encode to ensure compatible streams for concat
            reencoded = os.path.join(processing_dir, f"reencoded_part_{i}.mp4")
            cmd = [
                "ffmpeg", "-y", "-i", part,
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-pix_fmt", "yuv420p",
                "-r", str(main_params["fps"]),
                reencoded
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg re-encode failed: {result.stderr}")
            prepared_parts.append(reencoded)

    # Create concat file
    concat_file = os.path.join(processing_dir, "concat_list.txt")
    with open(concat_file, "w") as f:
        for part in prepared_parts:
            f.write(f"file '{part}'\n")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-c", "copy",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed: {result.stderr}")

    # Cleanup temp files
    for part in prepared_parts:
        if "converted_part_" in part or "reencoded_part_" in part:
            os.remove(part)
    os.remove(concat_file)


def extract_audio(video_path: str, audio_path: str):
    """Extract audio from video as WAV."""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {result.stderr}")


def burn_captions(video_path: str, ass_path: str, output_path: str,
                  style_name: str = "classic", on_progress=None):
    """Burn captions into video.

    Strategy:
    1. Try ffmpeg's ASS subtitle filter (single-pass, fastest) — needs libass.
    2. Fall back to Pillow overlay video approach (single-pass, no libass needed).

    on_progress: optional callback(progress_pct: int, message: str)
    """
    if not os.path.exists(ass_path):
        shutil.copy2(video_path, output_path)
        return

    # Try ASS filter first
    if _has_ass_filter():
        if on_progress:
            on_progress(15, "Burning captions (ASS filter)...")
        escaped_ass = str(ass_path).replace("\\", "\\\\").replace(":", "\\:")
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"ass='{escaped_ass}'",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "copy", "-pix_fmt", "yuv420p",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return

    # Fallback: Pillow renders a transparent overlay video, ffmpeg composites in one pass
    _burn_captions_pillow(video_path, ass_path, output_path, style_name, on_progress)


def _has_ass_filter() -> bool:
    """Check if ffmpeg has the ASS subtitle filter (needs libass)."""
    result = subprocess.run(
        ["ffmpeg", "-filters"], capture_output=True, text=True,
    )
    return "ass" in result.stdout.split() if result.returncode == 0 else False


def _burn_captions_pillow(video_path: str, ass_path: str, output_path: str,
                          style_name: str = "classic", on_progress=None):
    """Burn captions using Pillow-rendered overlay frames piped to ffmpeg.

    Generates transparent PNG frames for an overlay video via pipe,
    then composites with the source video in a single ffmpeg pass.
    No temp files on disk, no multi-batch re-encoding.
    """
    import tempfile
    from PIL import Image, ImageDraw, ImageFont
    from .caption_gen import get_style

    captions_json = os.path.join(os.path.dirname(ass_path), "captions.json")
    with open(captions_json) as f:
        captions = json.load(f)

    if not captions:
        shutil.copy2(video_path, output_path)
        return

    style = get_style(style_name)
    params = get_video_params(video_path)
    width, height = params["width"], params["height"]
    fps = params["fps"]
    duration = params["duration"]
    total_frames = int(duration * fps)

    font_path = _find_font(bold=style.get("font_weight") == "bold")
    font_size = max(28, int(height * style["font_size_ratio"]))
    try:
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    text_color = _hex_to_rgba(style["text_color"])
    outline_color = _hex_to_rgba(style["outline_color"]) if style.get("outline_color") else None
    outline_width = style.get("outline_width", 0)
    bg_color = _hex_to_rgba(style["bg_color"], style.get("bg_opacity", 255)) if style.get("bg_color") else None
    highlight_color = _hex_to_rgba(style.get("highlight_color", "#FFFFFF")) if style.get("word_highlight") else None
    uppercase = style.get("uppercase", False)
    margin_bottom = max(30, int(height * style["margin_bottom_pct"]))
    pad_x = style.get("padding_x", 0)
    pad_y = style.get("padding_y", 0)
    corner_radius = style.get("corner_radius", 0)
    word_highlight = style.get("word_highlight", False)

    # Pre-render unique caption images (much fewer than total frames)
    # For highlight style: one image per word per caption
    # For standard: one image per caption
    caption_images = {}  # key -> PIL Image (RGBA)

    for i, cap in enumerate(captions):
        cap_text = cap["text"].upper() if uppercase else cap["text"]

        if word_highlight and "word_timing" in cap and cap["word_timing"]:
            for wi, wt in enumerate(cap["word_timing"]):
                words_display = []
                for wt2 in cap["word_timing"]:
                    w = wt2["word"].upper() if uppercase else wt2["word"]
                    words_display.append(w)
                key = f"{i}_w{wi}"
                caption_images[key] = _render_highlight_image(
                    width, height, font, words_display, wi,
                    text_color, highlight_color, outline_color, outline_width,
                    margin_bottom,
                )
        else:
            key = str(i)
            caption_images[key] = _render_caption_image(
                width, height, font, cap_text,
                text_color, outline_color, outline_width,
                bg_color, margin_bottom, pad_x, pad_y, corner_radius,
            )

    # Build a timeline: for each frame, which caption image to show
    # This is a sorted list of (start_time, end_time, image_key)
    timeline = []
    for i, cap in enumerate(captions):
        if word_highlight and "word_timing" in cap and cap["word_timing"]:
            for wi, wt in enumerate(cap["word_timing"]):
                timeline.append((wt["start"], wt["end"], f"{i}_w{wi}"))
        else:
            timeline.append((cap["start"], cap["end"], str(i)))
    timeline.sort()

    # Pipe overlay frames into ffmpeg
    blank_raw = bytes(width * height * 4)  # transparent RGBA frame

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-f", "rawvideo", "-pix_fmt", "rgba",
        "-s", f"{width}x{height}", "-r", str(fps),
        "-i", "pipe:0",
        "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto",
        "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy", "-pix_fmt", "yuv420p",
        "-shortest",
        output_path,
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    if on_progress:
        on_progress(15, f"Rendering {len(caption_images)} caption overlays...")

    def _frames():
        tl_idx = 0  # current position in timeline
        for frame_num in range(total_frames):
            t = frame_num / fps
            while tl_idx < len(timeline) and timeline[tl_idx][1] < t:
                tl_idx += 1
            active_key = None
            for j in range(tl_idx, len(timeline)):
                start, end, key = timeline[j]
                if start > t:
                    break
                if start <= t <= end:
                    active_key = key
                    break
            yield caption_images[active_key].tobytes() if (active_key and active_key in caption_images) else blank_raw

    pipe_broke = _write_overlay_frames(proc, _frames(), total_frames, on_progress)
    _finish_overlay_pipe(proc, pipe_broke)


def _write_overlay_frames(proc, frames, total_frames=0, on_progress=None) -> bool:
    """Feed raw RGBA overlay frames to ffmpeg's stdin.

    ffmpeg can exit early (its own error, or -shortest reaching the audio end),
    which closes the pipe mid-write. We stop feeding rather than crash on
    BrokenPipeError, and let the caller inspect the exit code. Returns True if
    the pipe broke before all frames were written.
    """
    last_pct = 0
    for i, frame in enumerate(frames):
        try:
            proc.stdin.write(frame)
        except (BrokenPipeError, OSError):
            return True
        if on_progress and total_frames > 0:
            pct = 15 + int(80 * i / total_frames)
            if pct >= last_pct + 5:
                last_pct = pct
                on_progress(pct, f"Burning captions... {pct}%")
    return False


def _finish_overlay_pipe(proc, pipe_broke: bool):
    """Close the pipe and wait; raise only if ffmpeg actually failed.

    An early pipe close with exit code 0 (e.g. -shortest) is a valid output.
    """
    try:
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    _, stderr = proc.communicate()
    if proc.returncode != 0:
        msg = stderr.decode(errors="replace") if stderr else ""
        raise RuntimeError(f"ffmpeg caption burn failed: {msg}")


def _render_caption_image(width, height, font, text,
                          text_color, outline_color, outline_width,
                          bg_color, margin_bottom, pad_x, pad_y, corner_radius):
    """Render a single caption as a transparent RGBA PIL Image."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    if bg_color:
        box_w = tw + pad_x * 2
        box_h = th + pad_y * 2
        box_x = (width - box_w) // 2
        box_y = height - margin_bottom - box_h
        text_x = box_x + pad_x
        text_y = box_y + pad_y
        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_w, box_y + box_h],
            radius=corner_radius, fill=bg_color,
        )
    else:
        text_x = (width - tw) // 2
        text_y = height - margin_bottom - th

    if outline_color and outline_width > 0:
        _draw_text_outline(draw, text_x, text_y, text, font, outline_color, outline_width)

    draw.text((text_x, text_y), text, font=font, fill=text_color)
    return img


def _render_highlight_image(width, height, font, words, active_idx,
                            inactive_color, active_color, outline_color,
                            outline_width, margin_bottom):
    """Render a caption with one word highlighted as a transparent RGBA PIL Image."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    full_text = " ".join(words)
    bbox = draw.textbbox((0, 0), full_text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    start_x = (width - tw) // 2
    text_y = height - margin_bottom - th

    if outline_color and outline_width > 0:
        _draw_text_outline(draw, start_x, text_y, full_text, font, outline_color, outline_width)

    x = start_x
    for i, word in enumerate(words):
        color = active_color if i == active_idx else inactive_color
        draw.text((x, text_y), word, font=font, fill=color)
        word_w = draw.textbbox((0, 0), word + " ", font=font)[2]
        x += word_w

    return img


def _draw_text_outline(draw, x, y, text, font, color, width):
    """Draw text outline by rendering at offsets around the position."""
    for dx in range(-width, width + 1):
        for dy in range(-width, width + 1):
            if dx * dx + dy * dy <= width * width:
                draw.text((x + dx, y + dy), text, font=font, fill=color)


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple:
    """Convert hex color to RGBA tuple."""
    if not hex_color:
        return (255, 255, 255, alpha)
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (r, g, b, alpha)


def _find_font(bold: bool = True) -> str:
    """Find a suitable font for caption rendering."""
    if bold:
        bold_candidates = [
            os.path.expanduser("~/Library/Fonts/Montserrat-Bold.ttf"),
            os.path.expanduser("~/Library/Fonts/Montserrat-ExtraBold.ttf"),
            "/Library/Fonts/Montserrat-Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica Bold.ttc",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/System/Library/Fonts/SFNS.ttf",
        ]
        for path in bold_candidates:
            if os.path.exists(path):
                return path
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNS.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def copy_without_reencode(input_path: str, output_path: str):
    """Copy video without re-encoding."""
    shutil.copy2(input_path, output_path)
