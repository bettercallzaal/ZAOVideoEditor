import json
from pathlib import Path


# Caption style definitions
STYLES = {
    "classic": {
        "name": "Classic",
        "description": "Clean white text with black outline",
        "font_weight": "bold",
        "font_size_ratio": 0.05,
        "text_color": "#FFFFFF",
        "outline_color": "#000000",
        "outline_width": 2,
        "bg_color": None,
        "bg_opacity": 0,
        "uppercase": False,
        "margin_bottom_pct": 0.08,
        "padding_x": 0,
        "padding_y": 0,
        "corner_radius": 0,
        "word_highlight": False,
        "max_words": 8,
    },
    "box": {
        "name": "Box",
        "description": "White text on dark semi-transparent box",
        "font_weight": "bold",
        "font_size_ratio": 0.048,
        "text_color": "#FFFFFF",
        "outline_color": None,
        "outline_width": 0,
        "bg_color": "#000000",
        "bg_opacity": 180,
        "uppercase": False,
        "margin_bottom_pct": 0.08,
        "padding_x": 20,
        "padding_y": 10,
        "corner_radius": 8,
        "word_highlight": False,
        "max_words": 8,
    },
    "bold_pop": {
        "name": "Bold Pop",
        "description": "Large bold uppercase with thick outline",
        "font_weight": "bold",
        "font_size_ratio": 0.065,
        "text_color": "#FFFFFF",
        "outline_color": "#000000",
        "outline_width": 3,
        "bg_color": None,
        "bg_opacity": 0,
        "uppercase": True,
        "margin_bottom_pct": 0.12,
        "padding_x": 0,
        "padding_y": 0,
        "corner_radius": 0,
        "word_highlight": False,
        "max_words": 5,
    },
    "highlight": {
        "name": "Highlight",
        "description": "Word-by-word highlight, Hormozi style",
        "font_weight": "bold",
        "font_size_ratio": 0.065,
        "text_color": "#666666",
        "highlight_color": "#FFFFFF",
        "outline_color": "#000000",
        "outline_width": 3,
        "bg_color": None,
        "bg_opacity": 0,
        "uppercase": True,
        "margin_bottom_pct": 0.12,
        "padding_x": 0,
        "padding_y": 0,
        "corner_radius": 0,
        "word_highlight": True,
        "max_words": 5,
    },
    "brand_light": {
        "name": "Brand Light",
        "description": "Dark text on beige background",
        "font_weight": "bold",
        "font_size_ratio": 0.04,
        "text_color": "#141e27",
        "outline_color": None,
        "outline_width": 0,
        "bg_color": "#e0ddaa",
        "bg_opacity": 255,
        "uppercase": False,
        "margin_bottom_pct": 0.05,
        "padding_x": 16,
        "padding_y": 8,
        "corner_radius": 6,
        "word_highlight": False,
        "max_words": 6,
    },
    "brand_dark": {
        "name": "Brand Dark",
        "description": "Beige text on dark background",
        "font_weight": "bold",
        "font_size_ratio": 0.04,
        "text_color": "#e0ddaa",
        "outline_color": None,
        "outline_width": 0,
        "bg_color": "#141e27",
        "bg_opacity": 255,
        "uppercase": False,
        "margin_bottom_pct": 0.05,
        "padding_x": 16,
        "padding_y": 8,
        "corner_radius": 6,
        "word_highlight": False,
        "max_words": 6,
    },
}

# Backwards compatibility mapping
THEME_TO_STYLE = {
    "theme_a": "brand_light",
    "theme_b": "brand_dark",
}


def get_style(style_name: str) -> dict:
    """Get style config, with backwards compatibility for old theme names."""
    style_name = THEME_TO_STYLE.get(style_name, style_name)
    return STYLES.get(style_name, STYLES["classic"])


def split_text_to_captions(text: str, start: float, end: float,
                           words: list = None, max_words: int = 6) -> list:
    """Split a segment into single-line captions."""
    if words and len(words) > 0:
        return _split_with_word_timing(text, words, max_words)
    else:
        return _split_with_even_timing(text, start, end, max_words)


