"""Highlight / short clip detection from transcript.

Identifies the most engaging 30-90 second segments for short-form content.
Scores segments based on: entity density, questions, strong statements,
emotional language, and topic diversity.
"""

import re
from collections import Counter


# Words/phrases that signal engaging content
ENGAGEMENT_SIGNALS = {
    # Strong statements
    "never", "always", "absolutely", "completely", "exactly",
    "incredible", "insane", "crazy", "amazing", "perfect",
    "biggest", "fastest", "first", "best", "worst",
    # Insight/revelation
    "realized", "discovered", "learned", "figured", "understood",
    "secret", "trick", "hack", "strategy", "approach",
    # Emotional
    "love", "hate", "obsessed", "passionate", "excited",
    "frustrated", "surprised", "shocked", "inspired",
    # Conflict/tension
    "problem", "challenge", "struggle", "fight", "battle",
    "impossible", "difficult", "controversial", "debate",
    # Numbers/specifics
    "percent", "thousand", "million", "billion", "dollars",
    "$", "100%",
}

# Patterns that indicate quotable moments
QUOTE_PATTERNS = [
    r"the (?:thing|key|secret|trick) (?:is|was)",
    r"what (?:if|people don't|most people)",
    r"(?:i|we) (?:think|believe|realized|learned|figured out)",
    r"(?:the biggest|the most|the best|the worst)",
    r"(?:here's|here is) (?:the thing|what|why|how)",
    r"(?:you|nobody|everybody) (?:should|needs to|has to)",
]


def detect_highlights(segments: list, min_duration: float = 30.0,
                      max_duration: float = 90.0,
                      count: int = 5) -> list:
    """Detect the most engaging segments for short clips.

    Returns list of highlights, each with:
    - start/end timestamps
    - score (0-100)
    - title (auto-generated)
    - segment_ids covered
    - reason (why it scored high)
    """
    if not segments or len(segments) < 5:
        return []

    total_duration = segments[-1]["end"]

    # Score every possible window
    window_scores = []

    # Slide a window across segments
    for i in range(len(segments)):
        # Find window end
        window_start = segments[i]["start"]

        for j in range(i + 1, len(segments)):
            window_end = segments[j]["end"]
            window_duration = window_end - window_start

            if window_duration < min_duration:
                continue
            if window_duration > max_duration:
                break

            # Score this window
            window_segs = segments[i:j + 1]
            score, reasons = _score_window(window_segs)

            if score > 0:
                window_scores.append({
                    "start": round(window_start, 2),
                    "end": round(window_end, 2),
                    "duration": round(window_duration, 1),
                    "score": score,
                    "reasons": reasons,
                    "start_seg": i,
                    "end_seg": j,
                })

    # Sort by score
    window_scores.sort(key=lambda x: x["score"], reverse=True)

    # Select top non-overlapping highlights
    selected = []
    used_ranges = []

    for window in window_scores:
        if len(selected) >= count:
            break

        # Check overlap with already selected
        overlaps = False
        for used in used_ranges:
            overlap_start = max(window["start"], used[0])
            overlap_end = min(window["end"], used[1])
            if overlap_end - overlap_start > 10:  # Allow small overlap
                overlaps = True
                break

        if not overlaps:
            # Generate a title for this highlight
            highlight_segs = segments[window["start_seg"]:window["end_seg"] + 1]
            title = _generate_highlight_title(highlight_segs)

            selected.append({
                "start": window["start"],
                "end": window["end"],
                "duration": window["duration"],
                "score": min(100, int(window["score"])),
                "title": title,
                "reasons": window["reasons"],
                "segment_ids": list(range(window["start_seg"], window["end_seg"] + 1)),
            })
            used_ranges.append((window["start"], window["end"]))

    # Sort by time
    selected.sort(key=lambda x: x["start"])

    return selected


