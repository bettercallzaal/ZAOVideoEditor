"""Readable pass + pipeline orchestration (transcribe + ffmpeg + LLM mocked)."""

from pathlib import Path

from backend.services import readable_pass
from backend.services import recordings_pipeline


SEGMENTS = [
    {"start": 0.0, "end": 4.0, "text": "we launched Wave Wars", "speaker": "Zaal"},
    {"start": 4.0, "end": 8.0, "text": "it cost point five SOL", "speaker": "Zaal"},
]


def test_deterministic_readable_strips_emdash_and_formats_numbers():
    segs = [{"text": "we made five hundred SOL"}, {"text": "wait — really"}]
    out = readable_pass.make_readable(segs, title="Demo", deterministic_only=True)
    assert out["backend"] == "deterministic"
    assert "500 SOL" in out["markdown"]
    assert "—" not in out["markdown"]
    assert out["markdown"].startswith("# Demo")


def test_make_readable_uses_hermes_when_available(monkeypatch):
    monkeypatch.setattr(readable_pass.hermes, "run_prompt", lambda *a, **k: "clean transcript body")
    monkeypatch.setattr(readable_pass.hermes, "backend_name", lambda: "claude-cli")
    out = readable_pass.make_readable(SEGMENTS, title="Talk")
    assert out["backend"] == "claude-cli"
    assert "clean transcript body" in out["markdown"]
    assert out["markdown"].startswith("# Talk")


def test_make_readable_falls_back_when_no_backend(monkeypatch):
    monkeypatch.setattr(readable_pass.hermes, "run_prompt", lambda *a, **k: None)
    out = readable_pass.make_readable(SEGMENTS, title="Talk")
    assert out["backend"] == "deterministic"


def test_pipeline_corrects_segments_and_writes_outputs(monkeypatch, tmp_path):
    # avoid whisper + ffmpeg
    monkeypatch.setattr(recordings_pipeline, "_ensure_audio", lambda p: (p, None))
    monkeypatch.setattr(
        recordings_pipeline, "transcribe_audio",
        lambda *a, **k: {"segments": [dict(s) for s in SEGMENTS]},
    )
    monkeypatch.setattr(
        recordings_pipeline, "make_readable",
        lambda segments, title="", deterministic_only=False: {"markdown": f"# {title}\n\nbody", "backend": "mock"},
    )

    media = tmp_path / "rec.wav"
    media.write_bytes(b"fake")

    res = recordings_pipeline.process_recording(
        str(media), title="WaveWarZ Talk", out_dir=str(tmp_path / "out"),
    )

    # safe corrections applied to the cut transcript
    assert any("WaveWarZ" in s["text"] for s in res["segments"])
    # cut transcript keeps spelled numbers; readable is separate
    assert "point five SOL" in res["cut_transcript_md"]
    # review flags present (SOL is a review term) and deduped
    terms = [f["term"] for f in res["review_flags"]]
    assert len(terms) == len(set(terms))
    # files written
    out_dir = Path(res["output_dir"])
    assert (out_dir / "wavewarz-talk.cut.md").exists()
    assert (out_dir / "wavewarz-talk.readable.md").exists()
    assert (out_dir / "wavewarz-talk.review-flags.json").exists()


def test_pipeline_missing_file_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        recordings_pipeline.process_recording(str(tmp_path / "nope.wav"))
