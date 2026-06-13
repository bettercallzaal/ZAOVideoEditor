"""YouTube caption parsing (json3 -> pipeline segments)."""

from backend.services.youtube_captions import _parse_json3


def test_parse_json3_basic():
    data = {"events": [
        {"tStartMs": 0, "dDurationMs": 2000, "segs": [{"utf8": "hello "}, {"utf8": "world"}]},
        {"tStartMs": 2000, "dDurationMs": 1500, "segs": [{"utf8": "again"}]},
        {"tStartMs": 3500, "dDurationMs": 500, "segs": [{"utf8": "\n"}]},  # skipped
    ]}
    segs = _parse_json3(data)
    assert len(segs) == 2
    assert segs[0]["text"] == "hello world"
    assert segs[0]["start"] == 0.0 and segs[0]["end"] == 2.0
    assert segs[1]["text"] == "again"


def test_parse_json3_word_offsets():
    data = {"events": [
        {"tStartMs": 1000, "dDurationMs": 2000, "segs": [
            {"utf8": "one", "tOffsetMs": 0},
            {"utf8": " "},
            {"utf8": "two", "tOffsetMs": 1000},
        ]},
    ]}
    segs = _parse_json3(data)
    words = segs[0]["words"]
    assert words[0]["word"] == "one" and words[0]["start"] == 1.0
    assert words[1]["word"] == "two" and words[1]["start"] == 2.0
    # first word's end snapped to next word's start
    assert words[0]["end"] == 2.0


def test_parse_json3_empty():
    assert _parse_json3({"events": []}) == []
