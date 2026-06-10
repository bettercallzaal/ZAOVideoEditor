"""Stage F (captions) + clips for a finished recording.

Captions are editable data + a non-destructive burn: the trimmed master stays
caption-free, captions are generated from the transcript, and burning produces a
SEPARATE captioned file you can re-burn after editing. Clips reuse the shared clip
pipeline (PR #5) when present; otherwise only the clip PLAN is returned.
"""

import json
from pathlib import Path
from typing import Optional

from .caption_gen import generate_captions_from_segments, save_captions
from .highlights import detect_highlights


def build_caption_data(segments: list, style: str = "bold_pop") -> list:
    """Editable caption segments from the (cut-synced) transcript."""
    return generate_captions_from_segments(segments, style=style)


def write_caption_data(segments: list, out_path: Path, style: str = "bold_pop") -> list:
    captions = build_caption_data(segments, style=style)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_captions(captions, str(out_path))
    return captions


def burn_master_captions(master_path: str, captions: list, out_path: str,
                         style: str = "bold_pop") -> dict:
    """Burn captions onto the trimmed master into a NEW file (non-destructive).

    The master is never modified. Best-effort: on burn failure the master is
    copied through uncaptioned so export never hard-fails.
    """
    from .caption_gen import generate_ass
    from .ffmpeg_service import burn_captions, copy_without_reencode

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    work = out.parent
    ass_path = work / "_master.ass"
    (work / "captions.json").write_text(json.dumps(captions), encoding="utf-8")
    ass_path.write_text(generate_ass(captions, style=style), encoding="utf-8")

    try:
        burn_captions(master_path, str(ass_path), str(out), style_name=style)
        captioned = out.exists()
    except Exception as e:
        print(f"Master caption burn failed, copying uncaptioned: {e}")
        copy_without_reencode(master_path, str(out))
        captioned = False
    finally:
        for p in (ass_path, work / "captions.json"):
            if p.exists():
                p.unlink()

    return {"output": out.name, "captioned": captioned}


def plan_clips(segments: list, count: int = 6,
               min_duration: float = 30.0, max_duration: float = 90.0) -> list:
    """Highlight ranges for clips. Works without the PR #5 render code."""
    return detect_highlights(
        segments, min_duration=min_duration, max_duration=max_duration, count=count,
    )


def render_clips(master_path: str, segments: list, clips_dir: Path,
                 highlights: Optional[list] = None, aspects: Optional[list] = None,
                 project_name: str = "") -> dict:
    """Render captioned clips for each highlight, in each aspect.

    Reuses the shared clip pipeline (services.clip_service, services.content_gen
    .generate_clip_copy) from the clip-distribution work. If that code is not
    present yet, returns the clip PLAN only so this never hard-fails.
    """
    highlights = highlights or plan_clips(segments)
    aspects = aspects or ["9:16"]

    try:
        from .clip_service import export_clip
        from .content_gen import generate_clip_copy
    except ImportError:
        return {"rendered": False, "reason": "clip pipeline not available (merge PR #5)",
                "plan": highlights}

    clips_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for i, h in enumerate(highlights):
        base = _safe(h.get("title", f"clip_{i + 1}"), i + 1)
        renders = []
        for aspect in aspects:
            suffix = aspect.replace(":", "x")
            try:
                info = export_clip(
                    master_path, h["start"], h["end"], clips_dir / f"{base}_{suffix}.mp4",
                    aspect=aspect, segments=segments, burn_captions=True,
                )
                renders.append(info)
            except Exception as e:
                renders.append({"aspect": aspect, "error": str(e)})
        window = [s for s in segments if s.get("end", 0) > h["start"] and s.get("start", 0) < h["end"]]
        copy = generate_clip_copy(window, project_name=project_name, fallback_title=h.get("title", ""))
        (clips_dir / f"{base}.copy.json").write_text(json.dumps(copy, indent=2), encoding="utf-8")
        out.append({"base": base, "renders": renders, "copy": copy})

    return {"rendered": True, "clips": out}


def _safe(title: str, idx: int) -> str:
    safe = "".join(c for c in (title or f"clip_{idx}") if c.isalnum() or c in " _-").strip()
    return safe[:50] or f"clip_{idx}"
