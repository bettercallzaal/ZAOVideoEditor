"""Render service: filter construction, no-op copy path, transcript sync."""

from backend.services import render_service
from backend.services.render_service import _build_concat_filter, render_transcript_after_cuts


def test_concat_filter_builds_trim_and_concat():
    filt = _build_concat_filter([(0.0, 2.0), (4.0, 6.0)])
    assert "trim=0.0:2.0" in filt
    assert "atrim=4.0:6.0" in filt
    assert "concat=n=2:v=1:a=1[outv][outa]" in filt


def test_render_no_enabled_cuts_copies(monkeypatch, tmp_path):
    called = {}
    def fake_copy(src, dst):
        called["src"], called["dst"] = src, dst
        Path = __import__("pathlib").Path
        Path(dst).write_bytes(b"copy")
    monkeypatch.setattr(render_service, "_video_duration", lambda p: 6.0)
    import backend.services.ffmpeg_service as fs
    monkeypatch.setattr(fs, "copy_without_reencode", fake_copy)

    out = tmp_path / "trimmed.mp4"
    sheet = {"duration": 6.0, "cuts": [{"start": 2, "end": 4, "enabled": False}]}
    stats = render_service.render_cuts("src.mp4", sheet, str(out))
    assert stats["removed_seconds"] == 0.0
    assert called["dst"] == str(out)


def test_render_invokes_ffmpeg_for_enabled_cuts(monkeypatch, tmp_path):
    calls = {}
    class R:
        returncode = 0
        stderr = ""
    def fake_run(cmd, **k):
        calls["cmd"] = cmd
        return R()
    monkeypatch.setattr(render_service.subprocess, "run", fake_run)

    sheet = {"duration": 6.0, "cuts": [{"start": 2, "end": 4, "enabled": True}]}
    stats = render_service.render_cuts("src.mp4", sheet, str(tmp_path / "o.mp4"))
    assert stats["removed_seconds"] == 2.0
    assert "-filter_complex" in calls["cmd"]


def test_transcript_after_cuts_drops_cut_words():
    segs = [{
        "id": 0, "start": 0, "end": 4, "text": "um hello there",
        "words": [
            {"word": "um", "start": 0.0, "end": 0.3},
            {"word": "hello", "start": 1.0, "end": 1.5},
            {"word": "there", "start": 2.0, "end": 2.5},
        ],
    }]
    cuts = [{"start": 0.0, "end": 0.4, "enabled": True}]  # cut "um"
    out = render_transcript_after_cuts(segs, cuts)
    assert out[0]["text"] == "hello there"


def test_transcript_after_cuts_drops_fully_cut_segment():
    segs = [
        {"id": 0, "start": 0, "end": 2, "text": "keep", "words": []},
        {"id": 1, "start": 5, "end": 7, "text": "drop", "words": []},
    ]
    out = render_transcript_after_cuts(segs, [{"start": 4.5, "end": 7.5, "enabled": True}])
    assert len(out) == 1 and out[0]["text"] == "keep"


from pathlib import Path  # noqa: E402  (used in monkeypatched closure above)
