"""Word-level filler detection using transcript word timestamps.

Identifies filler words (um, uh, like, you know, etc.) at the word level
with precise timestamps. Enables one-click removal in the UI.
"""

import re
from typing import Optional


# Single-word fillers
FILLER_WORDS = {
    "um", "uh", "er", "ah", "eh", "hm", "hmm", "uhm", "mm",
    "umm", "uhh", "ahh", "ehh",
}

# Multi-word filler phrases (checked as sequences)
FILLER_PHRASES = [
    ["you", "know"],
    ["i", "mean"],
    ["kind", "of"],
    ["sort", "of"],
    ["like", "you", "know"],
]

def _is_filler_like(words: list, idx: int) -> bool:
    """Check if 'like' at position idx is a filler (not 'I like X')."""
    if idx == 0:
        return True  # Sentence-start "like" is usually filler

    prev_word = words[idx - 1]["word"].strip().lower().rstrip(",.")
    # "I like", "would like", "looks like" — NOT filler
    if prev_word in {"i", "would", "looks", "looked", "look", "sounds", "feels",
                     "dont", "don't", "didn't", "doesn't", "really"}:
        return False

    # Check if next word suggests comparison: "like a", "like the" — could be filler
    if idx + 1 < len(words):
        next_word = words[idx + 1]["word"].strip().lower().rstrip(",.")
        # "like $X" where X is a noun/adj — likely filler
        if next_word in {"a", "the", "this", "that", "so", "really", "super",
                         "very", "kind", "sort", "just"}:
            return True

    # Default: if it's surrounded by commas or at phrase boundary, likely filler
    word_text = words[idx]["word"].strip()
    if word_text.endswith(",") or (idx > 0 and words[idx - 1]["word"].strip().endswith(",")):
        return True

    return False


def _is_filler_adverb(words: list, idx: int) -> bool:
    """Check if an adverb (basically, literally, actually) is filler."""
    word_text = words[idx]["word"].strip()
    # If followed by comma, likely filler: "basically, ..."
    if word_text.endswith(","):
        return True
    # If at start of segment, likely filler
    if idx == 0:
        return True
    return False


def _is_filler_right(words: list, idx: int) -> bool:
    """Check if 'right' is a filler (not 'that's right' or 'the right way')."""
    word_text = words[idx]["word"].strip().rstrip(",.")
    if word_text != "right":
        return False

    # End of sentence or followed by question mark — likely filler
    if words[idx]["word"].strip().endswith("?"):
        return True

    # After a statement, standalone "right" is filler
    if idx > 0:
        prev = words[idx - 1]["word"].strip().lower().rstrip(",.")
        if prev in {"that's", "that", "the", "all"}:
            return False  # "that's right", "the right"
        return True  # standalone "right" after other words

    return False


# Fix forward reference issue — rebuild CONTEXTUAL_FILLERS after function defs
CONTEXTUAL_FILLERS = {
    "like": _is_filler_like,
    "basically": _is_filler_adverb,
    "literally": _is_filler_adverb,
    "actually": _is_filler_adverb,
    "right": _is_filler_right,
}


