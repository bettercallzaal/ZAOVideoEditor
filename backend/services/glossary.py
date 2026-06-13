"""Brand-glossary correction + number formatting for transcripts.

Stage C of the recordings pipeline. Mirrors the zabalgames `fix-transcript.mjs`
behaviour: `safe` rules auto-apply (whole-word, case-insensitive, original
casing of the replacement preserved); `review` rules are only flagged for a
human, never auto-changed.

Single source of truth: backend/data/transcript-corrections.json (to be
reconciled with the canonical file in zabalgames when wired).
"""

import json
import os
import re
from pathlib import Path
from typing import Optional


# Point this at the canonical zabalgames data/transcript-corrections.json via
# STUDIO_GLOSSARY_PATH so the Studio reads AND writes the team's living glossary
# (the "fix a word once, it learns" file). Defaults to the bundled seed copy.
CORRECTIONS_PATH = Path(
    os.environ.get("STUDIO_GLOSSARY_PATH", "").strip()
    or (Path(__file__).parent.parent / "data" / "transcript-corrections.json")
)


def load_corrections(path: Optional[Path] = None) -> dict:
    """Load corrections, normalizing the two on-disk shapes into one internal form.

    Internal form: {"safe": {wrong_lower: right}, "review": [{term, to, note}]}.
    Supports BOTH:
      - the bundled seed: safe = {wrong: right} dict
      - the zabalgames canonical file: safe/review = [{from, to, note}] lists
    so STUDIO_GLOSSARY_PATH can point straight at the team's file.
    """
    p = path or CORRECTIONS_PATH
    if not p.exists():
        return {"safe": {}, "review": []}
    with open(p) as f:
        data = json.load(f)

    raw_safe = data.get("safe", {})
    if isinstance(raw_safe, list):  # zabalgames {from,to} list format
        safe = {r["from"].lower(): r["to"] for r in raw_safe if r.get("from") and r.get("to")}
    else:
        safe = {k.lower(): v for k, v in raw_safe.items()}

    review = []
    for r in data.get("review", []):
        if isinstance(r, dict):
            term = r.get("term") or r.get("from")
            if term:
                review.append({"term": term, "to": r.get("to"), "note": r.get("note", "")})
    return {"safe": safe, "review": review}


def _whole_word_pattern(term: str) -> re.Pattern:
    # Word-ish boundaries that also work for multi-word terms and domains.
    # Trailing `(?!\.\w)` stops a bare word ("wavewarz") from matching inside a
    # domain ("wavewarz.com") while still matching at a sentence-ending period.
    return re.compile(rf"(?<![\w.]){re.escape(term)}(?![\w])(?!\.\w)", re.IGNORECASE)


def apply_safe_corrections(text: str, corrections: Optional[dict] = None) -> tuple[str, list]:
    """Apply safe brand corrections. Returns (corrected_text, changes).

    Longer terms first so "wave warz" wins before "wave". Case-insensitive match,
    exact replacement casing (so "wave wars" and "Wave Wars" both -> "WaveWarZ").
    """
    corr = corrections or load_corrections()
    safe = corr.get("safe", {})
    changes = []
    # apply longest keys first to avoid partial shadowing
    for wrong in sorted(safe.keys(), key=len, reverse=True):
        right = safe[wrong]
        pat = _whole_word_pattern(wrong)
        count = len(pat.findall(text))
        if count:
            text = pat.sub(right, text)
            changes.append({"from": wrong, "to": right, "count": count})
    return text, changes


def flag_review_terms(text: str, corrections: Optional[dict] = None) -> list:
    """Find review-only terms present in the text. Never edits; returns flags."""
    corr = corrections or load_corrections()
    flags = []
    for rule in corr.get("review", []):
        term = rule.get("term", "")
        if not term:
            continue
        if _whole_word_pattern(term).search(text):
            flags.append({
                "term": term,
                "suggestion": rule.get("to"),
                "note": rule.get("note", ""),
            })
    return flags


# --- Number / time formatting (spec section 4b) ---

_WORD_NUM = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000, "million": 1000000,
}


def _words_to_number(phrase: str) -> Optional[float]:
    """Convert a short spelled-out number phrase to a value. Handles 'point' decimals."""
    tokens = phrase.lower().replace("-", " ").split()
    if not tokens or any(t not in _WORD_NUM and t != "point" and t != "and" for t in tokens):
        return None
    if "point" in tokens:
        idx = tokens.index("point")
        whole_tokens, dec_tokens = tokens[:idx], tokens[idx + 1:]
        whole = _accumulate(whole_tokens) if whole_tokens else 0
        if whole is None:
            return None
        # decimals are read digit by digit: "zero five" -> .05
        digits = "".join(str(_WORD_NUM[t]) for t in dec_tokens if t in _WORD_NUM and _WORD_NUM[t] < 10)
        if not digits:
            return None
        return float(f"{int(whole)}.{digits}")
    val = _accumulate(tokens)
    return float(val) if val is not None else None


