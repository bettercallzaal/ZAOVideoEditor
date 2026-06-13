"""Auto-mark suggestions from transcript cues."""

from backend.services import auto_marks


def test_excitement_phrase_flagged():
    segs = [{"start": 10.0, "end": 12.0, "text": "Honestly this is the best part, let's go"}]
    out = auto_marks.suggest_marks(segs)
    assert len(out) == 1
    assert out[0]["reason"] == "phrase"
    assert out[0]["at"] == 10.0


def test_brand_mention_flagged():
    segs = [{"start": 5.0, "end": 7.0, "text": "We are building WaveWarZ on Base"}]
    out = auto_marks.suggest_marks(segs)
    assert out[0]["reason"] == "brand"


def test_question_flagged():
    segs = [{"start": 3.0, "end": 5.0, "text": "How do you onboard new artists here?"}]
    out = auto_marks.suggest_marks(segs)
    assert out[0]["reason"] == "question"


def test_short_question_not_flagged():
    segs = [{"start": 0.0, "end": 1.0, "text": "really?"}]
    assert auto_marks.suggest_marks(segs) == []


def test_plain_text_not_flagged():
    segs = [{"start": 0.0, "end": 2.0, "text": "and then we walked to the store"}]
    assert auto_marks.suggest_marks(segs) == []


def test_dedup_within_min_gap():
    segs = [
        {"start": 10.0, "end": 11.0, "text": "let's go"},
        {"start": 12.0, "end": 13.0, "text": "this is huge for WaveWarZ"},
        {"start": 40.0, "end": 41.0, "text": "amazing stuff"},
    ]
    out = auto_marks.suggest_marks(segs, min_gap=15.0)
    assert len(out) == 2          # second (12s) dropped, too close to first (10s)
    assert out[0]["at"] == 10.0
    assert out[1]["at"] == 40.0


def test_note_truncated():
    long = "let's go " + "x" * 100
    out = auto_marks.suggest_marks([{"start": 0.0, "end": 1.0, "text": long}])
    assert out[0]["note"].endswith("...")
    assert len(out[0]["note"]) <= 70


def test_max_suggestions_cap():
    segs = [{"start": float(i * 20), "end": float(i * 20 + 1), "text": "let's go"} for i in range(30)]
    out = auto_marks.suggest_marks(segs, max_suggestions=5)
    assert len(out) == 5


def test_custom_brand_terms():
    segs = [{"start": 0.0, "end": 1.0, "text": "shipping on Acme Protocol today"}]
    out = auto_marks.suggest_marks(segs, brand_terms=["acme protocol"])
    assert out[0]["reason"] == "brand"


def test_sorted_by_time():
    segs = [
        {"start": 50.0, "end": 51.0, "text": "amazing"},
        {"start": 5.0, "end": 6.0, "text": "let's go"},
    ]
    out = auto_marks.suggest_marks(segs)
    assert [m["at"] for m in out] == [5.0, 50.0]
