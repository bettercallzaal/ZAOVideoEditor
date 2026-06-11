#!/usr/bin/env python3
"""Run the Phase 1 recordings transcript pipeline on a file or URL.

Usage:
  python scripts/process_recording.py <file-or-url> [--title "..."] [--quality fast|standard|high]
                                       [--out DIR] [--no-llm]

Examples:
  python scripts/process_recording.py ~/Downloads/workshop.mp4 --title "WaveWarZ Talk"
  python scripts/process_recording.py "https://youtube.com/watch?v=..." --title "ZABAL Gamez S1" --out ./out

A URL is downloaded first via yt-dlp (must be installed). Output: a timestamped cut
transcript, a clean readable Markdown transcript, and a review-flags list.
"""

import argparse
import sys
import tempfile
from pathlib import Path

# allow running from the repo root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.recordings_pipeline import process_recording  # noqa: E402


def _maybe_download(source: str) -> tuple[str, bool]:
    """If source is a URL, download it with yt-dlp into a temp file."""
    if not (source.startswith("http://") or source.startswith("https://")):
        return source, False
    import subprocess
    out_dir = Path(tempfile.mkdtemp(prefix="rec_dl_"))
    template = str(out_dir / "input.%(ext)s")
    print(f"Downloading {source} ...")
    r = subprocess.run(
        ["yt-dlp", "-f", "bestaudio[ext=m4a]/bestaudio/best", "-o", template,
         "--no-playlist", "--no-warnings", source],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.exit(f"yt-dlp download failed:\n{r.stderr[-500:]}")
    files = list(out_dir.glob("input.*"))
    if not files:
        sys.exit("Download produced no file")
    return str(files[0]), True


def main():
    ap = argparse.ArgumentParser(description="ZAO recordings transcript pipeline (Phase 1)")
    ap.add_argument("source", help="path to a video/audio file, or a URL")
    ap.add_argument("--title", default="", help="recording title")
    ap.add_argument("--quality", default="standard", choices=["fast", "standard", "high"])
    ap.add_argument("--out", default=None, help="directory to write transcript files")
    ap.add_argument("--no-llm", action="store_true", help="skip the LLM readable pass (deterministic clean-up only)")
    args = ap.parse_args()

    media, _ = _maybe_download(args.source)

    def progress(pct, msg):
        print(f"[{pct:3d}%] {msg}", file=sys.stderr)

    result = process_recording(
        media, title=args.title, quality=args.quality,
        out_dir=args.out, readable_llm=not args.no_llm, on_progress=progress,
    )

    print(f"\nSegments: {result['segment_count']}  |  readable backend: {result['readable_backend']}")
    if result["review_flags"]:
        print(f"\nReview flags ({len(result['review_flags'])}) - confirm these by hand:")
        for f in result["review_flags"]:
            sugg = f" -> {f['suggestion']}" if f.get("suggestion") else ""
            print(f"  - {f['term']}{sugg}: {f['note']}")
    if args.out:
        print(f"\nWrote to {result['output_dir']}:")
        for k, v in result["files"].items():
            print(f"  {k}: {v}")
    else:
        print("\n--- READABLE TRANSCRIPT ---\n")
        print(result["readable_markdown"])


if __name__ == "__main__":
    main()
