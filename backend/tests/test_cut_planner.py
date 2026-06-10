"""Cut planning: filler/gap/bleed/false-start ranges + keep-range math."""

from backend.services.cut_planner import (
    plan_filler_cuts, plan_gap_cuts, plan_bleed_flags, build_edit_sheet,
    keep_ranges, _merge_overlaps,
)


def _seg(id, start, end, text, words):
    return {"id": id, "start": start, "end": end, "text": text, "words": words}


def test_filler_cuts_only_hard_fillers_enabled():
    segs = [_seg(0, 0, 3, "um hello you know there", [
        {"word": "um", "start": 0.0, "end": 0.3},
        {"word": "hello", "start": 0.4, "end": 0.9},
        {"word": "you", "start": 1.0, "end": 1.2},
        {"word": "know", "start": 1.2, "end": 1.4},
        {"word": "there", "start": 1.5, "end": 1.9},
    ])]
    cuts = plan_filler_cuts(segs)
    # "um" is cut; cadence "you know" is NOT (conservative default)
    assert any(c["text"] == "um" for c in cuts)
    assert all(c["type"] == "filler" and c["enabled"] for c in cuts)
    assert not any("know" in c.get("text", "") for c in cuts)


def test_gap_cuts_trigger_on_long_pause():
    segs = [_seg(0, 0, 10, "a b", [
        {"word": "a", "start": 0.0, "end": 0.5},
        {"word": "b", "start": 6.0, "end": 6.5},  # 5.5s gap
    ])]
    cuts = plan_gap_cuts(segs)
    assert len(cuts) == 1
    assert cuts[0]["type"] == "gap" and cuts[0]["enabled"]
    assert cuts[0]["start"] > 0.5 and cuts[0]["end"] < 6.0  # keeps padding


def test_gap_cuts_ignore_short_pause():
    segs = [_seg(0, 0, 2, "a b", [
        {"word": "a", "start": 0.0, "end": 0.5},
        {"word": "b", "start": 1.0, "end": 1.5},  # 0.5s gap < threshold
    ])]
    assert plan_gap_cuts(segs) == []


def test_bleed_flags_suggested_not_enabled():
    segs = [_seg(0, 0, 2, "intro bleed", []), _seg(1, 50, 52, "outro bleed", [])]
    flags = plan_bleed_flags(segs)
    assert len(flags) == 2
    assert all(f["type"] == "bleed" and not f["enabled"] for f in flags)


def test_keep_ranges_inverts_enabled_cuts():
    cuts = [
        {"start": 2, "end": 4, "enabled": True},
        {"start": 5, "end": 6, "enabled": False},  # disabled -> ignored
    ]
    assert keep_ranges(10.0, cuts) == [(0.0, 2.0), (4.0, 10.0)]


def test_keep_ranges_all_kept_when_nothing_enabled():
    assert keep_ranges(10.0, [{"start": 2, "end": 4, "enabled": False}]) == [(0.0, 10.0)]


def test_merge_overlaps_combines_enabled():
    cuts = [
        {"start": 1, "end": 3, "enabled": True, "text": "a"},
        {"start": 2, "end": 4, "enabled": True, "text": "b"},
        {"start": 9, "end": 9.5, "enabled": False, "text": "s"},
    ]
    merged = _merge_overlaps(cuts)
    enabled = [c for c in merged if c["enabled"]]
    assert len(enabled) == 1
    assert enabled[0]["start"] == 1 and enabled[0]["end"] == 4


def test_build_edit_sheet_structure():
    segs = [_seg(0, 0, 3, "um hi", [
        {"word": "um", "start": 0.0, "end": 0.3},
        {"word": "hi", "start": 0.4, "end": 0.8},
    ])]
    sheet = build_edit_sheet(segs, 3.0)
    assert sheet["duration"] == 3.0
    assert all({"start", "end", "type", "enabled", "source"} <= set(c) for c in sheet["cuts"])
