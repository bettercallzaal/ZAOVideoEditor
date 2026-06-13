"""Auto-mark suggestions: surface clippable moments from the live transcript.

As the live transcript fills in, scan it for cues that usually mean "this is
clippable" - excitement phrases, brand mentions, and audience questions - and
suggest marks the host can accept with one tap. It only suggests; the host still
decides. Pure function over segments, so it runs the same on a finished
transcript or a rolling live one.
"""

# Phrases that usually flag a high-energy / quotable moment.
CUE_PHRASES = [
    "let's go", "lets go", "that's huge", "thats huge", "oh my god", "no way",
    "this is the", "the key", "the point is", "exactly", "100%", "one hundred percent",
    "incredible", "amazing", "insane", "unbelievable", "game changer", "game-changer",
    "mind blowing", "mind-blowing", "the secret", "here's the thing", "heres the thing",
    "most important", "the big", "blew my mind", "love this", "this is fire",
    "shout out", "shoutout", "the takeaway", "pro tip", "hot take",
]

# ZAO ecosystem brands - a moment naming one is usually worth a clip.
BRAND_TERMS = [
    "wavewarz", "songjam", "zabal", "zaostock", "the zao", "coc concertz",
    "stilo world", "fishbowlz", "magnetiq", "bettercallzaal", "zoe", "hermes",
]


def _hit(text_l: str, terms: list) -> str:
    for t in terms:
        if t in text_l:
            return t
    return ""


def suggest_marks(segments: list, brand_terms: list = None, cue_phrases: list = None,
                  min_gap: float = 15.0, max_suggestions: int = 25) -> list:
    """Suggest marks from transcript segments.

    Returns [{at, note, reason}] sorted by time, de-duplicated so no two
    suggestions land within `min_gap` seconds of each other (the first/earliest
    in a cluster wins). reason is one of: phrase, brand, question.
    """
    brands = [b.lower() for b in (brand_terms if brand_terms is not None else BRAND_TERMS)]
    cues = [c.lower() for c in (cue_phrases if cue_phrases is not None else CUE_PHRASES)]

    raw = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        tl = text.lower()
        reason = ""
        if _hit(tl, cues):
            reason = "phrase"
        elif _hit(tl, brands):
            reason = "brand"
        elif text.rstrip().endswith("?") and len(text.split()) >= 4:
            reason = "question"
        if not reason:
            continue
        note = text if len(text) <= 70 else text[:67].rstrip() + "..."
        raw.append({"at": round(float(seg.get("start", 0.0)), 1), "note": note, "reason": reason})

    raw.sort(key=lambda m: m["at"])
    out = []
    last = None
    for m in raw:
        if last is not None and m["at"] - last < min_gap:
            continue
        out.append(m)
        last = m["at"]
        if len(out) >= max_suggestions:
            break
    return out
