"""Stage D: build a cut plan (edit sheet) from a word-timestamped transcript.

Conservative by default - only um/uh-class fillers and clear dead-air are
enabled. False-starts (LLM) and bleed (intro/outro) are SUGGESTED, never enabled
automatically: the human toggles them in review. Nothing here touches video; it
produces an edit sheet that render_service applies non-destructively.
"""

from typing import Optional

from .filler_detection import detect_fillers


# padding kept around a filler cut so speech isn't clipped (seconds)
_FILLER_PAD = 0.05
# a silence longer than this between words is "dead air" worth trimming
_GAP_THRESHOLD = 1.5
# keep this much air on each side of a trimmed gap so it doesn't feel abrupt
_GAP_KEEP = 0.35


def _all_words(segments: list) -> list:
    words = []
    for seg in segments:
        for w in seg.get("words", []) or []:
            if "start" in w and "end" in w:
                words.append(w)
    return words


def plan_filler_cuts(segments: list) -> list:
    """um/uh-class filler cuts only (type 'filler_word'). Conservative default."""
    result = detect_fillers(segments)
    cuts = []
    for i, f in enumerate(result.get("fillers", [])):
        if f.get("type") != "filler_word":
            continue  # skip phrases + contextual (cadence) - human-only
        cuts.append({
            "id": f"fil{i}",
            "start": round(max(0.0, f["start"] - _FILLER_PAD), 3),
            "end": round(f["end"] + _FILLER_PAD, 3),
            "type": "filler",
            "source": "auto",
            "enabled": True,
            "text": f.get("word", ""),
        })
    return cuts


def plan_gap_cuts(segments: list, threshold: float = _GAP_THRESHOLD) -> list:
    """Trim dead air longer than `threshold` between consecutive words."""
    words = _all_words(segments)
    cuts = []
    for i in range(1, len(words)):
        gap = words[i]["start"] - words[i - 1]["end"]
        if gap > threshold:
            start = round(words[i - 1]["end"] + _GAP_KEEP, 3)
            end = round(words[i]["start"] - _GAP_KEEP, 3)
            if end - start > 0.1:
                cuts.append({
                    "id": f"gap{i}",
                    "start": start,
                    "end": end,
                    "type": "gap",
                    "source": "auto",
                    "enabled": True,
                    "text": f"{round(gap, 1)}s pause",
                })
    return cuts


def plan_bleed_flags(segments: list) -> list:
    """Flag the first and last segments as possible intro/outro bleed.

    SUGGESTED only (enabled=False). The human confirms - per the spec we never
    assume bleed.
    """
    if not segments:
        return []
    flags = []
    first, last = segments[0], segments[-1]
    flags.append({
        "id": "bleed_intro", "start": round(first.get("start", 0), 3),
        "end": round(first.get("end", 0), 3), "type": "bleed", "source": "auto",
        "enabled": False, "text": (first.get("text") or "")[:80],
    })
    if last is not first:
        flags.append({
            "id": "bleed_outro", "start": round(last.get("start", 0), 3),
            "end": round(last.get("end", 0), 3), "type": "bleed", "source": "auto",
            "enabled": False, "text": (last.get("text") or "")[:80],
        })
    return flags


def plan_falsestart_cuts(segments: list) -> list:
    """Optional LLM pass: suggest false-start / stutter cuts. Review-only.

    Best-effort via Hermes. Returns [] if no LLM backend or on any failure.
    Suggestions are enabled=False - the human opts each one in.
    """
    import json
    import re as _re
    from . import hermes

    lines = []
    for seg in segments:
        for w in seg.get("words", []) or []:
            lines.append(f'{w.get("start", 0):.2f}-{w.get("end", 0):.2f} {w.get("word", "")}')
    if not lines:
        return []

    prompt = (
        "Here is a word-level transcript with start-end timestamps. Identify FALSE STARTS, "
        "stutters, and immediate repeats that a careful editor would cut (e.g. \"we're all, "
        "we're all\" -> keep one; \"i-is\" -> \"is\"; broken openings like \"we have a--\"). "
        "Do NOT flag cadence words (so, you know, like). Return ONLY a JSON array of "
        '{"start": float, "end": float, "reason": str}. Empty array if none.\n\n'
        + "\n".join(lines[:1200])
    )
    out = hermes.run_prompt(prompt, timeout=120)
    if not out:
        return []
    out = _re.sub(r"<think>[\s\S]*?</think>\s*", "", out)
    m = _re.search(r"\[[\s\S]*\]", out)
    if not m:
        return []
    try:
        ranges = json.loads(m.group(0))
    except (ValueError, TypeError):
        return []

    cuts = []
    for i, r in enumerate(ranges):
        try:
            s, e = float(r["start"]), float(r["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if e > s:
            cuts.append({
                "id": f"fs{i}", "start": round(s, 3), "end": round(e, 3),
                "type": "falsestart", "source": "llm", "enabled": False,
                "text": str(r.get("reason", ""))[:100],
            })
    return cuts


def _merge_overlaps(cuts: list) -> list:
    """Merge overlapping ENABLED cuts so render keep-ranges are clean.

    Disabled suggestions are kept separate (the human toggles them); only enabled
    cuts get merged for rendering safety.
    """
    enabled = sorted([c for c in cuts if c.get("enabled")], key=lambda c: c["start"])
    disabled = [c for c in cuts if not c.get("enabled")]
    merged = []
    for c in enabled:
        if merged and c["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], c["end"])
            merged[-1]["text"] = (merged[-1].get("text", "") + "; " + c.get("text", "")).strip("; ")
        else:
            merged.append(dict(c))
    return merged + disabled


def build_edit_sheet(segments: list, duration: float,
                     include_gaps: bool = True, include_falsestarts: bool = False,
                     gap_threshold: float = _GAP_THRESHOLD) -> dict:
    """Assemble the full edit sheet from a transcript.

    Returns {"duration", "cuts": [...]}. Filler + gap cuts are enabled by
    default; false-starts + bleed are suggested (enabled=False).
    """
    cuts = plan_filler_cuts(segments)
    if include_gaps:
        cuts += plan_gap_cuts(segments, threshold=gap_threshold)
    if include_falsestarts:
        cuts += plan_falsestart_cuts(segments)
    cuts += plan_bleed_flags(segments)
    cuts = _merge_overlaps(cuts)
    cuts.sort(key=lambda c: c["start"])
    return {"duration": round(duration, 3), "cuts": cuts}


def keep_ranges(duration: float, cuts: list) -> list:
    """Compute the keep ranges = [0, duration] minus the ENABLED cut ranges."""
    enabled = sorted(
        [(c["start"], c["end"]) for c in cuts if c.get("enabled")],
        key=lambda r: r[0],
    )
    keeps, cursor = [], 0.0
    for s, e in enabled:
        s = max(0.0, min(s, duration))
        e = max(0.0, min(e, duration))
        if s > cursor:
            keeps.append((round(cursor, 3), round(s, 3)))
        cursor = max(cursor, e)
    if cursor < duration:
        keeps.append((round(cursor, 3), round(duration, 3)))
    return [(s, e) for s, e in keeps if e - s > 0.05]
