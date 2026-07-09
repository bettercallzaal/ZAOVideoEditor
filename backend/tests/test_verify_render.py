"""The eval must fail on artifacts that once shipped green.

Each of these renders passed ffmpeg's exit code, its function's return value, and
the whole unit suite, while being visibly broken. That is the point of measuring
the frame buffer: it is the one signal upstream code cannot fake.

A verifier nobody has pointed at a known-bad artifact is just another green light,
so every check here is proven against a deliberately broken render, not only
against a good one.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.services import audiogram_service as ag  # noqa: E402
from scripts.verify_render import (  # noqa: E402
    MIN_FRAME_DELTA, MIN_WAVEFORM_COVERAGE, verify,
)


def _has_ffmpeg() -> bool:
    from shutil import which
    return which("ffmpeg") is not None and which("ffprobe") is not None


pytestmark = pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg/ffprobe not on PATH")


@pytest.fixture(scope="module")
def speech(tmp_path_factory):
    """Something with real amplitude variation, so the waveform has shape."""
    p = tmp_path_factory.mktemp("verify") / "a.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", "sine=frequency=200:duration=4,tremolo=f=4:d=0.9",
         "-ar", "48000", str(p)],
        check=True, capture_output=True,
    )
    return str(p)


def test_good_audiogram_passes_every_check(speech, tmp_path):
    out = str(tmp_path / "good.mp4")
    ag.render_audiogram(speech, out, title="Space", aspect="16:9")

    report = verify(out, aspect="16:9", duration=4.0, samples=4)
    assert report["ok"], report["failed"]


def test_catches_wrong_dimensions(speech, tmp_path):
    out = str(tmp_path / "portrait.mp4")
    ag.render_audiogram(speech, out, title="Space", aspect="9:16")

    report = verify(out, aspect="16:9", expect_waveform=False, samples=2)
    assert "dimensions_match_aspect" in report["failed"]


def test_catches_a_missing_waveform(speech, tmp_path):
    """Regression: -ss before -i shifted audio PTS and the waveform vanished."""
    card = str(tmp_path / "card.png")
    ag.build_card(card, "Space", width=1920, height=1080)

    out = str(tmp_path / "nowave.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", card,
         "-i", speech, "-shortest", "-c:v", "libx264", "-preset", "veryfast",
         "-pix_fmt", "yuv420p", "-c:a", "aac", out],
        check=True, capture_output=True,
    )

    report = verify(out, aspect="16:9", duration=4.0, samples=4)
    assert "waveform_visible" in report["failed"]


def test_catches_a_frozen_video(tmp_path):
    """A still card with silence: ffmpeg exits 0 and the file is valid."""
    card = str(tmp_path / "card.png")
    ag.build_card(card, "Space", width=1920, height=1080)

    out = str(tmp_path / "frozen.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", card,
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "4",
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", out],
        check=True, capture_output=True,
    )

    report = verify(out, aspect="16:9", expect_waveform=False, samples=4)
    assert "video_is_not_frozen" in report["failed"], (
        "a still frame must not pass; an earlier 0.02% threshold let it through"
    )


def test_catches_an_uncaptioned_short(speech, tmp_path):
    """Regression: export_clip swallowed the burn error and shipped this."""
    out = str(tmp_path / "nocap.mp4")
    ag.render_audiogram(speech, out, title="Space", aspect="9:16")

    report = verify(out, aspect="9:16", expect_captions=True, samples=4)
    assert "captions_burned_in" in report["failed"]


def test_audio_only_input_fails_the_video_check(speech, tmp_path):
    report = verify(speech, aspect="16:9", expect_waveform=False, samples=1)
    assert "has_video_stream" in report["failed"]
    assert report["ok"] is False


def test_thresholds_separate_good_from_broken_by_a_wide_margin():
    """A threshold is only a signal if it separates. Measured values:

    waveform coverage - healthy 32%-48%, both known-broken renders 0.077%
    waveform-band motion - live 2.2%-30%, frozen still exactly 0.000%
    """
    assert MIN_WAVEFORM_COVERAGE > 0.00077 * 5, "too close to the broken renders"
    assert MIN_WAVEFORM_COVERAGE < 0.32 / 10, "too close to a healthy render"
    assert MIN_FRAME_DELTA > 0, "a frozen still must not pass"
    assert MIN_FRAME_DELTA < 0.022 / 4, "too close to the quietest live render"


def test_motion_metric_does_not_depend_on_sample_count(speech, tmp_path):
    """A periodic signal aliases against widely spaced samples: a 4 Hz tremolo
    measured 12% at 4 samples but 1.5% at 3, flipping the verdict. The `speech`
    fixture is that same tremolo, so this pins the flake."""
    out = str(tmp_path / "tone.mp4")
    ag.render_audiogram(speech, out, title="Space", aspect="16:9")

    for samples in (2, 3, 4, 5):
        report = verify(out, aspect="16:9", samples=samples)
        assert "video_is_not_frozen" not in report["failed"], (
            f"a live render was called frozen at samples={samples}"
        )


def test_srt_zero_length_cues_are_reported(tmp_path, speech):
    out = str(tmp_path / "g.mp4")
    ag.render_audiogram(speech, out, title="Space", aspect="16:9")

    srt = tmp_path / "bad.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nreal\n\n"
        "2\n00:00:02,000 --> 00:00:02,000\ncast, cast, cast\n\n",
        encoding="utf-8",
    )
    report = verify(out, aspect="16:9", expect_waveform=False, srt=str(srt), samples=1)
    assert "srt_no_zero_length_cues" in report["failed"]


def test_srt_running_past_the_video_is_reported(tmp_path, speech):
    """Regression: --minutes capped the render but not the transcript, so the
    chapters described 1:02:23 of a 3-minute video."""
    out = str(tmp_path / "g.mp4")
    ag.render_audiogram(speech, out, title="Space", aspect="16:9")

    srt = tmp_path / "long.srt"
    srt.write_text("1\n01:02:20,000 --> 01:02:23,000\nway past the end\n\n",
                   encoding="utf-8")
    report = verify(out, aspect="16:9", expect_waveform=False, srt=str(srt), samples=1)
    assert "srt_within_video_duration" in report["failed"]


def test_report_shape_is_machine_readable(speech, tmp_path):
    """A loop's stop signal has to be parseable, not just printable."""
    out = str(tmp_path / "g.mp4")
    ag.render_audiogram(speech, out, title="Space", aspect="16:9")

    report = verify(out, aspect="16:9", samples=2)
    assert set(report) == {"file", "ok", "failed", "checks"}
    assert isinstance(report["ok"], bool)
    assert all({"name", "ok", "detail"} == set(c) for c in report["checks"])


def test_cli_exit_code_is_the_stop_signal(speech, tmp_path):
    """Exit 0 / 1 is what a loop actually branches on."""
    good = str(tmp_path / "good.mp4")
    ag.render_audiogram(speech, good, title="Space", aspect="16:9")

    root = Path(__file__).resolve().parent.parent.parent
    cmd = [sys.executable, str(root / "scripts" / "verify_render.py"), good,
           "--aspect", "16:9", "--samples", "3"]
    assert subprocess.run(cmd, capture_output=True).returncode == 0

    cmd_bad = cmd + ["--expect-captions"]
    assert subprocess.run(cmd_bad, capture_output=True).returncode == 1
