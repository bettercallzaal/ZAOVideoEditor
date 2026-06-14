"""Speaker talk-time analytics from diarized transcript segments.

Once speakers are detected/labeled, this rolls the segments up into per-speaker
talk time, share of the conversation, and segment counts - so you can see who
carried a session and how balanced it was. Pure function over segments.
"""


def talk_time(segments: list) -> dict:
    """Per-speaker talk time from segments that carry a `speaker` label.

    Returns {total_seconds, speakers:[{speaker, seconds, share, segments}]},
    speakers sorted by talk time descending. Segments without a speaker are
    grouped under "Unknown". Returns empty speakers list if nothing is labeled.
    """
    by = {}
    total = 0.0
    for seg in segments or []:
        try:
            dur = max(0.0, float(seg.get("end", 0.0)) - float(seg.get("start", 0.0)))
        except (TypeError, ValueError):
            continue
        spk = (seg.get("speaker") or "").strip() or "Unknown"
        if spk not in by:
            by[spk] = {"speaker": spk, "seconds": 0.0, "segments": 0}
        by[spk]["seconds"] += dur
        by[spk]["segments"] += 1
        total += dur

    # If nothing was actually labeled (everything Unknown), report no breakdown.
    if not by or (len(by) == 1 and "Unknown" in by):
        return {"total_seconds": round(total, 1), "speakers": []}

    rows = sorted(by.values(), key=lambda r: r["seconds"], reverse=True)
    for r in rows:
        r["seconds"] = round(r["seconds"], 1)
        r["share"] = round(r["seconds"] / total, 3) if total else 0.0
    return {"total_seconds": round(total, 1), "speakers": rows}