def _accumulate(tokens: list) -> Optional[int]:
    total, current = 0, 0
    for t in tokens:
        if t in ("and",):
            continue
        if t not in _WORD_NUM:
            return None
        v = _WORD_NUM[t]
        if v in (100,):
            current = (current or 1) * v
        elif v in (1000, 1000000):
            total += (current or 1) * v
            current = 0
        else:
            current += v
    return total + current


# alternation of all number words (longest-first so "seventeen" beats "seven")
_NUM_WORDS = sorted(list(_WORD_NUM.keys()) + ["point", "and"], key=len, reverse=True)
_NUM_ALT = "|".join(_NUM_WORDS)
# a maximal run of number words
_NUM_RUN = rf"(?:{_NUM_ALT})(?:\s+(?:{_NUM_ALT}))*"


def format_numbers(text: str) -> str:
    """Apply the spec's number/time formatting rules to readable text."""
    # times first: "eight thirty PM EST" -> "8:30pm EST"
    def _time(m):
        h = _WORD_NUM.get(m.group(1).lower())
        mnt = _WORD_NUM.get(m.group(2).lower())
        if h is None or mnt is None or h > 12 or mnt >= 60:
            return m.group(0)
        ampm = m.group(3).lower().replace(".", "")
        tz = (" " + m.group(4)) if m.group(4) else ""
        return f"{h}:{mnt:02d}{ampm}{tz}"
    text = re.sub(r"\b(\w+)\s+(\w+)\s+([AaPp]\.?[Mm]\.?)\s*([A-Z]{2,4})?\b", _time, text)

    # "forty plus" / "forty-plus" -> "40-plus"
    def _plus(m):
        n = _words_to_number(m.group(1))
        return f"{int(n)}-plus" if n is not None else m.group(0)
    text = re.sub(rf"\b({_NUM_RUN})[\s-]+plus\b", _plus, text, flags=re.IGNORECASE)

    # spelled amounts before a unit: "point five SOL" -> "0.5 SOL", "five hundred SOL" -> "500 SOL"
    units = r"(SOL|ETH|USDC|dollars?|percent|%)"
    def _amount(m):
        n = _words_to_number(m.group(1))
        if n is None:
            return m.group(0)
        return f"{n:g} {m.group(2)}"
    text = re.sub(rf"\b({_NUM_RUN})\s+{units}", _amount, text, flags=re.IGNORECASE)

    # bare "point zero five" -> "0.05"
    def _bare_point(m):
        n = _words_to_number(m.group(0))
        return f"{n:g}" if n is not None else m.group(0)
    text = re.sub(r"\bpoint(?:\s+(?:zero|one|two|three|four|five|six|seven|eight|nine)){1,3}\b",
                  _bare_point, text, flags=re.IGNORECASE)

    return text


def add_safe_correction(wrong: str, right: str, path: Optional[Path] = None) -> dict:
    """Teach the glossary a new safe correction (wrong -> right), persisted.

    Idempotent on the lowercased wrong form. Returns the updated corrections dict.
    This is how the UI's 'fix a term' makes a correction stick for every future
    recording.
    """
    p = path or CORRECTIONS_PATH
    wrong = (wrong or "").strip()
    right = (right or "").strip()
    if not wrong or not right:
        raise ValueError("Both the wrong and correct terms are required")
    data = {"safe": {}, "review": []}
    if p.exists():
        with open(p) as f:
            data = json.load(f)
    safe = data.setdefault("safe", {})
    if isinstance(safe, list):
        # zabalgames {from,to} list format - update in place or append, stays
        # compatible with their scripts/fix-transcript.mjs.
        for r in safe:
            if r.get("from", "").lower() == wrong.lower():
                r["to"] = right
                break
        else:
            safe.append({"from": wrong, "to": right})
    else:
        safe[wrong.lower()] = right
    with open(p, "w") as f:
        json.dump(data, f, indent=2)
    return load_corrections(p)


def correct_transcript_text(text: str, corrections: Optional[dict] = None,
                            do_number_format: bool = False) -> dict:
    """Full stage-C pass over a block of text.

    Returns {"text", "safe_changes", "review_flags"}. Number formatting is opt-in
    (used for the readable transcript, not the timestamped cut transcript).
    """
    corr = corrections or load_corrections()
    flags = flag_review_terms(text, corr)
    corrected, changes = apply_safe_corrections(text, corr)
    if do_number_format:
        corrected = format_numbers(corrected)
    return {"text": corrected, "safe_changes": changes, "review_flags": flags}
