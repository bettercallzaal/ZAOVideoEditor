import json
import re
from pathlib import Path

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
        # Case-insensitive word boundary replacement
        pattern = re.compile(re.escape(wrong), re.IGNORECASE)
        text = pattern.sub(correct, text)

    return text


def apply_corrections_to_segments(segments: list) -> list:
    """Apply dictionary corrections to transcript segments."""
    corrected = []
    for seg in segments:
        new_seg = dict(seg)
        new_seg["text"] = apply_corrections(seg["text"])
        if seg.get("words"):
            new_words = []
            for w in seg["words"]:
                new_w = dict(w)
                new_w["word"] = apply_corrections(w["word"])
                new_words.append(new_w)
            new_seg["words"] = new_words
        corrected.append(new_seg)
    return corrected
