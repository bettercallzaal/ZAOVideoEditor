#!/usr/bin/env python3
"""Verify a transcript by reading the words. The signal the render eval cannot see.

verify_render measures pixels. It passed, with every check green, on a 54-minute
video whose transcript was the phrase "So, yeah." repeated five hundred times.
The pixels were fine. Only the words were wrong, and nothing looked at the words.

Whisper's own confidence is worthless here: the collapsed transcript scored
avg_logprob -0.030, BETTER than a healthy one's -0.144. Repeated tokens are
trivially predictable, so the model is most confident exactly when it is looping.
Do not use confidence to detect collapse. Measure the text.

    python scripts/verify_transcript.py out/transcripts/space.cut.json --duration 3250

Exits 0 when the transcript looks like a conversation, 1 when it looks like a
loop. Prints a JSON report either way. Import verify() as a test assertion or a
loop's rubric.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# Measured on real transcripts:
#   collapsed 54-min space          0.967
#   5-min slice catching loop start 0.420
#   healthy 5-min slice (post-fix)  0.000
# 0.10 sits ~4x under the mildest real failure and above any plausible
# conversation, where a filler line repeats occasionally but never dominates.
MAX_SEGMENT_REPETITION = 0.10

# A loop inside one segment: "cast, cast, cast, cast, ...". Segment-to-segment
# repetition never sees this - the AMA transcript scored 0.000 while its opening
# segment was pure prompt echo and its last was one word fifty times.
MAX_INTRA_SEGMENT_REPETITION = 0.55

# Windowed vocabulary diversity (see vocab_diversity). Measured on the same
# 54-minute recording: collapsed 0.064, healthy 0.434, and the healthy value holds
# at 0.426-0.439 across a quarter, half and all of the transcript. 0.15 clears the
# collapse by 2.3x and sits 2.9x under a real conversation.
MIN_VOCAB_DIVERSITY = 0.15

# Whisper decodes initial_prompt as speech, so a glossary term list gets echoed
# into the opening segments. Never inject one; this catches a regression.
#
# Matching the literal word "Glossary" is not enough: a real echo read back the
# TERMS without the label - "Farcaster, Ohnahji, Saltorius, SongJam, WaveWarZ,
# Zabal, Zabal, ..." - and scored zero. Detect the shape instead: an opening
# segment that is mostly comma-separated proper nouns and almost no verbs.
_PROMPT_LABEL = re.compile(r"\bglossar(y|ies)\b", re.IGNORECASE)

# Fraction of an opening segment's tokens that are comma-separated capitalised
# terms, above which it reads as a term list rather than speech.
_ECHO_TERM_RATIO = 0.6

# Only intra-segment loops and prompt echo can be judged on a single segment.
# Segment-to-segment repetition and vocabulary need a real sample: three
# segments of someone saying "yeah" is not a loop.
MIN_SEGMENTS_TO_JUDGE = 10


def _texts(segments: list) -> list:
    return [(s.get("text") or "").strip() for s in segments if (s.get("text") or "").strip()]


def segment_repetition(segments: list) -> float:
    """Fraction of segments identical to the one before them."""
    texts = _texts(segments)
    if len(texts) < MIN_SEGMENTS_TO_JUDGE:
        return 0.0
    dup = sum(1 for i in range(1, len(texts)) if texts[i] == texts[i - 1])
    return dup / len(texts)


def intra_segment_repetition(segments: list) -> float:
    """Worst single-token dominance within any one segment.

    "cast, cast, cast, cast" -> 1.0. Real speech peaks well below 0.5 even on a
    filler-heavy line. Only segments long enough to be meaningful are scored.
    """
    worst = 0.0
    for text in _texts(segments):
        words = re.findall(r"[a-z']+", text.lower())
        if len(words) < 8:
            continue
        top = Counter(words).most_common(1)[0][1]
        worst = max(worst, top / len(words))
    return worst


VOCAB_WINDOW = 500


def vocab_diversity(segments: list) -> float:
    """Mean unique-word ratio over sliding windows. A loop has a tiny vocabulary.

    Windowed, because a plain unique/total ratio falls as a transcript gets
    longer - vocabulary saturates while the word count keeps climbing. Measured
    on ONE healthy 54-minute transcript:

        first   200 words -> 0.605
        first  2000 words -> 0.270
        all    8581 words -> 0.152

    A fixed threshold on that number is really a threshold on duration. This
    transcript scored 0.152 against a 0.15 limit - a 1.4% margin - and a healthy
    two-hour recording would have been rejected outright. Averaging the ratio over
    fixed-size windows removes the length dependence.
    """
    words = re.findall(r"[a-z']+", " ".join(_texts(segments)).lower())
    if len(words) < 50:
        return 1.0
    if len(words) <= VOCAB_WINDOW:
        return len(set(words)) / len(words)

    step = max(1, VOCAB_WINDOW // 2)
    ratios = [
        len(set(words[i:i + VOCAB_WINDOW])) / VOCAB_WINDOW
        for i in range(0, len(words) - VOCAB_WINDOW + 1, step)
    ]
    return sum(ratios) / len(ratios)


def words_per_minute(segments: list) -> float:
    if not segments:
        return 0.0
    span = segments[-1].get("end", 0) - segments[0].get("start", 0)
    if span <= 0:
        return 0.0
    words = re.findall(r"[a-z']+", " ".join(_texts(segments)).lower())
    return len(words) / (span / 60)


# Speech is held together by function words; a term list has none of them.
# "Oh shit, Kenny, there we go. Okay, I think we finally made it." is 5 comma
# parts, three of which look termish - so counting capitalised parts alone
# flags real speech. Requiring zero function words and no sentence punctuation
# separates the two cleanly.
_FUNCTION_WORDS = frozenset(
    "a an the i we you he she it they is are was were be been am do does did "
    "to of in on at for with from that this these those and or but so if then "
    "have has had can could would should will just like what who how why not "
    "my your his her our their me him them us there here".split()
)


def _is_term_list(text: str) -> bool:
    """True when a line reads as a comma-separated glossary rather than speech."""
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) < 4:
        return False
    # Sentence punctuation mid-line means prose, not a list.
    if re.search(r"[.!?]", text[:-1]):
        return False
    words = re.findall(r"[a-z']+", text.lower())
    if any(w in _FUNCTION_WORDS for w in words):
        return False

    termish = sum(1 for p in parts if len(p.split()) <= 3 and p[:1].isupper())
    return termish / len(parts) >= _ECHO_TERM_RATIO


def prompt_echo_segments(segments: list, head: int = 5) -> list:
    """Opening segments that look like the glossary prompt read back as speech."""
    return [t for t in _texts(segments)[:head]
            if _PROMPT_LABEL.search(t) or _is_term_list(t)]


def coverage(segments: list, audio_duration: float) -> float:
    """Fraction of the audio the transcript actually spans."""
    if not segments or not audio_duration:
        return 1.0
    return min(1.0, (segments[-1].get("end", 0) - segments[0].get("start", 0)) / audio_duration)


def verify(segments: list, audio_duration: float = None) -> dict:
    """Judge a transcript. Returns a report; never raises on a failed check."""
    checks = []

    n = len(_texts(segments))
    checks.append(("has_segments", n > 0, f"{n} non-empty segments"))
    if not n:
        return _report(checks)

    # These two need only ONE segment. A four-segment transcript whose opening
    # line is the echoed prompt and whose closing line is "cast, cast, cast, ..."
    # used to short-circuit past every check and pass.
    intra = intra_segment_repetition(segments)
    checks.append(("no_intra_segment_loop", intra < MAX_INTRA_SEGMENT_REPETITION,
                   f"worst segment is {intra:.0%} one repeated word "
                   f"(limit {MAX_INTRA_SEGMENT_REPETITION:.0%})"))

    echo = prompt_echo_segments(segments)
    checks.append(("no_glossary_prompt_echo", not echo,
                   f"{len(echo)} opening segments look like the injected prompt"
                   + (f": {echo[0][:60]!r}" if echo else "")))

    # These need a real sample: three segments of someone saying "yeah" is not a
    # loop, and a one-line clip has trivially perfect vocabulary diversity.
    if n < MIN_SEGMENTS_TO_JUDGE:
        checks.append(("sample_too_small_for_rate_checks", True,
                       f"{n} segments; skipping repetition/vocab/rate "
                       f"(need {MIN_SEGMENTS_TO_JUDGE})"))
        return _report(checks)

    rep = segment_repetition(segments)
    checks.append(("no_segment_repetition_loop", rep < MAX_SEGMENT_REPETITION,
                   f"{rep:.1%} of segments repeat the previous one "
                   f"(limit {MAX_SEGMENT_REPETITION:.0%})"))

    div = vocab_diversity(segments)
    checks.append(("vocabulary_is_diverse", div >= MIN_VOCAB_DIVERSITY,
                   f"{div:.1%} unique words (need {MIN_VOCAB_DIVERSITY:.0%})"))

    wpm = words_per_minute(segments)
    checks.append(("plausible_speech_rate", 40 <= wpm <= 400,
                   f"{wpm:.0f} words/min"))

    if audio_duration:
        cov = coverage(segments, audio_duration)
        checks.append(("spans_the_audio", cov >= 0.80,
                       f"transcript spans {cov:.0%} of {audio_duration / 60:.0f} min"))

    return _report(checks)


def _report(checks: list) -> dict:
    failed = [c[0] for c in checks if not c[1]]
    return {
        "ok": not failed,
        "failed": failed,
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("transcript", help="a *.cut.json written by process_recording")
    p.add_argument("--duration", type=float, help="audio duration in seconds")
    args = p.parse_args()

    segments = json.loads(Path(args.transcript).read_text())
    report = verify(segments, audio_duration=args.duration)

    print(json.dumps(report, indent=2))
    for c in report["checks"]:
        print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}",
              file=sys.stderr)

    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
