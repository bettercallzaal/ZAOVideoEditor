"""Subtitle export: SRT and WebVTT from transcript segments.

Every platform takes a sidecar subtitle file - YouTube, Vimeo, X, players, CapCut
and Premiere on import. This turns the (brand-corrected, optionally edited)
transcript into SRT and VTT, reusing the caption splitter so the line lengths
match the burned-in captions.
"""

from .caption_gen import (
    generate_captions_from_segments,
    generate_srt,
    format_timestamp_srt,
)


def _vtt_ts(seconds: float) -> str:
    # WebVTT uses a dot before milliseconds; SRT uses a comma.
    return format_timestamp_srt(seconds).replace(",", ".")


def build_srt(segments: list, style: str = "classic") -> str:
    """SRT content for the given transcript segments."""
    caps = generate_captions_from_segments(segments or [], style=style)
    return generate_srt(caps, style=style)


def build_vtt(segments: list, style: str = "classic") -> str:
    """WebVTT content for the given transcript segments."""
    caps = generate_captions_from_segments(segments or [], style=style)
    lines = ["WEBVTT", ""]
    for i, cap in enumerate(caps):
        lines.append(str(i + 1))
        lines.append(f"{_vtt_ts(cap['start'])} --> {_vtt_ts(cap['end'])}")
        lines.append(cap["text"])
        lines.append("")
    return "\n".join(lines)


def build(segments: list, fmt: str = "srt", style: str = "classic") -> str:
    fmt = (fmt or "srt").lower()
    if fmt == "vtt":
        return build_vtt(segments, style=style)
    if fmt == "srt":
        return build_srt(segments, style=style)
    raise ValueError(f"Unsupported subtitle format: {fmt}")
