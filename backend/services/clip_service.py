"""Clip cutting with aspect reframing + burned-in captions, in one ffmpeg pass.

Cut a [start, end] window from the source, reframe it to the target aspect, and
(optionally) burn the captions for just that window - timestamps rebased so the
ASS lines line up with the trimmed clip.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .reframe_service import build_vf, aspect_target, detect_focus_x
from .caption_gen import generate_captions_from_segments, generate_ass


def segments_in_window(segments: list, start: float, end: float) -> list:
    """Return segments overlapping [start, end], timestamps rebased to clip-relative.

    Word-level timings, when present, are rebased too so highlight-style captions
    stay in sync.
    """
    dur = end - start
    out = []
    for seg in segments:
        s_start = seg.get("start", 0)
        s_end = seg.get("end", 0)
        if s_end <= start or s_start >= end:
            continue
        new_seg = dict(seg)
        new_seg["start"] = max(0.0, s_start - start)
        new_seg["end"] = min(dur, s_end - start)
        words = seg.get("words")
        if words:
            new_words = []
            for w in words:
                w_start = w.get("start", s_start)
                w_end = w.get("end", s_end)
                if w_end <= start or w_start >= end:
                    continue
                nw = dict(w)
                nw["start"] = max(0.0, w_start - start)
                nw["end"] = min(dur, w_end - start)
                new_words.append(nw)
            new_seg["words"] = new_words
        out.append(new_seg)
    return out


def _write_caption_files(segments: list, start: float, end: float, style: str,
                         aspect: str, work_dir: Path) -> Optional[Path]:
    """Write clip.ass + captions.json into work_dir for the clip window.

    Both files are needed: the libass path uses clip.ass; the Pillow fallback
    (burn_captions) reads captions.json from the same directory. Returns the ASS
    path, or None when the window has no captions.
    """
    window = segments_in_window(segments, start, end)
    if not window:
        return None
    captions = generate_captions_from_segments(window, style=style)
    if not captions:
        return None
    out_w, out_h = aspect_target(aspect)
    ass_text = generate_ass(captions, style=style, video_width=out_w, video_height=out_h)
    ass_path = work_dir / "clip.ass"
    ass_path.write_text(ass_text, encoding="utf-8")
    (work_dir / "captions.json").write_text(json.dumps(captions), encoding="utf-8")
    return ass_path


def export_clip(video_path: str, start: float, end: float, out_path: Path,
                aspect: str = "9:16", segments: Optional[list] = None,
                style: str = "bold_pop", burn_captions: bool = True,
                speaker_aware: bool = False) -> dict:
    """Cut + reframe a clip, then burn the window's captions.

    Reframing (crop+scale) is one ffmpeg pass. Captions are applied by the shared
    burn_captions() helper, which uses the libass filter when available and falls
    back to a Pillow overlay otherwise - so captions work even on ffmpeg builds
    without libass.

    Returns {"filename", "aspect", "duration", "captioned"}; raises RuntimeError
    on encode failure.
    """
    duration = end - start
    if duration <= 0:
        raise ValueError("Clip end must be after start")

    focus_x = None
    if speaker_aware and aspect != "16:9":
        focus_x = detect_focus_x(video_path, sample_time=start + min(2.0, duration / 2))

    vf = build_vf(aspect, focus_x=focus_x)

    work_dir = None
    ass_path = None
    if burn_captions and segments:
        work_dir = Path(tempfile.mkdtemp(prefix="zve_clip_"))
        ass_path = _write_caption_files(segments, start, end, style, aspect, work_dir)

    # Pass 1: cut + reframe. Write straight to out_path when there are no captions,
    # otherwise to a temp file that pass 2 captions into out_path.
    reframe_target = out_path if not ass_path else (
        out_path.parent / f".{out_path.stem}.reframe.mp4"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(video_path),
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "21",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        str(reframe_target),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if work_dir:
            shutil.rmtree(work_dir, ignore_errors=True)
        if reframe_target != out_path and reframe_target.exists():
            reframe_target.unlink()
        raise RuntimeError(f"Clip reframe failed: {result.stderr[-400:]}")

    captioned = False
    if ass_path:
        # Pass 2: burn captions (libass or Pillow fallback) onto the reframed clip.
        # Best-effort: if the burn fails, keep the reframed clip uncaptioned rather
        # than failing the whole clip.
        from .ffmpeg_service import burn_captions as _burn
        try:
            _burn(str(reframe_target), str(ass_path), str(out_path), style_name=style)
            captioned = out_path.exists()
        except Exception as e:
            print(f"Clip caption burn failed, keeping uncaptioned clip: {e}")
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
            if not captioned and reframe_target != out_path and reframe_target.exists():
                shutil.move(str(reframe_target), str(out_path))
            elif reframe_target != out_path and reframe_target.exists():
                reframe_target.unlink()

    return {
        "filename": out_path.name,
        "aspect": aspect,
        "duration": round(duration, 1),
        "captioned": captioned,
    }
