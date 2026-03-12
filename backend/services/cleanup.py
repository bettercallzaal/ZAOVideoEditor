import re


# Common filler words/phrases to remove
FILLER_PATTERNS = [
    r'\b(um+|uh+|er+|ah+|eh+|hm+|hmm+|uhm+)\b',
    r'\b(you know)\b(?=[\s,.])',
    r'\b(I mean)\b(?=[\s,.])',
    r'\b(like)\b(?=\s*,)',  # "like," as filler
    r'\b(sort of|kind of)\b(?=\s*,)',  # when used as filler before comma
    r'\b(basically)\b(?=\s*,)',
    r'\b(literally)\b(?=\s*,)',
]

# Repeated word patterns (stutters)
STUTTER_PATTERN = re.compile(r'\b(\w+)(\s+\1){1,}\b', re.IGNORECASE)


def remove_fillers(text: str) -> str:
    """Remove filler words from text."""
    for pattern in FILLER_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    # Clean up extra whitespace left behind
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'\s+,', ',', text)
    text = re.sub(r',\s*,', ',', text)
    text = re.sub(r'^\s*,\s*', '', text)
    return text.strip()


def fix_stutters(text: str) -> str:
    """Remove repeated words (stutters)."""
    return STUTTER_PATTERN.sub(r'\1', text)


def fix_capitalization(text: str) -> str:
    """Fix sentence capitalization."""
    # Capitalize after sentence endings
    text = re.sub(r'(^|[.!?]\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), text)
    # Capitalize "I" when standalone
    text = re.sub(r"\bi\b", "I", text)
    # Capitalize first character
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def fix_punctuation(text: str) -> str:
    """Improve punctuation."""
    # Remove duplicate punctuation
    text = re.sub(r'([.!?])\1+', r'\1', text)
    # Add period at end if missing
    text = text.strip()
    if text and text[-1] not in '.!?':
        text += '.'
    # Fix spacing after punctuation
    text = re.sub(r'([.!?,;:])\s*([A-Za-z])', r'\1 \2', text)
    # Remove spaces before punctuation
    text = re.sub(r'\s+([.!?,;:])', r'\1', text)
    return text


def cleanup_segment(text: str) -> str:
    """Apply all cleanup steps to a text segment."""
    text = remove_fillers(text)
    text = fix_stutters(text)
    text = fix_capitalization(text)
    text = fix_punctuation(text)
    return text


def cleanup_transcript(segments: list) -> list:
    """Clean up all segments in a transcript."""
    cleaned = []
    for seg in segments:
        new_seg = dict(seg)
        cleaned_text = cleanup_segment(seg["text"])
        if cleaned_text:  # Skip empty segments after cleanup
            new_seg["text"] = cleaned_text
            cleaned.append(new_seg)
    return cleaned
