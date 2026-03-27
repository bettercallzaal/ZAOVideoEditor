import json
import re
from pathlib import Path
from typing import Optional

DICTIONARY_PATH = Path(__file__).parent.parent.parent / "shared" / "dictionary.json"


def load_dictionary() -> dict:
    """Load the correction dictionary."""
    if DICTIONARY_PATH.exists():
        with open(DICTIONARY_PATH, "r") as f:
            return json.load(f)
    return {"corrections": {}}


def save_dictionary(data: dict):
    """Save the correction dictionary."""
    DICTIONARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DICTIONARY_PATH, "w") as f:
        json.dump(data, f, indent=2)


def add_correction(wrong: str, correct: str):
    """Add a correction to the dictionary."""
    data = load_dictionary()
    data["corrections"][wrong.lower()] = correct
    save_dictionary(data)


def remove_correction(wrong: str):
    """Remove a correction from the dictionary."""
    data = load_dictionary()
    key = wrong.lower()
    if key in data["corrections"]:
        del data["corrections"][key]
        save_dictionary(data)


def apply_corrections(text: str) -> str:
    """Apply dictionary corrections to text."""
    data = load_dictionary()
    corrections = data.get("corrections", {})

    # Sort by length descending so longer phrases match first
    sorted_keys = sorted(corrections.keys(), key=len, reverse=True)

    for wrong in sorted_keys:
        correct = corrections[wrong]
        # Case-insensitive replacement with word boundaries to avoid partial matches
        pattern = re.compile(r'\b' + re.escape(wrong) + r'\b', re.IGNORECASE)
        text = pattern.sub(correct, text)

    return text


def apply_fuzzy_corrections(text: str, threshold: float = 80.0) -> str:
    """Apply fuzzy/phonetic dictionary corrections to text.

    Uses rapidfuzz for similarity matching to catch phonetic misspellings
    like "sal torius" -> "Saltorius". Only applies when no exact match exists.
    """
    try:
        from rapidfuzz import fuzz
    except ImportError:
        # rapidfuzz not installed — skip fuzzy matching
        return text

    data = load_dictionary()
    corrections = data.get("corrections", {})
    if not corrections:
        return text

    words = text.split()

    # Separate single-word and multi-word correction keys
    single_keys = {k: v for k, v in corrections.items() if ' ' not in k}
    multi_keys = {k: v for k, v in corrections.items() if ' ' in k}

    # --- Pass 1: Check bigrams/trigrams against multi-word keys ---
    for key, correct in sorted(multi_keys.items(), key=lambda x: len(x[0]), reverse=True):
        key_word_count = len(key.split())
        i = 0
        while i <= len(words) - key_word_count:
            ngram = ' '.join(words[i:i + key_word_count]).lower()
            # Skip if it's already an exact match (handled by apply_corrections)
            if ngram == key:
                i += 1
                continue
            score = fuzz.ratio(ngram, key)
            if score >= threshold:
                # Replace the ngram with the correction
                words[i:i + key_word_count] = [correct]
                # Don't advance past the replacement
                i += 1
            else:
                i += 1

    # --- Pass 2: Check individual words against single-word keys AND
    #     collapsed multi-word keys (e.g., "saltorias" vs "sal torius" → "saltorius") ---
    all_keys = dict(single_keys)
    # Add collapsed versions of multi-word keys for single-word fuzzy matching
    for key, correct in multi_keys.items():
        collapsed = key.replace(" ", "")
        all_keys[collapsed] = correct

    for i, word in enumerate(words):
        # Strip punctuation for matching but preserve it for reconstruction
        stripped = word.strip('.,!?;:"\'-()[]{}')
        if not stripped:
            continue
        lower = stripped.lower()

        # Skip if exact match exists (already handled by apply_corrections)
        if lower in corrections:
            continue

        best_score = 0.0
        best_correction: Optional[str] = None
        for key, correct in all_keys.items():
            score = fuzz.ratio(lower, key)
            if score > best_score and score >= threshold:
                best_score = score
                best_correction = correct

        if best_correction is not None:
            # Preserve surrounding punctuation
            prefix = word[:len(word) - len(word.lstrip('.,!?;:"\'-()[]{}'))]
            suffix = word[len(stripped) + len(prefix):]
            words[i] = prefix + best_correction + suffix

    return ' '.join(words)


def apply_corrections_to_segments(segments: list) -> list:
    """Apply dictionary corrections to transcript segments."""
    corrected = []
    for seg in segments:
        new_seg = dict(seg)
        # Exact matching first, then fuzzy/phonetic matching
        new_seg["text"] = apply_fuzzy_corrections(apply_corrections(seg["text"]))
        if seg.get("words"):
            new_words = []
            for w in seg["words"]:
                new_w = dict(w)
                new_w["word"] = apply_fuzzy_corrections(apply_corrections(w["word"]))
                new_words.append(new_w)
            new_seg["words"] = new_words
        corrected.append(new_seg)
    return corrected


def learn_from_edits(before_segments: list, after_segments: list):
    """Auto-learn new dictionary corrections by diffing pre-edit and post-edit segments.

    Compares segment text before and after user edits. When a user consistently
    changes the same word/phrase, it gets added to the dictionary automatically.
    """
    data = load_dictionary()
    corrections = data.get("corrections", {})
    candidates = data.get("_candidates", {})  # track frequency before promoting

    # Build text maps keyed by segment ID for alignment
    before_map = {seg.get("id", i): seg["text"] for i, seg in enumerate(before_segments)}
    after_map = {seg.get("id", i): seg["text"] for i, seg in enumerate(after_segments)}

    new_pairs = []
    for seg_id in before_map:
        if seg_id not in after_map:
            continue
        old_text = before_map[seg_id]
        new_text = after_map[seg_id]
        if old_text == new_text:
            continue

        # Extract word-level diffs
        old_words = old_text.split()
        new_words = new_text.split()

        from difflib import SequenceMatcher
        sm = SequenceMatcher(None, old_words, new_words)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == 'replace':
                old_phrase = ' '.join(old_words[i1:i2]).strip()
                new_phrase = ' '.join(new_words[j1:j2]).strip()
                # Only learn short replacements (1-3 words) to avoid noise
                if old_phrase and new_phrase and len(old_words[i1:i2]) <= 3:
                    new_pairs.append((old_phrase.lower(), new_phrase))

    if not new_pairs:
        return

    # Track candidates — promote to dictionary after 2+ occurrences
    changed = False
    for wrong, correct in new_pairs:
        # Skip if already in dictionary
        if wrong in corrections:
            continue
        # Skip if the "wrong" text is the same as "correct" (case-insensitive)
        if wrong == correct.lower():
            continue

        if wrong in candidates:
            candidates[wrong]["count"] += 1
            candidates[wrong]["correct"] = correct
            # Promote to dictionary after seen twice
            if candidates[wrong]["count"] >= 2:
                corrections[wrong] = correct
                del candidates[wrong]
                changed = True
        else:
            candidates[wrong] = {"correct": correct, "count": 1}
            changed = True

    if changed or new_pairs:
        data["corrections"] = corrections
        data["_candidates"] = candidates
        save_dictionary(data)
