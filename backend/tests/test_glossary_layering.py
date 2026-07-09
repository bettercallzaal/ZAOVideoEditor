"""Glossary layering: the bundled seed and the team's living file must compose.

The two on-disk glossaries are NOT supersets of each other. The bundled seed
carries WaveWarZ, COC Concertz, SongJam, FISHBOWLZ; the zabalgames canonical
file carries POIDH, Neynar, Farcaster and the Zaal/Zabal mishears. Pointing
STUDIO_GLOSSARY_PATH at the canonical file used to *replace* the seed, silently
dropping every rule the canonical file did not happen to duplicate.
"""

import json

from backend.services.glossary import (
    BUNDLED_CORRECTIONS_PATH, add_safe_correction, apply_safe_corrections,
    external_corrections_path, load_corrections,
)


def _write_canonical(path, safe_rules):
    """The zabalgames shape: safe as a list of {from, to}."""
    path.write_text(json.dumps({
        "safe": [{"from": k, "to": v} for k, v in safe_rules.items()],
        "review": [],
    }))
    return path


def test_bundled_seed_alone_has_the_zao_brands():
    corr = load_corrections(BUNDLED_CORRECTIONS_PATH)
    assert corr["safe"]["wavewarz"] == "WaveWarZ"
    assert corr["safe"]["fishbowlz"] == "FISHBOWLZ"


def test_overlay_adds_without_dropping_the_seed(tmp_path, monkeypatch):
    canon = _write_canonical(tmp_path / "canon.json", {"POID": "POIDH"})
    monkeypatch.setenv("STUDIO_GLOSSARY_PATH", str(canon))

    corr = load_corrections()
    assert corr["safe"]["poid"] == "POIDH", "overlay rule missing"
    assert corr["safe"]["wavewarz"] == "WaveWarZ", "seed rule was dropped by the overlay"


def test_overlay_wins_on_conflict(tmp_path, monkeypatch):
    canon = _write_canonical(tmp_path / "canon.json", {"wavewarz": "OVERRIDDEN"})
    monkeypatch.setenv("STUDIO_GLOSSARY_PATH", str(canon))
    assert load_corrections()["safe"]["wavewarz"] == "OVERRIDDEN"


def test_explicit_path_does_not_layer(tmp_path):
    """An explicit path means exactly that file - used for diffing the two."""
    canon = _write_canonical(tmp_path / "canon.json", {"POID": "POIDH"})
    corr = load_corrections(canon)
    assert corr["safe"] == {"poid": "POIDH"}
    assert "wavewarz" not in corr["safe"]


def test_no_external_configured_is_just_the_seed(monkeypatch):
    monkeypatch.delenv("STUDIO_GLOSSARY_PATH", raising=False)
    assert external_corrections_path() is None
    assert load_corrections()["safe"]["songjam"] == "SongJam"


def test_env_is_read_at_call_time_not_import_time(tmp_path, monkeypatch):
    monkeypatch.delenv("STUDIO_GLOSSARY_PATH", raising=False)
    assert "poid" not in load_corrections()["safe"]

    canon = _write_canonical(tmp_path / "canon.json", {"POID": "POIDH"})
    monkeypatch.setenv("STUDIO_GLOSSARY_PATH", str(canon))
    assert "poid" in load_corrections()["safe"]


def test_teaching_writes_to_the_living_file_not_the_seed(tmp_path, monkeypatch):
    canon = _write_canonical(tmp_path / "canon.json", {"POID": "POIDH"})
    monkeypatch.setenv("STUDIO_GLOSSARY_PATH", str(canon))

    seed_before = BUNDLED_CORRECTIONS_PATH.read_text()
    add_safe_correction("zaostok", "ZAOstock")

    assert "zaostok" in canon.read_text().lower()
    assert BUNDLED_CORRECTIONS_PATH.read_text() == seed_before, "teaching mutated the bundled seed"


def test_zabal_mishear_from_the_real_recording():
    """Whisper large-v3 renders ZABAL as 'ExaBall'. Observed, not invented."""
    text, changes = apply_safe_corrections(
        "super excited to talk. ExaBall Games, I got a couple ideas.",
        load_corrections(BUNDLED_CORRECTIONS_PATH),
    )
    assert "ZABAL Gamez" in text
    assert "ExaBall" not in text


def test_longer_rule_beats_shorter_one():
    """'exaball games' must win over 'exaball', or we get 'ZABAL Games'."""
    text, _ = apply_safe_corrections("ExaBall Games rules",
                                     load_corrections(BUNDLED_CORRECTIONS_PATH))
    assert "ZABAL Gamez" in text
    assert "ZABAL Games" not in text


def test_bare_exaball_still_maps_to_zabal():
    text, _ = apply_safe_corrections("the ExaBall ecosystem",
                                     load_corrections(BUNDLED_CORRECTIONS_PATH))
    assert "ZABAL ecosystem" in text


