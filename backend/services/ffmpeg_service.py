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


def burn_captions(video_path: str, ass_path: str, output_path: str):
    """Burn captions into video using Pillow-rendered PNG overlays.

    Works without libass/drawtext by:
    1. Rendering each unique caption as a transparent PNG
    2. Using ffmpeg overlay filter with enable expressions to show each at the right time
    Processes captions in batches to avoid ffmpeg filter complexity limits.
    """
    import tempfile
    from PIL import Image, ImageDraw, ImageFont

    captions_json = os.path.join(os.path.dirname(ass_path), "captions.json")
    with open(captions_json) as f:
        captions = json.load(f)

    if not captions:
        # No captions — just copy the video
        shutil.copy2(video_path, output_path)
        return

    theme = _parse_ass_theme(ass_path)
    params = get_video_params(video_path)
    width, height = params["width"], params["height"]

    font_path = _find_font()
    font_size = max(28, min(42, int(height / 27)))

    try:
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    text_color = theme.get("text_color", (20, 30, 39, 255))
    bg_color = theme.get("bg_color", (224, 221, 170, 255))
    margin_bottom = max(30, int(height * 0.05))

    with tempfile.TemporaryDirectory() as tmpdir:
        # Render each caption as a transparent PNG
        png_paths = []
        for i, cap in enumerate(captions):
            text = cap["text"]
            img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]

            pad_x, pad_y = 16, 8
            box_w = tw + pad_x * 2
            box_h = th + pad_y * 2
            box_x = (width - box_w) // 2
            box_y = height - margin_bottom - box_h

            draw.rounded_rectangle(
                [box_x, box_y, box_x + box_w, box_y + box_h],
                radius=6, fill=bg_color,
            )
            draw.text((box_x + pad_x, box_y + pad_y), text, font=font, fill=text_color)

            png_path = os.path.join(tmpdir, f"cap_{i:05d}.png")
            img.save(png_path)
            png_paths.append(png_path)

        # Process in batches to avoid ffmpeg filter graph limits
        # ffmpeg can handle ~50-80 inputs comfortably
        BATCH_SIZE = 50
        current_input = video_path

        for batch_start in range(0, len(captions), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(captions))
            batch_captions = captions[batch_start:batch_end]
            batch_pngs = png_paths[batch_start:batch_end]
            is_last_batch = batch_end >= len(captions)

            batch_output = output_path if is_last_batch else os.path.join(tmpdir, f"pass_{batch_start}.mp4")

            # Build ffmpeg command with overlay chain
            cmd = ["ffmpeg", "-y", "-i", current_input]
            for png in batch_pngs:
                cmd.extend(["-i", png])

            # Build filter chain: [0:v][1:v]overlay=enable='between(t,s,e)'[v1]; [v1][2:v]overlay=...
            filters = []
            prev = "0:v"
            for j, cap in enumerate(batch_captions):
                input_idx = j + 1
                out_label = f"v{j + 1}"
                start = cap["start"]
                end = cap["end"]
                filters.append(
                    f"[{prev}][{input_idx}:v]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'[{out_label}]"
                )
                prev = out_label

            filter_str = ";".join(filters)

            cmd.extend([
                "-filter_complex", filter_str,
                "-map", f"[{prev}]",
                "-map", "0:a?",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-c:a", "copy",
                "-pix_fmt", "yuv420p",
                batch_output,
            ])

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg caption burn failed: {result.stderr}")

            # Clean up intermediate pass files
            if current_input != video_path and os.path.exists(current_input):
                os.remove(current_input)
            current_input = batch_output


def _parse_ass_theme(ass_path: str) -> dict:
    """Extract color info from ASS file style line."""
    theme = {
        "text_color": (20, 30, 39, 255),     # #141e27
        "bg_color": (224, 221, 170, 255),     # #e0ddaa
    }
    try:
        with open(ass_path) as f:
            for line in f:
                if line.startswith("Style: Default,"):
                    parts = line.split(",")
                    if len(parts) > 3:
                        # PrimaryColour is parts[3], BackColour is parts[7]
                        primary = parts[3].strip()  # &H00BBGGRR
                        back = parts[7].strip()
                        theme["text_color"] = _ass_color_to_rgba(primary)
                        theme["bg_color"] = _ass_color_to_rgba(back)
    except Exception:
        pass
    return theme


def _ass_color_to_rgba(color_str: str) -> tuple:
    """Convert ASS color &H00BBGGRR to RGBA tuple."""
    try:
        color_str = color_str.replace("&H", "").replace("&h", "")
        color_str = color_str.lstrip("0") or "0"
        val = int(color_str, 16)
        r = val & 0xFF
        g = (val >> 8) & 0xFF
        b = (val >> 16) & 0xFF
        return (r, g, b, 255)
    except Exception:
        return (255, 255, 255, 255)


def _find_font() -> str:
    """Find a suitable font for caption rendering."""
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def copy_without_reencode(input_path: str, output_path: str):
    """Copy video without re-encoding."""
    shutil.copy2(input_path, output_path)
