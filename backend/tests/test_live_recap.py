"""End-of-stream recap from the live transcript."""

import json

import pytest

from backend.services import live_recap


def _fake_gen(segments, project_name):
    return {"recap": f"Recap of {len(segments)} segments for {project_name}",
            "chapters": [{"start": 0, "title": "Intro"}],
            "quotes": [{"text": "let's go"}], "clips": [{"start": 10, "end": 30}]}


def test_builds_and_persists(tmp_path):
    (tmp_path / "live_transcript.json").write_text(json.dumps(
        {"segments": [{"start": 0, "end": 2, "text": "hello"}, {"start": 2, "end": 4, "text": "world"}]}))
    out = live_recap.build_live_recap(tmp_path, project_name="Live Show", generator=_fake_gen)
    assert "2 segments" in out["recap"]
    assert out["source"] == "live-transcript"
    assert out["clips"]
    saved = json.loads((tmp_path / "metadata" / "insights.json").read_text())
    assert saved["recap"] == out["recap"]


def test_no_transcript_raises(tmp_path):
    with pytest.raises(ValueError, match="No live transcript"):
        live_recap.build_live_recap(tmp_path, generator=_fake_gen)


def test_empty_segments_raises(tmp_path):
    (tmp_path / "live_transcript.json").write_text(json.dumps({"segments": []}))
    with pytest.raises(ValueError):
        live_recap.build_live_recap(tmp_path, generator=_fake_gen)


def test_corrupt_transcript_treated_as_empty(tmp_path):
    (tmp_path / "live_transcript.json").write_text("{ broken")
    with pytest.raises(ValueError):
        live_recap.build_live_recap(tmp_path, generator=_fake_gen)


def test_project_name_defaults_to_dir(tmp_path):
    d = tmp_path / "my-live"
    d.mkdir()
    (d / "live_transcript.json").write_text(json.dumps({"segments": [{"start": 0, "end": 1, "text": "x"}]}))
    out = live_recap.build_live_recap(d, generator=_fake_gen)
    assert "my-live" in out["recap"]