def test_detect_speakers_reports_why_it_failed(monkeypatch):
    """Diarization stays non-fatal, but the reason must reach the caller.

    It used to print() into a background worker's stdout and return unlabeled
    segments, so an explicit --speakers looked like it had worked.
    """
    from backend.services import recordings_pipeline as rp

    segs = [{"start": 0, "end": 1, "text": "hi"}]
    monkeypatch.setattr(
        rp, "_ensure_audio", lambda p: (p, None), raising=False,
    )

    def boom(_path):
        raise RuntimeError("HF_TOKEN not set")

    import sys, types
    fake = types.ModuleType("backend.services.diarization")
    fake.diarize_audio = boom
    fake.assign_speakers_to_segments = lambda s, t: s
    monkeypatch.setitem(sys.modules, "backend.services.diarization", fake)

    out, err = rp._detect_speakers("a.wav", segs, lambda p, m: None)
    assert out == segs, "segments must survive a diarization failure"
    assert err and "HF_TOKEN" in err, "the reason must be returned, not swallowed"


def test_detect_speakers_reports_empty_turns(monkeypatch):
    from backend.services import recordings_pipeline as rp
    import sys, types

    fake = types.ModuleType("backend.services.diarization")
    fake.diarize_audio = lambda _p: []
    fake.assign_speakers_to_segments = lambda s, t: s
    monkeypatch.setitem(sys.modules, "backend.services.diarization", fake)

    segs = [{"start": 0, "end": 1, "text": "hi"}]
    out, err = rp._detect_speakers("a.wav", segs, lambda p, m: None)
    assert out == segs
    assert err == "diarization produced no speaker turns"


# --- word-level tokens (captions are built from these, not from seg["text"]) --

def _w(word, start, end):
    return {"word": word, "start": start, "end": end}


def test_word_tokens_are_corrected():
    """Captions come from seg["words"]. Correcting only seg["text"] ships a video
    whose description says POIDH and whose captions say Poid."""
    from backend.services.glossary import correct_word_tokens

    words = [_w(" I", 0, 0.2), _w(" like", 0.2, 0.4), _w(" Poid", 0.4, 0.8)]
    out, changes = correct_word_tokens(words, {"safe": {"poid": "POIDH"}, "review": []})
    assert [w["word"] for w in out] == [" I", " like", " POIDH"]
    assert changes


def test_word_token_correction_preserves_timing():
    from backend.services.glossary import correct_word_tokens

    words = [_w(" Poid", 1.0, 1.5)]
    out, _ = correct_word_tokens(words, {"safe": {"poid": "POIDH"}, "review": []})
    assert out[0]["start"] == 1.0 and out[0]["end"] == 1.5


def test_word_token_correction_keeps_punctuation():
    from backend.services.glossary import correct_word_tokens

    words = [_w(" Poid,", 0, 1), _w(" Poid.", 1, 2)]
    out, _ = correct_word_tokens(words, {"safe": {"poid": "POIDH"}, "review": []})
    assert [w["word"] for w in out] == [" POIDH,", " POIDH."]


def test_multiword_rule_spanning_two_tokens():
    """'exaball games' -> 'ZABAL Gamez' spans two tokens; a per-token pass misses it."""
    from backend.services.glossary import correct_word_tokens

    words = [_w(" ExaBall", 1.0, 1.4), _w(" Games", 1.4, 1.9), _w(" rocks", 1.9, 2.2)]
    corr = {"safe": {"exaball games": "ZABAL Gamez", "exaball": "ZABAL"}, "review": []}
    out, changes = correct_word_tokens(words, corr)

    assert [w["word"] for w in out] == [" ZABAL Gamez", " rocks"]
    assert out[0]["start"] == 1.0 and out[0]["end"] == 1.9, "merged token must span both"
    assert any(c["from"] == "exaball games" for c in changes)


def test_multiword_rule_that_collapses_word_count():
    from backend.services.glossary import correct_word_tokens

    words = [_w(" wave", 0.0, 0.3), _w(" wars", 0.3, 0.7)]
    corr = {"safe": {"wave wars": "WaveWarZ"}, "review": []}
    out, _ = correct_word_tokens(words, corr)
    assert [w["word"] for w in out] == [" WaveWarZ"]
    assert out[0]["end"] == 0.7


def test_bare_token_rule_still_applies_after_multiword_miss():
    from backend.services.glossary import correct_word_tokens

    words = [_w(" ExaBall", 0, 1), _w(" ecosystem", 1, 2)]
    corr = {"safe": {"exaball games": "ZABAL Gamez", "exaball": "ZABAL"}, "review": []}
    out, _ = correct_word_tokens(words, corr)
    assert [w["word"] for w in out] == [" ZABAL", " ecosystem"]


def test_empty_words_is_safe():
    from backend.services.glossary import correct_word_tokens
    assert correct_word_tokens([], {"safe": {}, "review": []}) == ([], [])


def test_srt_and_description_agree_on_brand_names():
    """The end-to-end invariant that was violated: metadata said POIDH, captions
    said Poid."""
    from backend.services.caption_gen import generate_captions_from_segments, generate_srt
    from backend.services.glossary import correct_transcript_text, correct_word_tokens

    corr = {"safe": {"poid": "POIDH"}, "review": []}
    segs = [{
        "start": 0.0, "end": 1.0, "text": "I like Poid",
        "words": [_w(" I", 0, 0.2), _w(" like", 0.2, 0.5), _w(" Poid", 0.5, 1.0)],
    }]
    for s in segs:
        s["text"] = correct_transcript_text(s["text"], corr)["text"]
        s["words"], _ = correct_word_tokens(s["words"], corr)

    srt = generate_srt(generate_captions_from_segments(segs))
    assert "POIDH" in srt
    assert "Poid " not in srt and not srt.rstrip().endswith("Poid")
    assert "POIDH" in segs[0]["text"]