def _split_with_word_timing(text: str, words: list, max_words: int = 6) -> list:
    """Split using word-level timestamps. Preserves per-word timing data."""
    min_words = max(2, max_words // 2)
    captions = []
    current_words = []
    current_word_data = []
    current_start = None

    for w in words:
        word_text = w["word"].strip()
        if not word_text:
            continue

        if current_start is None:
            current_start = w["start"]
        current_words.append(word_text)
        current_word_data.append({
            "word": word_text,
            "start": w["start"],
            "end": w["end"],
        })

        if len(current_words) >= max_words:
            captions.append({
                "start": current_start,
                "end": w["end"],
                "text": " ".join(current_words),
                "word_timing": list(current_word_data),
            })
            current_words = []
            current_word_data = []
            current_start = None

    # Remaining words
    if current_words:
        # Avoid orphan words — merge into previous if too few
        if len(current_words) < min_words and captions:
            prev = captions[-1]
            prev["text"] += " " + " ".join(current_words)
            prev["end"] = words[-1]["end"]
            prev["word_timing"].extend(current_word_data)
        else:
            end_time = words[-1]["end"] if words else 0
            captions.append({
                "start": current_start,
                "end": end_time,
                "text": " ".join(current_words),
                "word_timing": list(current_word_data),
            })

    return captions


def _split_with_even_timing(text: str, start: float, end: float,
                            max_words: int = 6) -> list:
    """Split with evenly distributed timing when word timestamps unavailable."""
    min_words = max(2, max_words // 2)
    all_words = text.split()
    if not all_words:
        return []

    captions = []
    duration = end - start
    total_words = len(all_words)
    time_per_word = duration / total_words if total_words > 0 else 0

    i = 0
    while i < total_words:
        chunk_size = min(max_words, total_words - i)
        remaining = total_words - i - chunk_size
        if 0 < remaining < min_words:
            chunk_size = max(min_words, (total_words - i) // 2)

        chunk = all_words[i:i + chunk_size]
        cap_start = start + i * time_per_word
        cap_end = start + (i + chunk_size) * time_per_word

        # Build synthetic word timing
        word_timing = []
        for k, word in enumerate(chunk):
            ws = cap_start + k * time_per_word
            we = cap_start + (k + 1) * time_per_word
            word_timing.append({"word": word, "start": round(ws, 3), "end": round(we, 3)})

        captions.append({
            "start": round(cap_start, 3),
            "end": round(cap_end, 3),
            "text": " ".join(chunk),
            "word_timing": word_timing,
        })
        i += chunk_size

    return captions


def generate_captions_from_segments(segments: list, style: str = "classic") -> list:
    """Generate single-line captions from transcript segments."""
    style_config = get_style(style)
    max_words = style_config.get("max_words", 6)

    all_captions = []
    caption_id = 0

    for seg in segments:
        seg_captions = split_text_to_captions(
            seg["text"],
            seg["start"],
            seg["end"],
            seg.get("words", []),
            max_words=max_words,
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


def drop_degenerate(captions: list) -> list:
    """Remove zero-length and inverted cues.

    Whisper can loop on music or silence and emit a run of repeated words that
    all share one timestamp, which becomes a cue with start == end. Players and
    YouTube's caption validator reject those, so they never reach a viewer -
    they just make the whole file suspect. Drop them at the boundary.
    """
    return [c for c in captions if c["end"] > c["start"]]


def generate_srt(captions: list, style: str = "classic") -> str:
    """Generate SRT file content."""
    style_config = get_style(style)
    uppercase = style_config.get("uppercase", False)

    lines = []
    for i, cap in enumerate(drop_degenerate(captions)):
        lines.append(str(i + 1))
        lines.append(f"{format_timestamp_srt(cap['start'])} --> {format_timestamp_srt(cap['end'])}")
        text = cap["text"].upper() if uppercase else cap["text"]
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def hex_to_ass_color(hex_color: str) -> str:
    """Convert hex color (#RRGGBB) to ASS color (&H00BBGGRR)."""
    hex_color = hex_color.lstrip("#")
    r = hex_color[0:2]
    g = hex_color[2:4]
    b = hex_color[4:6]
    return f"&H00{b.upper()}{g.upper()}{r.upper()}"


def hex_to_ass_color_alpha(hex_color: str, alpha: int = 0) -> str:
    """Convert hex color to ASS color with alpha (&HAABBGGRR)."""
    hex_color = hex_color.lstrip("#")
    r = hex_color[0:2]
    g = hex_color[2:4]
    b = hex_color[4:6]
    return f"&H{alpha:02X}{b.upper()}{g.upper()}{r.upper()}"


def generate_ass(captions: list, style: str = "classic",
                 video_width: int = 1920, video_height: int = 1080) -> str:
    """Generate ASS subtitle file content with style-specific formatting."""
    s = get_style(style)

    font_size = max(28, int(video_height * s["font_size_ratio"]))
    text_color = hex_to_ass_color(s["text_color"])
    outline_color = hex_to_ass_color(s.get("outline_color") or "#000000")
    outline_width = s.get("outline_width", 0)
    margin_v = max(30, int(video_height * s["margin_bottom_pct"]))
    bold = -1 if s.get("font_weight") == "bold" else 0
    uppercase = s.get("uppercase", False)

    # BorderStyle: 1 = outline+shadow, 3 = opaque box
    if s.get("bg_color") and s.get("bg_opacity", 0) > 0:
        border_style = 3
        bg_ass = hex_to_ass_color(s["bg_color"])
        shadow = 0
    else:
        border_style = 1
        bg_ass = "&H80000000"
        shadow = 1 if outline_width > 0 else 0

    # For highlight style, set secondary color for karaoke
    if s.get("word_highlight"):
        secondary_color = hex_to_ass_color(s.get("highlight_color", "#FFFFFF"))
    else:
        secondary_color = "&H000000FF"

    # Font selection for ASS (external players will use this)
    font_name = "Arial"

    header = f"""[Script Info]
Title: ZAO Video Editor Captions
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{text_color},{secondary_color},{outline_color},{bg_ass},{bold},0,0,0,100,100,0,0,{border_style},{outline_width},{shadow},2,30,30,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""

    events = []
    for cap in drop_degenerate(captions):
        start = format_timestamp_ass(cap["start"])
        end = format_timestamp_ass(cap["end"])
        text = cap["text"].upper() if uppercase else cap["text"]

        # For highlight style, add karaoke tags with word timing
        if s.get("word_highlight") and "word_timing" in cap and cap["word_timing"]:
            karaoke_parts = []
            for wt in cap["word_timing"]:
                duration_cs = max(1, int((wt["end"] - wt["start"]) * 100))
                w = wt["word"].upper() if uppercase else wt["word"]
                karaoke_parts.append(f"{{\\kf{duration_cs}}}{w}")
            text = " ".join(karaoke_parts)

        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    return header + "\n" + "\n".join(events) + "\n"


def save_captions(captions: list, output_path: str):
    """Save captions data to JSON."""
    with open(output_path, "w") as f:
        json.dump(captions, f, indent=2)
