"""Live clip-marking: marks during a stream become clip ranges from the VOD."""

from backend.services import live_marks


def test_start_session_writes_state(tmp_path):
    state = live_marks.start_session(tmp_path, started_at=1000.0)
    assert state["started_at"] == 1000.0
    assert state["marks"] == []
    assert (tmp_path / "marks.json").exists()


def test_add_mark_computes_seconds_from_start(tmp_path):
    live_marks.start_session(tmp_path, started_at=1000.0)
    m = live_marks.add_mark(tmp_path, note="fire moment", now=1075.4)
    assert m["at"] == 75.4
    assert m["note"] == "fire moment"


def test_add_mark_explicit_at_wins(tmp_path):
    live_marks.start_session(tmp_path, started_at=1000.0)
    m = live_marks.add_mark(tmp_path, note="manual", now=9999.0, at=42.0)
    assert m["at"] == 42.0


def test_marks_stay_sorted(tmp_path):
    live_marks.start_session(tmp_path, started_at=0.0)
    live_marks.add_mark(tmp_path, at=30.0)
    live_marks.add_mark(tmp_path, at=10.0)
    live_marks.add_mark(tmp_path, at=20.0)
    ats = [m["at"] for m in live_marks.get_state(tmp_path)["marks"]]
    assert ats == [10.0, 20.0, 30.0]


def test_add_mark_without_start_stamps_now(tmp_path):
    # No start_session called; first mark seeds started_at and lands at ~0.
    m = live_marks.add_mark(tmp_path, note="late start", now=500.0)
    assert m["at"] == 0.0


def test_get_state_missing_file(tmp_path):
    state = live_marks.get_state(tmp_path)
    assert state == {"started_at": None, "marks": []}


def test_marks_to_highlights_windows_around_mark():
    marks = [{"at": 100.0, "note": "the drop"}]
    hl = live_marks.marks_to_highlights(marks, duration=600.0, pre=20.0, post=40.0)
    assert len(hl) == 1
    assert hl[0]["start"] == 80.0
    assert hl[0]["end"] == 140.0
    assert hl[0]["duration"] == 60.0
    assert hl[0]["title"] == "the drop"
    assert hl[0]["source"] == "live-mark"


def test_marks_to_highlights_clamps_to_duration():
    marks = [{"at": 5.0, "note": ""}, {"at": 595.0, "note": ""}]
    hl = live_marks.marks_to_highlights(marks, duration=600.0, pre=20.0, post=40.0)
    assert hl[0]["start"] == 0.0          # clamped low
    assert hl[1]["end"] == 600.0          # clamped high
    assert hl[0]["title"] == "Marked moment 1"


def test_marks_to_highlights_offset_shifts_window():
    marks = [{"at": 100.0, "note": "x"}]
    hl = live_marks.marks_to_highlights(marks, duration=600.0, pre=10.0, post=10.0, offset=15.0)
    # center = 100 + 15 = 115
    assert hl[0]["start"] == 105.0
    assert hl[0]["end"] == 125.0


def test_marks_to_highlights_drops_too_short():
    # duration clamps both ends to the same tiny window -> dropped (< 2s).
    marks = [{"at": 0.5, "note": ""}]
    hl = live_marks.marks_to_highlights(marks, duration=1.0, pre=0.1, post=0.1)
    assert hl == []


def test_marks_to_highlights_no_duration_no_clamp():
    marks = [{"at": 100.0, "note": ""}]
    hl = live_marks.marks_to_highlights(marks, duration=0.0, pre=20.0, post=40.0)
    assert hl[0]["end"] == 140.0
