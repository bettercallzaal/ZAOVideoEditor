import re
import json
from pathlib import Path


# Caption theme definitions
THEMES = {
    "theme_a": {
        "text_color": "#141e27",
        "bg_color": "#e0ddaa",
        "font_size": 36,
        "name": "Dark on Light",
    },
    "theme_b": {
        "text_color": "#e0ddaa",
        "bg_color": "#141e27",
        "font_size": 36,
        "name": "Light on Dark",
    },
}

MAX_WORDS_PER_CAPTION = 6
MIN_WORDS_PER_CAPTION = 3


def split_text_to_captions(text: str, start: float, end: float, words: list = None) -> list:
    """Split a segment into single-line captions of 3-6 words."""
    if words and len(words) > 0:
        return _split_with_word_timing(text, words)
    else:
        return _split_with_even_timing(text, start, end)


def _split_with_word_timing(text: str, words: list) -> list:
    """Split using word-level timestamps."""
    captions = []
    current_words = []
    current_start = None

    for w in words:
        word_text = w["word"].strip()
        if not word_text:
            continue

        if current_start is None:
            current_start = w["start"]
        current_words.append(word_text)

        if len(current_words) >= MAX_WORDS_PER_CAPTION:
            caption_text = " ".join(current_words)
            captions.append({
                "start": current_start,
                "end": w["end"],
                "text": caption_text,
            })
            current_words = []
            current_start = None

    # Remaining words
    if current_words:
        caption_text = " ".join(current_words)
        end_time = words[-1]["end"] if words else 0
        captions.append({
            "start": current_start,
            "end": end_time,
            "text": caption_text,
        })

    return captions


def _split_with_even_timing(text: str, start: float, end: float) -> list:
    """Split with evenly distributed timing when word timestamps unavailable."""
    all_words = text.split()
    if not all_words:
        return []

    captions = []
    duration = end - start
    total_words = len(all_words)
    time_per_word = duration / total_words if total_words > 0 else 0

    i = 0
    while i < total_words:
        chunk_size = min(MAX_WORDS_PER_CAPTION, total_words - i)
        # Avoid leaving orphan words
        remaining = total_words - i - chunk_size
        if 0 < remaining < MIN_WORDS_PER_CAPTION:
            chunk_size = max(MIN_WORDS_PER_CAPTION, (total_words - i) // 2)

        chunk = all_words[i:i + chunk_size]
        cap_start = start + i * time_per_word
        cap_end = start + (i + chunk_size) * time_per_word

        captions.append({
            "start": round(cap_start, 3),
            "end": round(cap_end, 3),
            "text": " ".join(chunk),
        })
        i += chunk_size

    return captions


def generate_captions_from_segments(segments: list) -> list:
    """Generate single-line captions from transcript segments."""
    all_captions = []
    caption_id = 0

    for seg in segments:
        seg_captions = split_text_to_captions(
            seg["text"],
            seg["start"],
            seg["end"],
            seg.get("words", []),
        )
        for cap in seg_captions:
            cap["id"] = caption_id
            caption_id += 1
            all_captions.append(cap)

    return all_captions


def format_timestamp_srt(seconds: float) -> str:
    """Format seconds to SRT timestamp: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_timestamp_ass(seconds: float) -> str:
    """Format seconds to ASS timestamp: H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def generate_srt(captions: list) -> str:
    """Generate SRT file content."""
    lines = []
    for i, cap in enumerate(captions):
        lines.append(str(i + 1))
        lines.append(f"{format_timestamp_srt(cap['start'])} --> {format_timestamp_srt(cap['end'])}")
        lines.append(cap["text"])
        lines.append("")
    return "\n".join(lines)


def hex_to_ass_color(hex_color: str) -> str:
    """Convert hex color (#RRGGBB) to ASS color (&H00BBGGRR)."""
    hex_color = hex_color.lstrip("#")
    r = hex_color[0:2]
    g = hex_color[2:4]
    b = hex_color[4:6]
    return f"&H00{b.upper()}{g.upper()}{r.upper()}"


def generate_ass(captions: list, theme: str = "theme_a", video_width: int = 1920, video_height: int = 1080) -> str:
    """Generate ASS subtitle file content."""
    t = THEMES[theme]
    text_color = hex_to_ass_color(t["text_color"])
    bg_color = hex_to_ass_color(t["bg_color"])
    font_size = t["font_size"]

    # Bottom margin: small (about 40px from bottom)
    margin_v = 40

    header = f"""[Script Info]
Title: ZAO Video Editor Captions
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},{text_color},&H000000FF,{bg_color},{bg_color},-1,0,0,0,100,100,0,0,3,2,0,2,20,20,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""

    events = []
    for cap in captions:
        start = format_timestamp_ass(cap["start"])
        end = format_timestamp_ass(cap["end"])
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{cap['text']}")

    return header + "\n" + "\n".join(events) + "\n"


def save_captions(captions: list, output_path: str):
    """Save captions data to JSON."""
    with open(output_path, "w") as f:
        json.dump(captions, f, indent=2)
