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


# --- aspect-native rendering (Shorts) -------------------------------------

def test_aspect_sizes():
    assert ag.aspect_size("16:9") == (1920, 1080)
    assert ag.aspect_size("9:16") == (1080, 1920)
    assert ag.aspect_size("1:1") == (1080, 1080)


def test_unknown_aspect_raises():
    with pytest.raises(ValueError, match="Unsupported aspect"):
        ag.aspect_size("4:3")


def test_portrait_moves_the_waveform_off_the_caption_band():
    """Reusing the landscape ratio drops the waveform behind burned captions."""
    _, _, land_y = ag._wave_geometry(1920, 1080)
    _, _, port_y = ag._wave_geometry(1080, 1920)
    assert land_y / 1080 > 0.6
    assert port_y / 1920 < 0.5


def test_portrait_waveform_is_proportionally_taller():
    _, land_h, _ = ag._wave_geometry(1920, 1080)
    _, port_h, _ = ag._wave_geometry(1080, 1920)
    assert port_h / 1080 > land_h / 1920, "a narrow waveform reads as a hairline"


def test_filtergraph_uses_draw_full():
    """draw=scale makes strokes translucent whenever samples-per-column != 1.

    48000/30 = 1600 samples. At 1600px wide that is exactly one sample per
    column and nothing is antialiased, which is why 16:9 looked fine and 9:16
    rendered a nearly invisible waveform.
    """
    assert "draw=full" in ag.build_filtergraph(width=1080, height=1920)
    assert "draw=full" in ag.build_filtergraph(width=1920, height=1080)


def test_filtergraph_trims_in_graph_not_with_input_seek():
    """-ss before -i shifts audio PTS while the looped card starts at 0, so
    overlay pairs them wrong and the waveform vanishes. Trim inside the graph."""
    graph = ag.build_filtergraph(width=1080, height=1920, start=40, duration=15)
    assert "atrim=start=40:end=55" in graph
    assert "asetpts=PTS-STARTPTS" in graph
    assert "asplit=2" in graph, "wave and muxed audio must share one trimmed stream"
    assert f"[{ag.AUDIO_LABEL}]" in graph


def test_filtergraph_without_window_has_no_atrim():
    assert "atrim" not in ag.build_filtergraph()


def test_filtergraph_duration_only_starts_at_zero():
    graph = ag.build_filtergraph(duration=15)
    assert "atrim=end=15" in graph


def test_render_short_is_native_9_16_not_a_crop(tmp_path):
    audio = _make_audio(tmp_path / "a.mp3", seconds=6)
    res = ag.render_short(audio, str(tmp_path / "s.mp4"), start=1.0, end=4.0,
                          title="Space", aspect="9:16")

    assert res["aspect"] == "9:16"
    assert res["duration"] == 3.0
    video = next(s for s in _streams(tmp_path / "s.mp4") if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1080, 1920)
    assert ag.probe_streams(str(tmp_path / "s.mp4"))["duration"] == pytest.approx(3.0, abs=0.4)


def test_render_short_rejects_inverted_window(tmp_path):
    audio = _make_audio(tmp_path / "a.mp3")
    with pytest.raises(ValueError, match="end must be after start"):
        ag.render_short(audio, str(tmp_path / "s.mp4"), start=5.0, end=1.0, title="x")


def test_card_fills_any_aspect(tmp_path):
    from PIL import Image
    for aspect in ("16:9", "9:16", "1:1"):
        w, h = ag.aspect_size(aspect)
        card = ag.build_card(str(tmp_path / f"c{w}x{h}.png"), "Zaal x Kenny",
                             subtitle="hosted by @zaal", footer="58 min",
                             width=w, height=h)
        with Image.open(card) as img:
            assert img.size == (w, h)


# --- caption wrapping (Pillow fallback) -----------------------------------

def test_captions_wrap_to_frame_width():
    """A 5-word line at 6.5% of a 1920px height runs off a 1080px-wide Short."""
    from PIL import Image, ImageDraw, ImageFont
    from backend.services.ffmpeg_service import _find_font, _wrap_to_width

    draw = ImageDraw.Draw(Image.new("RGB", (1080, 1920)))
    font = ImageFont.truetype(_find_font(bold=True), 124)

    lines = _wrap_to_width(draw, "MADE IT. WHAT'S UP, KENNY?", font, 1080 - 108)
    assert len(lines) > 1
    for line in lines:
        assert draw.textlength(line, font=font) <= 1080 - 108


def test_wrap_keeps_an_overlong_single_word():
    from PIL import Image, ImageDraw, ImageFont
    from backend.services.ffmpeg_service import _find_font, _wrap_to_width

    draw = ImageDraw.Draw(Image.new("RGB", (200, 200)))
    font = ImageFont.truetype(_find_font(bold=True), 120)
    assert _wrap_to_width(draw, "SUPERCALIFRAGILISTIC", font, 100) == ["SUPERCALIFRAGILISTIC"]