def detect_fillers(segments: list) -> dict:
    """Detect all filler words/phrases in transcript segments.

    Returns a summary with:
    - fillers: list of detected fillers with timestamps and type
    - segments: segments annotated with filler markers on words
    - stats: count of each filler type
    """
    all_fillers = []
    annotated_segments = []
    stats = {}

    for seg in segments:
        words = seg.get("words", [])
        if not words:
            annotated_segments.append(seg)
            continue

        new_seg = dict(seg)
        new_words = []
        skip_until = -1

        for i, word_data in enumerate(words):
            if i < skip_until:
                new_words.append(word_data)
                continue

            word_clean = word_data["word"].strip().lower().rstrip(".,!?;:")
            new_word = dict(word_data)

            # Check single-word fillers
            if word_clean in FILLER_WORDS:
                new_word["is_filler"] = True
                new_word["filler_type"] = "filler_word"
                filler_entry = {
                    "word": word_data["word"].strip(),
                    "start": word_data["start"],
                    "end": word_data["end"],
                    "type": "filler_word",
                    "segment_id": seg["id"],
                }
                all_fillers.append(filler_entry)
                stats[word_clean] = stats.get(word_clean, 0) + 1

            # Check multi-word phrases
            elif _check_phrase_filler(words, i):
                phrase, phrase_len = _get_matching_phrase(words, i)
                if phrase:
                    new_word["is_filler"] = True
                    new_word["filler_type"] = "filler_phrase"
                    # Mark subsequent words in phrase too
                    for j in range(i + 1, min(i + phrase_len, len(words))):
                        if j < len(words):
                            w = dict(words[j])
                            w["is_filler"] = True
                            w["filler_type"] = "filler_phrase"
                    skip_until = i + phrase_len

                    phrase_text = " ".join(phrase)
                    filler_entry = {
                        "word": phrase_text,
                        "start": word_data["start"],
                        "end": words[min(i + phrase_len - 1, len(words) - 1)]["end"],
                        "type": "filler_phrase",
                        "segment_id": seg["id"],
                    }
                    all_fillers.append(filler_entry)
                    stats[phrase_text] = stats.get(phrase_text, 0) + 1

            # Check contextual fillers
            elif word_clean in CONTEXTUAL_FILLERS:
                checker = CONTEXTUAL_FILLERS[word_clean]
                if checker(words, i):
                    new_word["is_filler"] = True
                    new_word["filler_type"] = "contextual_filler"
                    filler_entry = {
                        "word": word_data["word"].strip(),
                        "start": word_data["start"],
                        "end": word_data["end"],
                        "type": "contextual_filler",
                        "segment_id": seg["id"],
                    }
                    all_fillers.append(filler_entry)
                    stats[word_clean] = stats.get(word_clean, 0) + 1

            new_words.append(new_word)

        new_seg["words"] = new_words
        annotated_segments.append(new_seg)

    return {
        "fillers": all_fillers,
        "segments": annotated_segments,
        "stats": stats,
        "total_fillers": len(all_fillers),
        "total_duration": sum(f["end"] - f["start"] for f in all_fillers),
    }


def _check_phrase_filler(words: list, idx: int) -> bool:
    """Check if words starting at idx match any filler phrase."""
    for phrase in FILLER_PHRASES:
        if idx + len(phrase) <= len(words):
            match = True
            for j, p_word in enumerate(phrase):
                w = words[idx + j]["word"].strip().lower().rstrip(".,!?;:")
                if w != p_word:
                    match = False
                    break
            if match:
                return True
    return False


def _get_matching_phrase(words: list, idx: int) -> tuple:
    """Get the matching filler phrase and its length."""
    for phrase in FILLER_PHRASES:
        if idx + len(phrase) <= len(words):
            match = True
            for j, p_word in enumerate(phrase):
                w = words[idx + j]["word"].strip().lower().rstrip(".,!?;:")
                if w != p_word:
                    match = False
                    break
            if match:
                return phrase, len(phrase)
    return None, 0


def remove_fillers_from_transcript(segments: list, filler_types: list = None) -> list:
    """Remove detected filler words from transcript segments.

    Args:
        segments: Annotated segments (from detect_fillers)
        filler_types: Which types to remove. Default: all types.
                      Options: "filler_word", "filler_phrase", "contextual_filler"

    Returns updated segments with fillers removed from text and words.
    """
    if filler_types is None:
        filler_types = ["filler_word", "filler_phrase", "contextual_filler"]

    cleaned = []
    for seg in segments:
        new_seg = dict(seg)
        words = seg.get("words", [])

        if not words:
            cleaned.append(new_seg)
            continue

        # Filter out filler words
        kept_words = []
        for w in words:
            if w.get("is_filler") and w.get("filler_type") in filler_types:
                continue
            kept_words.append(w)

        # Rebuild text from remaining words
        if kept_words:
            new_text = "".join(w["word"] for w in kept_words).strip()
            # Clean up punctuation artifacts
            new_text = re.sub(r'\s{2,}', ' ', new_text)
            new_text = re.sub(r',\s*,', ',', new_text)
            new_text = re.sub(r'^\s*,\s*', '', new_text)
            new_seg["text"] = new_text
            new_seg["words"] = kept_words
            cleaned.append(new_seg)
        # Skip empty segments

    return cleaned
