#!/usr/bin/env python3
"""Audio space -> YouTube-ready 1080p mp4, in one command.

An audio space has no video track, so it cannot be uploaded anywhere that wants
video. This renders a branded audiogram, transcribes it, and writes the YouTube
title, description, chapters, and tags beside the mp4.

Source can be a local recording or a Zuke space id. Zuke's recap endpoint
already returns the audio URL plus host and participant metadata, so no changes
to Zuke are needed - it hands off, this picks up.

    # From a Zuke space
    python scripts/space_to_youtube.py --space-id abc123 \
        --zuke-base https://zuke.thezao.com

    # From a local recording
    python scripts/space_to_youtube.py ~/Downloads/space.ogg \
        --title "ZABAL GAMEZ Fireside" --host zaal

    # Three-minute smoke render before committing to the full length
    python scripts/space_to_youtube.py ~/Downloads/space.ogg --minutes 3

Captions ship as a .srt sidecar, which YouTube ingests natively. Use --burn only
for platforms with no caption track (Shorts, TikTok, Reels); it needs an ffmpeg
built with libass.
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services import audiogram_service as ag  # noqa: E402
from backend.services import recordings_pipeline as rp  # noqa: E402
from backend.services.caption_gen import (  # noqa: E402
    generate_ass, generate_captions_from_segments, generate_srt,
)
from backend.services.metadata_gen import (  # noqa: E402
    generate_chapters, generate_description, generate_tags,
)


def log(msg: str):
    print(f"[space->yt] {msg}", flush=True)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s or "space"


def fetch_zuke_recap(zuke_base: str, space_id: str) -> dict:
    """Pull the recap payload Zuke already exposes. This is the whole bridge."""
    url = f"{zuke_base.rstrip('/')}/api/recordings/recap?spaceId={space_id}"
    log(f"GET {url}")
    with urllib.request.urlopen(url, timeout=30) as resp:
        payload = json.load(resp)

    if not payload.get("ok"):
        raise SystemExit(f"Zuke recap failed: {payload}")

    audio = [a for a in payload.get("audio", []) if a.get("url")]
    if not audio:
        raise SystemExit(f"Space {space_id} has no recording yet.")

    host = (payload.get("host") or {}).get("username") or ""
    return {
        "audio_url": audio[0]["url"],
        "title": (payload.get("space") or {}).get("title") or space_id,
        "host": host,
        "participants": payload.get("participants", []),
    }


def download(url: str, dest: Path) -> Path:
    """Fetch a remote recording. Extension comes from the URL, not the response."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    log(f"downloading {url}")
    # A snippet URL carries a media fragment (#t=start,end); strip it, the whole
    # parent file is what gets downloaded.
    clean = url.split("#")[0]
    with urllib.request.urlopen(clean, timeout=120) as resp, open(dest, "wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)
    log(f"saved {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
    return dest


def slice_audio(source: Path, seconds: float, dest: Path) -> Path:
    """Cut the head off a recording, for smoke runs.

    The slice has to happen before transcription, not just before the render.
    Otherwise the transcript, captions, and chapters all describe the full-length
    recording while the mp4 is three minutes long - and you pay for transcribing
    an hour of audio you are about to throw away.
    """
    import subprocess

    dest.parent.mkdir(parents=True, exist_ok=True)
    log(f"smoke slice: first {seconds / 60:.1f} min -> {dest.name}")
    subprocess.run(
        ["ffmpeg", "-y", "-t", str(seconds), "-i", str(source), "-c", "copy", str(dest)],
        check=True, capture_output=True,
    )
    return dest


def build_youtube_txt(segments: list, title: str, host: str, participants: list) -> str:
    description = generate_description(segments, title)
    chapters = generate_chapters(segments)
    tags = generate_tags(segments, title)

    credit = f"Hosted by @{host.lstrip('@')}" if host else ""
    guests = ", ".join(
        f"@{p['username']}" for p in participants
        if p.get("username") and p["username"] != host
    )

    parts = [
        f"TITLE\n{title}", "",
        "DESCRIPTION",
        description,
    ]
    if credit:
        parts += ["", credit]
    if guests:
        parts += [f"With: {guests}"]
    parts += [
        "", "CHAPTERS", chapters,
        "", "TAGS", tags, "",
    ]
    return "\n".join(parts)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source", nargs="?", help="Local audio file, or omit and pass --space-id")
    p.add_argument("--space-id", help="Zuke space id; resolves audio + metadata via the recap API")
    p.add_argument("--zuke-base", default=os.environ.get("ZUKE_BASE_URL", "https://zuke.thezao.com"))
    p.add_argument("--title", default="", help="Overrides the title from Zuke")
    p.add_argument("--host", default="", help="Farcaster handle of the host, no @")
    p.add_argument("--out", default="out", help="Output directory")
    p.add_argument("--quality", default="fast", choices=["fast", "balanced", "best"])
    p.add_argument("--minutes", type=float, help="Smoke render: cap output length")
    p.add_argument("--hwaccel", action="store_true", help="h264_videotoolbox (Apple silicon)")
    p.add_argument("--burn", action="store_true",
                   help="Burn captions into the picture. Needs libass. YouTube does not need this.")
    p.add_argument("--style", default="brand_dark",
                   help="Caption style: classic, box, bold_pop, highlight, brand_light, brand_dark")
    p.add_argument("--speakers", action="store_true",
                   help="Label who is talking. Needs pyannote.audio, torch, and HF_TOKEN.")
    p.add_argument("--no-verify", action="store_true",
                   help="Skip measuring the finished mp4. Not recommended.")
    args = p.parse_args()

    if not args.source and not args.space_id:
        p.error("give a local file or --space-id")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    title, host, participants = args.title, args.host, []

    if args.space_id:
        recap = fetch_zuke_recap(args.zuke_base, args.space_id)
        title = title or recap["title"]
        host = host or recap["host"]
        participants = recap["participants"]
        ext = Path(recap["audio_url"].split("#")[0]).suffix or ".ogg"
        source = download(recap["audio_url"], out_dir / f"{slugify(title)}{ext}")
    else:
        source = Path(args.source).expanduser()
        if not source.exists():
            raise SystemExit(f"No such file: {source}")
        title = title or source.stem.replace("-", " ").title()

    info = ag.probe_streams(str(source))
    if not info["has_audio"]:
        raise SystemExit(f"{source} has no audio stream.")
    if info["has_video"]:
        raise SystemExit(
            f"{source} already has a video stream - use the normal editor pipeline."
        )

    log(f"title: {title}")
    log(f"duration: {info['duration'] / 60:.1f} min")

    if args.minutes and args.minutes * 60 < info["duration"]:
        source = slice_audio(source, args.minutes * 60,
                             out_dir / f"smoke{source.suffix}")
        info = ag.probe_streams(str(source))

    if args.burn and not ag._has_ass_filter():
        raise SystemExit(
            "--burn needs an ffmpeg with libass (no 'ass' filter found).\n"
            "YouTube reads the .srt sidecar, so drop --burn unless this is for Shorts."
        )

    slug = slugify(title)

    log("transcribing (this is the slow part)...")
    result = rp.process_recording(
        str(source), title=title, quality=args.quality, engine="auto",
        out_dir=str(out_dir / "transcripts"), readable_llm=False,
        detect_speakers=args.speakers,
        on_progress=lambda pct, msg: log(f"  {pct}% {msg}"),
    )
    segments = result["segments"]
    log(f"{len(segments)} segments")

    # Whisper loops on long audio and emits one sentence for tens of minutes. The
    # segment count still looks healthy and the render still verifies, because the
    # pixels are fine and only the words are wrong. Stop before the encode.
    if result.get("repetition_collapse"):
        raise SystemExit(
            f"TRANSCRIPT COLLAPSED: {result['repetition_ratio']:.0%} of segments repeat "
            f"the previous one. This is a Whisper repetition loop, not a conversation.\n"
            f"Refusing to render. Try --quality best, or transcribe with Groq "
            f"(set GROQ_API_KEY)."
        )

    # Diarization is deliberately non-fatal, so an unmet dependency would
    # otherwise show up only as captions that never say who is talking.
    if args.speakers and result.get("speaker_error"):
        log(f"WARNING: --speakers requested but diarization failed: {result['speaker_error']}")
        log("WARNING: captions will not be speaker-labelled. Install pyannote.audio + torch")
        log("WARNING: and set HF_TOKEN, or drop --speakers.")

    if result.get("glossary_changes"):
        for ch in result["glossary_changes"]:
            log(f"  glossary: {ch['from']!r} -> {ch['to']!r} x{ch['count']}")

    captions = generate_captions_from_segments(segments, style=args.style)
    srt_path = out_dir / f"{slug}.srt"
    srt_path.write_text(generate_srt(captions, style=args.style), encoding="utf-8")
    log(f"captions -> {srt_path}  (upload this alongside the video)")

    ass_path = None
    if args.burn:
        ass_path = out_dir / f"{slug}.ass"
        ass_path.write_text(
            generate_ass(captions, style=args.style,
                         video_width=ag.WIDTH, video_height=ag.HEIGHT),
            encoding="utf-8",
        )

    subtitle = f"hosted by @{host.lstrip('@')}" if host else ""
    footer = f"{len(segments)} segments  .  {info['duration'] / 60:.0f} min"

    mp4_path = out_dir / f"{slug}.mp4"
    log("rendering audiogram...")
    ag.render_audiogram(
        str(source), str(mp4_path), title=title, subtitle=subtitle, footer=footer,
        ass_path=str(ass_path) if ass_path else None,
        hwaccel=args.hwaccel,
        on_progress=lambda pct, msg: log(f"  {pct}% {msg}"),
    )

    meta_path = out_dir / f"{slug}.youtube.txt"
    meta_path.write_text(build_youtube_txt(segments, title, host, participants), encoding="utf-8")

    size_mb = mp4_path.stat().st_size / 1e6
    log("")
    log(f"video     {mp4_path}  ({size_mb:.1f} MB)")
    log(f"captions  {srt_path}")
    log(f"metadata  {meta_path}")

    # Measure the artifact, not the exit code. Every render bug this pipeline has
    # shipped left ffmpeg exiting 0 with a valid, wrong file.
    verified = True
    if not args.no_verify:
        from verify_render import verify

        log("")
        log("verifying the render...")
        report = verify(str(mp4_path), aspect="16:9",
                        expect_captions=bool(args.burn), srt=str(srt_path),
                        duration=info["duration"])
        for c in report["checks"]:
            log(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}")
        verified = report["ok"]
        if not verified:
            log("")
            log(f"RENDER FAILED VERIFICATION: {', '.join(report['failed'])}")
            log("Do not upload this file.")

    if args.minutes:
        log(f"NOTE: smoke render, capped at {args.minutes} min. Drop --minutes for the full space.")
    log("")
    log("Upload is manual on purpose. Nothing was pushed to YouTube.")

    if not verified:
        sys.exit(1)


if __name__ == "__main__":
    main()
