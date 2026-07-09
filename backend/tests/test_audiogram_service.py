"""Audiogram bridge: audio-only input gets a real video stream.

Fixtures are synthesized with ffmpeg so the suite carries no binary files. The
important case is a .mp4 that holds only an audio stream, which is what a Juke
space export actually looks like - extension sniffing gets it wrong.
"""

import subprocess

import pytest

from backend.services import audiogram_service as ag


def _has_ffmpeg() -> bool:
    from shutil import which
    return which("ffmpeg") is not None and which("ffprobe") is not None


pytestmark = pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg/ffprobe not on PATH")


def _make_audio(path, seconds=2, container_ext=None):
    """Synthesize a tone. container_ext lets us hide audio inside a .mp4."""
    out = str(path)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:a", "aac" if out.endswith(".mp4") else "libmp3lame", out],
        check=True, capture_output=True,
    )
    return out


def _make_video(path, seconds=2):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=320x240:rate=10",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )
    return str(path)


def _streams(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    import json
    return json.loads(out.stdout)["streams"]


def test_probe_reports_audio_only(tmp_path):
    audio = _make_audio(tmp_path / "a.mp3")
    info = ag.probe_streams(audio)
    assert info["has_audio"] is True
    assert info["has_video"] is False
    assert info["duration"] == pytest.approx(2.0, abs=0.3)


def test_audio_only_mp4_is_detected_despite_extension(tmp_path):
    """A Juke space export is a .mp4 with no video stream. Extension lies."""
    disguised = _make_audio(tmp_path / "space.mp4")
    assert ag.is_audio_only(disguised) is True


def test_real_video_is_not_audio_only(tmp_path):
    video = _make_video(tmp_path / "v.mp4")
    assert ag.is_audio_only(video) is False


def test_probe_raises_on_garbage(tmp_path):
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"not media")
    with pytest.raises(RuntimeError):
        ag.probe_streams(str(junk))


