"""Stage F (cut render): apply an edit sheet to a video, non-destructively.

The source is never modified. Render produces a NEW trimmed master by keeping
the ranges left after the enabled cuts are removed, stitched in one ffmpeg pass
via the select/aselect filters. Re-runnable: change which cuts are enabled and
re-render from the original.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .cut_planner import keep_ranges


def _video_duration(video_path: str) -> float:
    from .ffmpeg_service import get_video_params
    try:
        return float(get_video_params(video_path).get("duration", 0.0))
    except Exception:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", video_path],
            capture_output=True, text=True,
        )
        try:
            return float(r.stdout.strip())
        except ValueError:
            return 0.0


def _build_concat_filter(keeps: list) -> str:
    """filter_complex that trims each keep range and concatenates with A/V sync.

    Uses trim/atrim (colon-separated args, no comma escaping) + concat - more
    reliable than the select filter, which leaves bogus duration metadata.
    """
    parts, labels = [], ""
    for i, (s, e) in enumerate(keeps):
        parts.append(f"[0:v]trim={s}:{e},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim={s}:{e},asetpts=PTS-STARTPTS[a{i}]")
        labels += f"[v{i}][a{i}]"
    parts.append(f"{labels}concat=n={len(keeps)}:v=1:a=1[outv][outa]")
    return ";".join(parts)


def render_cuts(video_path: str, edit_sheet: dict, out_path: str) -> dict:
    """Apply the edit sheet's enabled cuts to video_path -> out_path.

    Returns {"kept_ranges", "removed_seconds", "duration_out"}. If nothing is
    enabled, the source is copied verbatim (still a new file - non-destructive).
    """
    duration = edit_sheet.get("duration") or _video_duration(video_path)
    cuts = edit_sheet.get("cuts", [])
    keeps = keep_ranges(duration, cuts)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    enabled = [c for c in cuts if c.get("enabled")]
    if not enabled or not keeps:
        # nothing to cut - copy through (re-encode-free) so the master still exists
        from .ffmpeg_service import copy_without_reencode
        copy_without_reencode(video_path, str(out))
        return {"kept_ranges": [(0.0, duration)], "removed_seconds": 0.0, "duration_out": duration}

    filt = _build_concat_filter(keeps)
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-filter_complex", filt,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Cut render failed: {result.stderr[-400:]}")

    kept = sum(e - s for s, e in keeps)
    return {
        "kept_ranges": keeps,
        "removed_seconds": round(duration - kept, 2),
        "duration_out": round(kept, 2),
    }


def render_transcript_after_cuts(segments: list, cuts: list) -> list:
    """Return the transcript segments with cut words/segments removed.

    Keeps the readable + cut transcripts in sync with what the rendered video
    actually contains. A segment is dropped if it falls entirely inside an
    enabled cut; partially-cut segments keep the words outside the cut.
    """
    enabled = [(c["start"], c["end"]) for c in cuts if c.get("enabled")]

    def _in_cut(t: float) -> bool:
        return any(s <= t < e for s, e in enabled)

    out = []
    for seg in segments:
        words = seg.get("words") or []
        if words:
            kept_words = [w for w in words if not _in_cut((w.get("start", 0) + w.get("end", 0)) / 2)]
            if not kept_words:
                continue
            new_seg = dict(seg)
            new_seg["words"] = kept_words
            new_seg["text"] = " ".join(w.get("word", "").strip() for w in kept_words).strip()
            new_seg["start"] = kept_words[0].get("start", seg.get("start"))
            new_seg["end"] = kept_words[-1].get("end", seg.get("end"))
            out.append(new_seg)
        else:
            mid = (seg.get("start", 0) + seg.get("end", 0)) / 2
            if not _in_cut(mid):
                out.append(dict(seg))
    return out