def _score_window(segments: list) -> tuple:
    """Score a window of segments for engagement potential.

    Returns (score, list_of_reasons).
    """
    score = 0.0
    reasons = []

    full_text = " ".join(s["text"] for s in segments)
    text_lower = full_text.lower()
    words = text_lower.split()
    word_count = len(words)

    if word_count < 10:
        return 0, []

    # 1. Engagement signal density
    signal_hits = sum(1 for w in words
                      if w.rstrip(".,!?;:") in ENGAGEMENT_SIGNALS)
    signal_density = signal_hits / word_count
    if signal_density > 0.05:
        score += signal_density * 200
        reasons.append(f"{signal_hits} engagement signals")

    # 2. Questions (indicate interesting discussion)
    questions = sum(1 for s in segments if s["text"].strip().endswith("?"))
    if questions >= 1:
        score += questions * 8
        reasons.append(f"{questions} questions")

    # 3. Proper nouns / entities (specific > generic)
    proper_nouns = 0
    for seg in segments:
        for word in seg["text"].split():
            clean = re.sub(r'[^A-Za-z]', '', word)
            if clean and clean[0].isupper() and len(clean) > 2:
                proper_nouns += 1
    if proper_nouns > 3:
        score += proper_nouns * 3
        reasons.append(f"{proper_nouns} proper nouns")

    # 4. Quote-worthy patterns
    for pattern in QUOTE_PATTERNS:
        matches = re.findall(pattern, text_lower)
        if matches:
            score += len(matches) * 12
            reasons.append("quotable statement")
            break

    # 5. Word diversity (varied vocabulary = interesting content)
    unique_words = set(w.rstrip(".,!?;:") for w in words if len(w) > 3)
    diversity = len(unique_words) / max(word_count, 1)
    if diversity > 0.5:
        score += diversity * 30
        reasons.append("high vocabulary diversity")

    # 6. Conversation flow (back-and-forth between speakers)
    speakers = [s.get("speaker") for s in segments if s.get("speaker")]
    if speakers:
        speaker_changes = sum(1 for i in range(1, len(speakers))
                              if speakers[i] != speakers[i - 1])
        if speaker_changes >= 2:
            score += speaker_changes * 5
            reasons.append(f"{speaker_changes} speaker changes")

    # 7. Longer substantive segments (not just backchannels)
    substantive = sum(1 for s in segments if len(s["text"].split()) > 8)
    if substantive >= 3:
        score += substantive * 4
        reasons.append(f"{substantive} substantive segments")

    # 8. Penalize segments that are mostly filler/backchannel
    filler_segs = sum(1 for s in segments if len(s["text"].split()) <= 3)
    filler_ratio = filler_segs / len(segments)
    if filler_ratio > 0.5:
        score *= 0.5
        reasons.append("high filler ratio (penalized)")

    return round(score, 1), reasons


def _generate_highlight_title(segments: list) -> str:
    """Generate a short title for a highlight clip."""
    # Find the most interesting sentence in the window
    best_sent = ""
    best_score = -1

    for seg in segments:
        text = seg["text"].strip()
        words = text.split()
        if len(words) < 5:
            continue

        score = 0
        text_lower = text.lower()

        # Proper nouns
        for w in words:
            clean = re.sub(r'[^A-Za-z]', '', w)
            if clean and clean[0].isupper() and len(clean) > 2:
                score += 2

        # Engagement words
        for w in words:
            if w.lower().rstrip(".,!?;:") in ENGAGEMENT_SIGNALS:
                score += 1

        # Question
        if text.endswith("?"):
            score += 3

        if score > best_score:
            best_score = score
            best_sent = text

    if not best_sent:
        best_sent = segments[0]["text"]

    # Truncate to a title
    words = best_sent.split()
    if len(words) > 10:
        best_sent = " ".join(words[:10]) + "..."

    # Clean up
    best_sent = best_sent.strip().rstrip(".,!?;:")
    if best_sent:
        best_sent = best_sent[0].upper() + best_sent[1:]

    return best_sent


def export_clip_timestamps(highlight: dict) -> dict:
    """Get ffmpeg-ready timestamps for extracting a clip."""
    return {
        "start": highlight["start"],
        "end": highlight["end"],
        "duration": highlight["duration"],
        "ss": _format_ffmpeg_time(highlight["start"]),
        "to": _format_ffmpeg_time(highlight["end"]),
    }


def _format_ffmpeg_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm for ffmpeg."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"