def test_render_audiogram_produces_1080p_video(tmp_path):
    audio = _make_audio(tmp_path / "a.mp3")
    out = ag.render_audiogram(audio, str(tmp_path / "out.mp4"), title="Test Space")

    streams = _streams(out)
    kinds = {s["codec_type"] for s in streams}
    assert kinds == {"video", "audio"}

    video = next(s for s in streams if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (ag.WIDTH, ag.HEIGHT)


def test_rendered_audiogram_satisfies_get_video_params(tmp_path):
    """The whole point: the twelve get_video_params() call sites stop failing."""
    from backend.services.ffmpeg_service import get_video_params

    audio = _make_audio(tmp_path / "a.mp3")
    out = ag.render_audiogram(audio, str(tmp_path / "out.mp4"), title="Test")

    params = get_video_params(out)
    assert params["width"] == 1920
    assert params["height"] == 1080


def test_get_video_params_still_fails_on_raw_audio(tmp_path):
    """Guards the premise. If this ever passes, the bridge is unnecessary."""
    from backend.services.ffmpeg_service import get_video_params

    audio = _make_audio(tmp_path / "a.mp3")
    with pytest.raises(RuntimeError, match="No video stream"):
        get_video_params(audio)


def test_render_rejects_input_that_already_has_video(tmp_path):
    video = _make_video(tmp_path / "v.mp4")
    with pytest.raises(RuntimeError, match="already has a video stream"):
        ag.render_audiogram(video, str(tmp_path / "out.mp4"), title="x")


def test_duration_limit_truncates(tmp_path):
    audio = _make_audio(tmp_path / "a.mp3", seconds=6)
    out = ag.render_audiogram(audio, str(tmp_path / "out.mp4"), title="T", duration_limit=2)
    assert ag.probe_streams(out)["duration"] == pytest.approx(2.0, abs=0.4)


def test_ensure_video_track_passes_video_through(tmp_path):
    video = _make_video(tmp_path / "v.mp4")
    result = ag.ensure_video_track(tmp_path, video, title="x")
    assert str(result) == video
    assert not (tmp_path / "processing" / "audiogram.mp4").exists()


def test_ensure_video_track_renders_and_caches(tmp_path):
    audio = _make_audio(tmp_path / "a.mp3")

    first = ag.ensure_video_track(tmp_path, audio, title="Space")
    assert first.name == "audiogram.mp4"
    assert first.exists()

    stamp = first.stat().st_mtime_ns
    second = ag.ensure_video_track(tmp_path, audio, title="Space")
    assert second == first
    assert second.stat().st_mtime_ns == stamp, "cached audiogram was re-encoded"


def test_build_card_is_1080p(tmp_path):
    from PIL import Image

    card = ag.build_card(str(tmp_path / "card.png"), "A Very Long Space Title That Must Fit",
                         subtitle="with a guest", footer="hosted by @zaal")
    with Image.open(card) as img:
        assert img.size == (ag.WIDTH, ag.HEIGHT)


def test_filtergraph_omits_ass_when_no_captions():
    graph = ag.build_filtergraph(ass_path=None)
    assert "showwaves" in graph
    assert "ass=" not in graph
    assert graph.endswith("[v]")


def test_filtergraph_includes_ass_when_captions_given():
    graph = ag.build_filtergraph(ass_path="/tmp/c.ass")
    assert "ass='/tmp/c.ass'" in graph
    assert graph.endswith("[v]")


def test_filtergraph_escapes_windows_style_and_colon_paths():
    graph = ag.build_filtergraph(ass_path="/tmp/a:b/c.ass")
    assert "a\\:b" in graph


def test_burn_request_without_libass_raises_clear_error(tmp_path, monkeypatch):
    """Better a loud failure than a silently captionless two-hour render."""
    monkeypatch.setattr(ag, "_has_ass_filter", lambda: False)
    audio = _make_audio(tmp_path / "a.mp3")
    with pytest.raises(RuntimeError, match="libass"):
        ag.render_audiogram(audio, str(tmp_path / "o.mp4"), title="t",
                            ass_path=str(tmp_path / "c.ass"))


def test_has_ass_filter_not_fooled_by_lookalike_filters():
    """'allpass', 'bandpass' and 'Pass the source unchanged' all contain 'ass'."""
    result = ag._has_ass_filter()
    assert isinstance(result, bool)

    probe = subprocess.run(["ffmpeg", "-hide_banner", "-h", "filter=ass"],
                           capture_output=True, text=True)
    truth = "Unknown filter" not in (probe.stdout + probe.stderr)
    assert result is truth


def test_srt_drops_zero_length_cues():
    """Whisper loops on music and emits repeated words sharing one timestamp."""
    from backend.services.caption_gen import generate_srt

    caps = [
        {"start": 0.0, "end": 1.5, "text": "real caption"},
        {"start": 2.0, "end": 2.0, "text": "cast, cast, cast"},
        {"start": 3.0, "end": 4.0, "text": "another real one"},
    ]
    srt = generate_srt(caps)
    assert "real caption" in srt
    assert "another real one" in srt
    assert "cast, cast, cast" not in srt
    assert "-->" in srt
    # Surviving cues are renumbered 1..n, with no gap where the bad cue was.
    assert srt.splitlines()[0] == "1"
    assert srt.count("-->") == 2


def test_ass_drops_zero_length_cues():
    from backend.services.caption_gen import generate_ass

    caps = [
        {"start": 0.0, "end": 1.5, "text": "keep me"},
        {"start": 2.0, "end": 2.0, "text": "drop me"},
    ]
    ass = generate_ass(caps)
    assert "keep me" in ass
    assert "drop me" not in ass


def test_drop_degenerate_removes_inverted_cues():
    from backend.services.caption_gen import drop_degenerate

    caps = [
        {"start": 5.0, "end": 1.0, "text": "inverted"},
        {"start": 1.0, "end": 5.0, "text": "fine"},
    ]
    assert [c["text"] for c in drop_degenerate(caps)] == ["fine"]


def test_waveform_uses_sqrt_scale():
    """Linear scale draws conversational speech as a near-flat line."""
    assert "scale=sqrt" in ag.build_filtergraph()