def test_wrap_of_empty_text_is_not_empty():
    from PIL import Image, ImageDraw, ImageFont
    from backend.services.ffmpeg_service import _find_font, _wrap_to_width

    draw = ImageDraw.Draw(Image.new("RGB", (200, 200)))
    font = ImageFont.truetype(_find_font(bold=True), 20)
    assert _wrap_to_width(draw, "", font, 100) == [""]


def test_finish_overlay_pipe_survives_closed_stdin():
    """communicate() flushes proc.stdin; flushing a closed file raises ValueError,
    which is neither BrokenPipeError nor OSError. That killed every burn."""
    import subprocess, sys
    from backend.services.ffmpeg_service import _finish_overlay_pipe

    proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.buffer.read()"],
                            stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.stdin.write(b"x")
    proc.stdin.close()
    _finish_overlay_pipe(proc, pipe_broke=False)  # must not raise
    assert proc.returncode == 0


def test_ffmpeg_service_has_ass_filter_agrees_with_probe():
    from backend.services.ffmpeg_service import _has_ass_filter as impl
    probe = subprocess.run(["ffmpeg", "-hide_banner", "-h", "filter=ass"],
                           capture_output=True, text=True)
    assert impl() is ("Unknown filter" not in (probe.stdout + probe.stderr))


# --- duration of raw elementary streams ------------------------------------

def _make_raw_aac(path, seconds=3):
    """A Juke space export: raw AAC with no container index, named .mp4."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:a", "aac", "-f", "adts", str(path)],
        check=True, capture_output=True,
    )
    return str(path)


def test_raw_aac_duration_is_decoded_not_estimated(tmp_path):
    """ffprobe reports a bitrate estimate for a raw stream, on BOTH the format
    and the stream. A real 54:10 space reported 57:59 - 3.8 minutes long."""
    raw = _make_raw_aac(tmp_path / "space.mp4", seconds=3)
    assert ag.probe_streams(raw)["duration"] == pytest.approx(3.0, abs=0.35)


def test_indexed_container_duration_is_not_re_decoded(tmp_path, monkeypatch):
    """Only raw streams pay the decode cost."""
    audio = _make_audio(tmp_path / "a.mp3")  # mp3 is raw; use a real container
    wav = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-y", "-i", audio, str(wav)], check=True, capture_output=True)

    called = []
    monkeypatch.setattr(ag, "_decoded_duration", lambda p: called.append(p))
    ag.probe_streams(str(wav))
    assert called == [], "an indexed container must not be decoded"


def test_raw_stream_does_get_decoded(tmp_path, monkeypatch):
    raw = _make_raw_aac(tmp_path / "space.mp4", seconds=2)
    called = []

    def spy(p):
        called.append(p)
        return 2.0

    monkeypatch.setattr(ag, "_decoded_duration", spy)
    assert ag.probe_streams(raw)["duration"] == 2.0
    assert called == [raw]


def test_decode_failure_falls_back_to_the_estimate(tmp_path, monkeypatch):
    raw = _make_raw_aac(tmp_path / "space.mp4", seconds=2)
    monkeypatch.setattr(ag, "_decoded_duration", lambda p: None)
    assert ag.probe_streams(raw)["duration"] > 0, "must not zero out on decode failure"


def test_is_audio_only_never_decodes(tmp_path, monkeypatch):
    """find_video() calls this per request; decoding an hour of audio to answer
    a yes/no question turns a cheap HTTP request into seconds of CPU."""
    raw = _make_raw_aac(tmp_path / "space.mp4", seconds=2)

    def boom(_p):
        raise AssertionError("is_audio_only must not decode")

    monkeypatch.setattr(ag, "_decoded_duration", boom)
    assert ag.is_audio_only(raw) is True


def test_render_audiogram_does_not_decode_to_validate(tmp_path, monkeypatch):
    raw = _make_raw_aac(tmp_path / "space.mp4", seconds=2)
    calls = []
    monkeypatch.setattr(ag, "_decoded_duration", lambda p: calls.append(p) or 2.0)
    ag.render_audiogram(raw, str(tmp_path / "o.mp4"), title="t")
    assert calls == [], "the render only needs stream kinds, not an exact duration"


def test_exact_duration_flag_controls_the_decode(tmp_path, monkeypatch):
    raw = _make_raw_aac(tmp_path / "space.mp4", seconds=2)
    calls = []
    monkeypatch.setattr(ag, "_decoded_duration", lambda p: calls.append(p) or 2.0)

    ag.probe_streams(raw, exact_duration=False)
    assert calls == []
    ag.probe_streams(raw, exact_duration=True)
    assert calls == [raw]
