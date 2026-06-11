"""Clip window slicing + per-clip copy fallback (no ffmpeg / no LLM needed)."""

from backend.services.clip_service import segments_in_window
from backend.services.content_gen import generate_clip_copy


def test_window_rebases_to_clip_relative():
    segs = [
        {"start": 10, "end": 20, "text": "a"},
        {"start": 25, "end": 40, "text": "b"},
        {"start": 5, "end": 12, "text": "c"},
    ]
    out = segments_in_window(segs, 10, 30)
    texts = {s["text"]: (round(s["start"], 1), round(s["end"], 1)) for s in out}
    # 'a' fully inside -> 0..10; 'b' clipped to clip end (20); 'c' clipped to 0..2
    assert texts["a"] == (0.0, 10.0)
    assert texts["b"] == (15.0, 20.0)
    assert texts["c"] == (0.0, 2.0)


def test_window_excludes_outside():
    segs = [{"start": 0, "end": 5, "text": "before"}, {"start": 100, "end": 110, "text": "after"}]
    assert segments_in_window(segs, 50, 60) == []


def test_window_rebases_words():
    segs = [{
        "start": 10, "end": 20, "text": "hi there",
        "words": [{"start": 10, "end": 11, "word": "hi"}, {"start": 19, "end": 20, "word": "there"}],
    }]
    out = segments_in_window(segs, 10, 30)
    words = out[0]["words"]
    assert round(words[0]["start"], 1) == 0.0
    assert round(words[1]["end"], 1) == 10.0


def test_clip_copy_fallback_without_llm(monkeypatch):
    # Force "no LLM configured" so we exercise the deterministic fallback.
    monkeypatch.setattr("backend.services.content_gen._get_client", lambda: (None, None))
    copy = generate_clip_copy(
        [{"text": "this is a clip about ZAO"}],
        project_name="demo", fallback_title="Great Moment",
    )
    assert copy["title"] == "Great Moment"
    assert "clip" in copy["caption"]
    assert isinstance(copy["hashtags"], list) and copy["hashtags"]
    assert copy["model"] is None


def test_clip_copy_fallback_empty_segments(monkeypatch):
    monkeypatch.setattr("backend.services.content_gen._get_client", lambda: (None, None))
    copy = generate_clip_copy([], project_name="demo", fallback_title="T")
    assert copy["title"] == "T"
