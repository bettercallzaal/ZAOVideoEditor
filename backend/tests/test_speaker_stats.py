"""Speaker talk-time analytics."""

from backend.services import speaker_stats


def test_talk_time_per_speaker_and_share():
    segs = [
        {"start": 0, "end": 30, "speaker": "Alice"},
        {"start": 30, "end": 40, "speaker": "Bob"},
        {"start": 40, "end": 70, "speaker": "Alice"},
    ]
    out = speaker_stats.talk_time(segs)
    assert out["total_seconds"] == 70.0
    assert out["speakers"][0]["speaker"] == "Alice"  # most talk time
    assert out["speakers"][0]["seconds"] == 60.0
    assert out["speakers"][0]["segments"] == 2
    assert abs(out["speakers"][0]["share"] - 0.857) < 0.01
    assert out["speakers"][1]["speaker"] == "Bob"


def test_unlabeled_segments_grouped_unknown():
    segs = [
        {"start": 0, "end": 10, "speaker": "Alice"},
        {"start": 10, "end": 20},  # no speaker
    ]
    out = speaker_stats.talk_time(segs)
    names = {s["speaker"] for s in out["speakers"]}
    assert "Unknown" in names


def test_all_unknown_returns_no_breakdown():
    segs = [{"start": 0, "end": 10}, {"start": 10, "end": 20}]
    out = speaker_stats.talk_time(segs)
    assert out["speakers"] == []
    assert out["total_seconds"] == 20.0


def test_empty():
    out = speaker_stats.talk_time([])
    assert out == {"total_seconds": 0.0, "speakers": []}


def test_bad_timestamps_skipped():
    segs = [
        {"start": 0, "end": 10, "speaker": "Alice"},
        {"start": "x", "end": "y", "speaker": "Bob"},
    ]
    out = speaker_stats.talk_time(segs)
    assert out["total_seconds"] == 10.0
    assert all(s["speaker"] != "Bob" for s in out["speakers"])
