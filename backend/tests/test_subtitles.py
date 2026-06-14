"""Subtitle export (SRT / WebVTT)."""

import pytest

from backend.services import subtitles

SEGS = [
    {"start": 0.0, "end": 2.5, "text": "Hello and welcome"},
    {"start": 2.5, "end": 5.0, "text": "to the ZABAL Gamez"},
]


def test_srt_has_numbering_and_arrow():
    out = subtitles.build_srt(SEGS)
    assert out.strip().startswith("1")
    assert "-->" in out
    assert "00:00:00,000" in out
    assert "Hello and welcome" in out


def test_vtt_has_header_and_dot_timestamps():
    out = subtitles.build_vtt(SEGS)
    assert out.startswith("WEBVTT")
    assert "00:00:00.000 -->" in out
    assert "," not in out.split("\n")[2]  # the timestamp line uses a dot, not a comma


def test_build_dispatch():
    assert subtitles.build(SEGS, "srt") == subtitles.build_srt(SEGS)
    assert subtitles.build(SEGS, "vtt") == subtitles.build_vtt(SEGS)


def test_build_rejects_unknown_format():
    with pytest.raises(ValueError):
        subtitles.build(SEGS, "ass")


def test_empty_segments_safe():
    assert subtitles.build_srt([]).strip() == ""
    assert subtitles.build_vtt([]).startswith("WEBVTT")
