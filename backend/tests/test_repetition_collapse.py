"""Whisper repetition collapse: the failure that passed every other check.

A real 54-minute space transcribed into "So, yeah." repeated for fifty minutes.
1983 segments, well-formed captions, a valid 1080p render, and every check in
verify_render passed - because the pixels were fine and only the words were wrong.

Nothing in the pipeline looked at the words. This is that check.
"""

import pytest

from backend.services.recordings_pipeline import (
    REPETITION_LIMIT, repetition_ratio,
)
from backend.services.whisper_service import PASS_CONFIGS, TEMPERATURE_FALLBACK


def _segs(texts):
    return [{"text": t, "start": i, "end": i + 1} for i, t in enumerate(texts)]


def test_healthy_conversation_scores_zero():
    segs = _segs(["hi Kenny", "what's up Zaal", "let's talk POIDH", "sounds good",
                  "so bounties", "right", "exactly", "for sure", "yeah", "ok then",
                  "next topic", "sure"])
    assert repetition_ratio(segs) == 0.0


def test_the_real_collapse_is_caught():
    """The shipped transcript: 4 minutes of speech, then one line 500 times."""
    segs = _segs(["hi Kenny", "what's up Zaal", "let's talk POIDH"] + ["So, yeah."] * 500)
    ratio = repetition_ratio(segs)
    assert ratio > 0.95
    assert ratio >= REPETITION_LIMIT


def test_occasional_repeats_are_tolerated():
    """Real conversations do repeat a filler line now and then."""
    segs = _segs(["a", "b", "yeah", "yeah", "c", "d", "e", "right", "f", "g",
                  "h", "i", "j", "k", "l", "m", "n", "o", "p", "q"])
    assert repetition_ratio(segs) < REPETITION_LIMIT


def test_threshold_separates_by_a_wide_margin():
    assert REPETITION_LIMIT > 0.0
    assert REPETITION_LIMIT < 0.967 / 5, "too close to the real collapse"


def test_short_transcripts_are_not_judged():
    """A 3-segment clip of someone saying 'yeah' twice is not a loop."""
    assert repetition_ratio(_segs(["yeah", "yeah", "yeah"])) == 0.0


def test_blank_segments_do_not_count_as_repeats():
    assert repetition_ratio(_segs([""] * 20)) == 0.0


def test_empty_input():
    assert repetition_ratio([]) == 0.0


# --- the root cause -------------------------------------------------------

def test_temperature_is_a_sequence_not_a_scalar():
    """faster-whisper only runs the temperature fallback - its escape hatch from a
    repetition loop - when temperature is a sequence. A scalar 0.0 silently
    disables it and makes compression_ratio_threshold decorative."""
    assert isinstance(TEMPERATURE_FALLBACK, (list, tuple))
    assert len(TEMPERATURE_FALLBACK) > 1
    assert TEMPERATURE_FALLBACK[0] == 0.0

    for config in PASS_CONFIGS:
        t = config["temperature"]
        assert isinstance(t, (list, tuple)), f"{config['name']}: scalar temperature"
        assert len(t) > 1, f"{config['name']}: no fallback ladder"


def test_long_form_does_not_condition_on_previous_text():
    """Feeding the model its own looping output back as context cements the loop."""
    for config in PASS_CONFIGS:
        assert config["condition_on_previous_text"] is False, config["name"]


def test_compression_ratio_threshold_is_still_set():
    """It is the trigger for the fallback; without it the ladder never fires."""
    for config in PASS_CONFIGS:
        assert config["compression_ratio_threshold"] > 1.0


def test_initial_prompt_is_not_injected():
    """Whisper decodes initial_prompt as preceding speech, so a bare glossary term
    list gets echoed into the transcript and seeds the loop. hotwords biases the
    same spellings without ever being decoded."""
    from backend.services.whisper_service import _build_vocab_prompt

    initial_prompt, hotwords = _build_vocab_prompt()
    assert initial_prompt is None, "initial_prompt is read back as speech"
    if hotwords is not None:
        assert "Glossary" not in hotwords
