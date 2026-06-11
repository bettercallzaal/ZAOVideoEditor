"""Brand glossary corrections, review flagging, number formatting."""

import pytest

from backend.services.glossary import (
    apply_safe_corrections, flag_review_terms, format_numbers, correct_transcript_text,
)


def test_safe_corrections_fix_casing_whole_word():
    out, changes = apply_safe_corrections("we launched Wave Wars and songjam today")
    assert "WaveWarZ" in out
    assert "SongJam" in out
    assert any(c["to"] == "WaveWarZ" for c in changes)


def test_safe_corrections_do_not_mangle_domain():
    out, _ = apply_safe_corrections("go to wavewars.com now")
    assert "wavewarz.com" in out
    assert "WaveWarZ.com" not in out  # the bare-word rule must not hit inside the domain


def test_safe_corrections_still_fix_word_at_sentence_end():
    out, _ = apply_safe_corrections("have you seen wave wars.")
    assert "WaveWarZ." in out


def test_steelo_to_stilo():
    out, _ = apply_safe_corrections("over at Steelo World")
    assert "Stilo World" in out


def test_review_terms_flagged_not_changed():
    text = "we bought on base with 5 SOL and Hurricane Mike"
    flags = flag_review_terms(text)
    terms = {f["term"] for f in flags}
    assert "base" in terms
    assert "Hurricane Mike" in terms
    # flagging never edits
    out, _ = apply_safe_corrections(text)
    assert "base" in out


@pytest.mark.parametrize("src,expected", [
    ("it cost point five SOL", "0.5 SOL"),
    ("five hundred SOL", "500 SOL"),
    ("at eight thirty PM EST", "8:30pm EST"),
    ("forty plus people", "40-plus people"),
    ("point zero five", "0.05"),
    ("point zero three ETH", "0.03 ETH"),
])
def test_number_formatting(src, expected):
    assert expected in format_numbers(src)


def test_correct_transcript_text_no_number_format_by_default():
    res = correct_transcript_text("we made five hundred SOL on Wave Wars")
    assert "WaveWarZ" in res["text"]
    assert "five hundred SOL" in res["text"]  # numbers untouched for the cut transcript
    assert isinstance(res["review_flags"], list)


def test_correct_transcript_text_with_number_format():
    res = correct_transcript_text("five hundred SOL", do_number_format=True)
    assert "500 SOL" in res["text"]
