"""Live (real-time) chunked transcription: rebase, append, roll up."""

from backend.services import live_transcribe


def _fake(segments):
    """A transcriber stub that ignores the audio and returns canned segments."""
    def _t(audio_path, quality, engine):
        return {"segments": segments}
    return _t


def test_transcribe_chunk_rebases_to_offset():
    tr = _fake([{"start": 0.0, "end": 2.0, "text": "hello there"}])
    segs = live_transcribe.transcribe_chunk("x.webm", offset=30.0, transcriber=tr)
    assert segs == [{"start": 30.0, "end": 32.0, "text": "hello there"}]


def test_transcribe_chunk_drops_empty_text():
    tr = _fake([
        {"start": 0.0, "end": 1.0, "text": "  "},
        {"start": 1.0, "end": 2.0, "text": "kept"},
    ])
    segs = live_transcribe.transcribe_chunk("x.webm", transcriber=tr)
    assert len(segs) == 1
    assert segs[0]["text"] == "kept"


def test_append_chunk_accumulates_and_sorts(tmp_path):
    tr1 = _fake([{"start": 0.0, "end": 5.0, "text": "first"}])
    tr2 = _fake([{"start": 0.0, "end": 5.0, "text": "second"}])
    live_transcribe.append_chunk(tmp_path, "a.webm", offset=10.0, transcriber=tr2)
    live_transcribe.append_chunk(tmp_path, "b.webm", offset=0.0, transcriber=tr1)
    out = live_transcribe.get_live_transcript(tmp_path)
    assert out["count"] == 2
    assert [s["text"] for s in out["segments"]] == ["first", "second"]  # sorted by start
    assert out["text"] == "first second"


def test_get_live_transcript_missing_file(tmp_path):
    out = live_transcribe.get_live_transcript(tmp_path)
    assert out == {"segments": [], "text": "", "count": 0}


def test_append_chunk_persists(tmp_path):
    tr = _fake([{"start": 0.0, "end": 1.0, "text": "saved"}])
    live_transcribe.append_chunk(tmp_path, "a.webm", transcriber=tr)
    assert (tmp_path / "live_transcript.json").exists()
    again = live_transcribe.get_live_transcript(tmp_path)
    assert again["count"] == 1
