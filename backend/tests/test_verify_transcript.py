"""The words eval. Proven against transcripts that shipped broken.

verify_render measures pixels and passed, every check green, on a 54-minute video
whose transcript was "So, yeah." five hundred times. An eval only sees what it
looks at. This one reads the words.

Each check here is anchored to a real failure:
  segment loop      - the 54-minute Zaal x Kenny transcript, 0.967
  intra-segment loop - the Farcaster AMA, one segment 100% "cast"
  prompt echo       - "Farcaster, Ohnahji, Saltorius, SongJam, WaveWarZ, Zabal..."
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.verify_transcript import (  # noqa: E402
    MAX_INTRA_SEGMENT_REPETITION, MAX_SEGMENT_REPETITION, MIN_VOCAB_DIVERSITY,
    _is_term_list, intra_segment_repetition, prompt_echo_segments,
    segment_repetition, vocab_diversity, verify, words_per_minute,
)

CONVO = [
    "Oh shit, Kenny, there we go.",
    "What's up, Zaal? Can you hear me?",
    "I can hear you loud and clear.",
    "All right, beautiful. I knew we could get this working.",
    "Yeah, it's just tough, I should probably get in higher.",
    "But I'm a stubborn person and that's what it is.",
    "The last one I did, every ten minutes I got booted out.",
    "They had a glitch at one point where that happened.",
    "The fact you can't get up on Android is a bigger problem.",
    "So I'm really excited to leverage POIDH for social capital.",
    "We can prove they're a verifiable active community member.",
    "That's one thing I'm trying to do with the ZAO token.",
    "So, yeah, if anyone wants to come up, welcome to come up.",
    "Absolutely, let's dig into bounties.",
]


def _segs(texts, step=4.0):
    return [{"text": t, "start": i * step, "end": i * step + step - 0.5}
            for i, t in enumerate(texts)]


# --- the healthy case must pass, or the eval is useless -------------------

def test_a_real_conversation_passes():
    report = verify(_segs(CONVO), audio_duration=len(CONVO) * 4)
    assert report["ok"], report["failed"]


# --- failure 1: the segment-to-segment loop ------------------------------

def test_the_54_minute_collapse_is_caught():
    segs = _segs(CONVO[:3] + ["So, yeah."] * 500)
    report = verify(segs)
    assert "no_segment_repetition_loop" in report["failed"]
    assert segment_repetition(segs) > 0.95


def test_vocabulary_collapse_is_caught():
    segs = _segs(CONVO[:3] + ["So, yeah."] * 500)
    assert vocab_diversity(segs) < MIN_VOCAB_DIVERSITY
    assert "vocabulary_is_diverse" in verify(segs)["failed"]


def test_occasional_filler_repeats_are_tolerated():
    """Real speech repeats "yeah" now and then. That is not a loop."""
    segs = _segs(CONVO + ["Yeah.", "Yeah."])
    assert segment_repetition(segs) < MAX_SEGMENT_REPETITION


# --- failure 2: the loop inside one segment ------------------------------

def test_intra_segment_loop_is_caught_on_a_single_segment():
    """The AMA transcript had four segments; segment-to-segment repetition scored
    0.000 while one segment was the word "cast" fifty times. A short-circuit on
    segment count used to skip this check entirely and pass."""
    segs = _segs(["Hello there everyone, welcome.", ", ".join(["cast"] * 50)])
    assert intra_segment_repetition(segs) == pytest.approx(1.0, abs=0.02)
    assert "no_intra_segment_loop" in verify(segs)["failed"]


def test_short_segments_do_not_trigger_the_intra_check():
    """"Yeah, yeah, yeah" is three words, not a loop."""
    assert intra_segment_repetition(_segs(["Yeah, yeah, yeah."])) == 0.0


def test_normal_speech_is_under_the_intra_limit():
    assert intra_segment_repetition(_segs(CONVO)) < MAX_INTRA_SEGMENT_REPETITION


# --- failure 3: the prompt read back as speech ---------------------------

def test_prompt_echo_is_caught_without_the_word_glossary():
    """The real echo dropped the "Glossary:" label and read back only the terms."""
    echo = "Farcaster, Ohnahji, Saltorius, SongJam, WaveWarZ, Zabal, Zabal, Zabal"
    assert _is_term_list(echo)
    assert prompt_echo_segments(_segs([echo] + CONVO))


def test_labelled_prompt_echo_is_caught():
    labelled = "Glossary: Better Calls Zaal, Farcaster, SongJam, WaveWarZ, ZABAL, ZAO"
    assert prompt_echo_segments(_segs([labelled] + CONVO))


@pytest.mark.parametrize("speech", [
    "Oh shit, Kenny, there we go. Okay, I think we finally made it. What's up, Kenny?",
    "Yeah, right, exactly, for sure, absolutely.",
    "So, yeah, if anyone wants to come up, welcome to come up.",
    "We talked about bounties, clipping, and the World Cup, right?",
])
def test_real_speech_is_not_mistaken_for_a_term_list(speech):
    """A false positive blocks a good render, which is worse than the bug.
    Counting capitalised comma-parts alone flagged the real opening line."""
    assert not _is_term_list(speech)


def test_prompt_echo_only_looks_at_the_opening():
    """A term list deep in a conversation is someone reading a list aloud."""
    late = CONVO + ["Kenny, Zaal, POIDH, WaveWarZ, SongJam, ZABAL"]
    assert not prompt_echo_segments(late and _segs(late), head=5)


# --- rates and coverage ---------------------------------------------------

def test_speech_rate_is_plausible():
    assert 40 <= words_per_minute(_segs(CONVO)) <= 400


def test_transcript_that_stops_early_is_flagged():
    report = verify(_segs(CONVO), audio_duration=3600)
    assert "spans_the_audio" in report["failed"]


def test_empty_transcript():
    report = verify([])
    assert not report["ok"]
    assert "has_segments" in report["failed"]


def test_short_clip_skips_the_rate_checks_but_not_the_loop_checks():
    segs = _segs(["Hello there everyone.", ", ".join(["cast"] * 40)])
    report = verify(segs)
    names = [c["name"] for c in report["checks"]]
    assert "no_intra_segment_loop" in names
    assert "no_segment_repetition_loop" not in names
    assert not report["ok"], "an intra-segment loop must still fail a short clip"


# --- the trap: do not use model confidence -------------------------------

def test_collapse_is_caught_despite_perfect_model_confidence():
    """The collapsed transcript scored avg_logprob -0.030, BETTER than a healthy
    one's -0.144. Repeated tokens are trivially predictable, so the model is most
    confident exactly when it is looping. An eval that trusted confidence would
    have passed the broken transcript and failed the good one."""
    collapsed = _segs(CONVO[:3] + ["So, yeah."] * 500)
    for s in collapsed:
        s["avg_logprob"] = -0.030      # near-perfect confidence
        s["no_speech_prob"] = 0.025

    healthy = _segs(CONVO)
    for s in healthy:
        s["avg_logprob"] = -0.144      # measurably worse, and correct
        s["no_speech_prob"] = 0.10

    assert not verify(collapsed)["ok"], "confidence must not rescue a loop"
    assert verify(healthy, audio_duration=len(CONVO) * 4)["ok"]


def test_thresholds_separate_measured_values():
    """collapsed 0.967 / loop-start 0.420 / healthy 0.004 segment repetition;
    collapsed 0.064 / healthy 0.434 windowed vocabulary diversity."""
    assert MAX_SEGMENT_REPETITION < 0.420 / 4
    assert MAX_SEGMENT_REPETITION > 0.004
    assert MIN_VOCAB_DIVERSITY > 0.064 * 2
    assert MIN_VOCAB_DIVERSITY < 0.434 / 2


def test_vocab_diversity_does_not_depend_on_transcript_length():
    """A plain unique/total ratio falls as a transcript grows: one healthy
    54-minute transcript scored 0.605 over its first 200 words and 0.152 over all
    8581, against a 0.15 limit. That threshold was really a threshold on duration,
    and a healthy two-hour recording would have been rejected."""
    unit = CONVO * 40           # a long, non-repeating-enough conversation
    short = vocab_diversity(_segs(CONVO * 5))
    long_ = vocab_diversity(_segs(unit))
    assert abs(short - long_) < 0.12, f"length-dependent: {short:.3f} vs {long_:.3f}"
    assert long_ > MIN_VOCAB_DIVERSITY
