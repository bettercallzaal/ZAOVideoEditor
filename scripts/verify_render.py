#!/usr/bin/env python3
"""Verify a rendered audiogram by measuring the pixels. The stop signal.

Every render bug this repo has shipped passed the signals it had. ffmpeg exited
0. export_clip returned captioned=True. The unit tests were green. And the output
was a Short with no captions, or a 58-minute video whose waveform was an
invisible flat line, because `showwaves` drew translucent strokes that `overlay`
blended into the background.

Exit codes, return values and unit tests are all signals a render can fake. The
frame buffer is not. This module opens the finished file, samples frames, and
counts pixels in the regions where the waveform and the captions are supposed to
be. Anything that reads the artifact instead of the process can serve as the exit
condition of a loop; nothing upstream of the artifact can.

    python scripts/verify_render.py out/clip.mp4 --aspect 9:16 \
        --expect-waveform --expect-captions --srt out/clip.srt --duration 15

Exits 0 when every check passes, 1 otherwise, and prints a JSON report either
way. Import `verify()` to use it as a test assertion or a loop's rubric.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.audiogram_service import (  # noqa: E402
    BRAND_FG, aspect_size, _wave_geometry,
)

# Measured on a real 58-minute space. Peak coverage of the waveform band across
# sampled frames: a healthy render scores ~48%, both known-broken renders scored
# 0.077%. 0.5% sits ~6x above the broken renders and ~95x below a healthy one, so
# it separates without flaking on a quiet passage (coverage is the peak across
# samples, not the mean). A threshold at 0.1% would clear the bugs by only 1.3x.
MIN_WAVEFORM_COVERAGE = 0.005

# Burned captions are near-white with an outline. Even one short word covers well
# over this. The card's own text is brand beige, which is excluded by requiring a
# high blue channel.
MIN_CAPTION_COVERAGE = 0.0005

# Motion is measured inside the waveform band, not across the whole frame. Most
# of an audiogram is a static card, so whole-frame delta is dominated by dead
# pixels: real speech scored 2.1%-8.1% but a steady tone scored 0.221%, barely
# above a frozen still's 0.031% of x264 noise.
#
# Restricted to the band where the waveform lives, a frozen still scores exactly
# 0.000% while live renders score 2.2%-30%. Half a percent clears the quietest
# live render by 4x and any frozen frame by an unbounded margin. (2% looked fine
# against a loud clip and left only a 1.09x margin on a quiet one.)
MIN_FRAME_DELTA = 0.005


def _probe(path: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {out.stderr.strip()}")
    return json.loads(out.stdout)


def _frame(path: str, t: float, out_png: str) -> str:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(path),
         "-frames:v", "1", out_png],
        check=True, capture_output=True,
    )
    return out_png


def _near(px, target, tol=60) -> bool:
    return sum(abs(a - b) for a, b in zip(px, target)) <= tol * 3


def _count_region(img, x0, y0, x1, y1, pred) -> tuple:
    px = img.load()
    hits = 0
    total = 0
    for y in range(max(0, y0), min(img.size[1], y1)):
        for x in range(max(0, x0), min(img.size[0], x1)):
            total += 1
            if pred(px[x, y]):
                hits += 1
    return hits, total


def _is_brand_fg(p) -> bool:
    return _near(p, tuple(int(BRAND_FG.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)))


def _is_caption_white(p) -> bool:
    """Strict white. Brand beige is (224,221,170), and its antialiased edges wash
    out to things like (210,219,207) after yuv420p - which a loose `> 200` test
    counts as white, so an uncaptioned render scored 0.137% and passed."""
    return min(p) > 220 and (max(p) - min(p)) < 25


def _frame_delta(a, b, box=None) -> float:
    """Fraction of sampled pixels that changed between two frames.

    `box` restricts the comparison to the region that is supposed to move.
    """
    pa, pb = a.load(), b.load()
    w, h = a.size
    x0, y0, x1, y1 = box or (0, 0, w, h)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)

    step = max(1, (x1 - x0) // 120)
    diff = seen = 0
    for y in range(y0, y1, step):
        for x in range(x0, x1, step):
            seen += 1
            if sum(abs(i - j) for i, j in zip(pa[x, y], pb[x, y])) > 30:
                diff += 1
    return diff / max(1, seen)


def _check_srt(srt_path: Path, duration: float) -> list:
    """Cheap but real: a caption file YouTube rejects is a failed render."""
    checks = []
    text = srt_path.read_text(encoding="utf-8", errors="replace")
    stamps = re.findall(
        r"(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})", text)

    def secs(h, m, s, ms):
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    if not stamps:
        checks.append(("srt_has_cues", False, "no cues parsed"))
        return checks
    checks.append(("srt_has_cues", True, f"{len(stamps)} cues"))

    degenerate = [c for c in stamps if secs(*c[4:]) <= secs(*c[:4])]
    checks.append(("srt_no_zero_length_cues", not degenerate,
                   f"{len(degenerate)} cues with end <= start"))

    last_end = max(secs(*c[4:]) for c in stamps)
    over = last_end > duration + 1.0
    checks.append(("srt_within_video_duration", not over,
                   f"last cue ends {last_end:.1f}s, video is {duration:.1f}s"))
    return checks


def verify(path: str, aspect: str = "16:9", expect_waveform: bool = True,
           expect_captions: bool = False, srt: str = None,
           duration: float = None, samples: int = 6) -> dict:
    """Measure the rendered artifact. Returns a report; never raises on a failed check."""
    from PIL import Image

    checks = []
    info = _probe(path)
    streams = info.get("streams", [])
    kinds = [s.get("codec_type") for s in streams]
    actual_duration = float(info.get("format", {}).get("duration", 0.0))

    checks.append(("has_video_stream", "video" in kinds, f"streams={kinds}"))
    checks.append(("has_audio_stream", "audio" in kinds, f"streams={kinds}"))

    if "video" not in kinds:
        return _report(path, checks)

    vs = next(s for s in streams if s["codec_type"] == "video")
    want_w, want_h = aspect_size(aspect)
    got = (vs.get("width"), vs.get("height"))
    checks.append(("dimensions_match_aspect", got == (want_w, want_h),
                   f"{got} vs expected {(want_w, want_h)}"))

    if duration is not None:
        ok = abs(actual_duration - duration) <= max(0.5, duration * 0.02)
        checks.append(("duration_matches", ok,
                       f"{actual_duration:.2f}s vs expected {duration:.2f}s"))

    wave_w, wave_h, wave_y = _wave_geometry(want_w, want_h)
    wave_x = (want_w - wave_w) // 2

    tmp = Path(tempfile.mkdtemp(prefix="verify_"))
    times = [actual_duration * (i + 1) / (samples + 1) for i in range(samples)]
    frames = []
    try:
        for i, t in enumerate(times):
            frames.append(Image.open(_frame(path, t, str(tmp / f"f{i}.png"))).convert("RGB"))

        if expect_waveform:
            best = 0.0
            for img in frames:
                hits, total = _count_region(img, wave_x, wave_y,
                                            wave_x + wave_w, wave_y + wave_h,
                                            _is_brand_fg)
                best = max(best, hits / max(1, total))
            checks.append(("waveform_visible", best >= MIN_WAVEFORM_COVERAGE,
                           f"peak coverage {best * 100:.3f}% of the waveform band "
                           f"(need {MIN_WAVEFORM_COVERAGE * 100:.3f}%)"))

        if expect_captions:
            # Start below the waveform. On 16:9 a naive "bottom 45%" band swallows
            # the waveform, whose washed-out beige edges then read as caption text.
            band_top = max(int(want_h * 0.55), wave_y + wave_h + 10)
            best = 0.0
            for img in frames:
                hits, total = _count_region(img, 0, band_top, want_w, want_h,
                                            _is_caption_white)
                best = max(best, hits / max(1, total))
            checks.append(("captions_burned_in", best >= MIN_CAPTION_COVERAGE,
                           f"peak coverage {best * 100:.4f}% of the caption band "
                           f"(need {MIN_CAPTION_COVERAGE * 100:.4f}%)"))

        # Compare each sampled frame against one a fixed short hop later, rather
        # than against the next distant sample. Widely spaced samples can land on
        # the same phase of a periodic signal - a 4 Hz tremolo measured 12% at 4
        # samples and 1.5% at 3 - which makes the result depend on the sample
        # count. A neighbouring frame is always mid-motion.
        band = (wave_x, wave_y, wave_x + wave_w, wave_y + wave_h)
        deltas = []
        for i, t in enumerate(times):
            hop = min(t + 0.1, max(0.0, actual_duration - 0.05))
            if hop <= t:
                continue
            nxt = Image.open(_frame(path, hop, str(tmp / f"n{i}.png"))).convert("RGB")
            try:
                deltas.append(_frame_delta(frames[i], nxt, box=band))
            finally:
                nxt.close()

        if deltas:
            delta = max(deltas)
            checks.append(("video_is_not_frozen", delta >= MIN_FRAME_DELTA,
                           f"max waveform-band delta {delta * 100:.3f}% "
                           f"(need {MIN_FRAME_DELTA * 100:.3f}%)"))
    finally:
        for f in frames:
            f.close()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    if srt:
        checks.extend(_check_srt(Path(srt), actual_duration))

    return _report(path, checks)


def _report(path: str, checks: list) -> dict:
    failed = [c[0] for c in checks if not c[1]]
    return {
        "file": str(path),
        "ok": not failed,
        "failed": failed,
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("video")
    p.add_argument("--aspect", default="16:9", choices=["16:9", "9:16", "1:1"])
    p.add_argument("--expect-waveform", action="store_true", default=True)
    p.add_argument("--no-waveform", dest="expect_waveform", action="store_false")
    p.add_argument("--expect-captions", action="store_true")
    p.add_argument("--srt")
    p.add_argument("--duration", type=float)
    p.add_argument("--samples", type=int, default=6)
    args = p.parse_args()

    report = verify(args.video, aspect=args.aspect,
                    expect_waveform=args.expect_waveform,
                    expect_captions=args.expect_captions,
                    srt=args.srt, duration=args.duration, samples=args.samples)

    print(json.dumps(report, indent=2))
    for c in report["checks"]:
        print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}",
              file=sys.stderr)

    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
