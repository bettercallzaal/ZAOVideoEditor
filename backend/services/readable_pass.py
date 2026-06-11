"""Stage G: turn a corrected transcript into a clean, brand-voice Markdown read.

This is the second of the two transcript outputs. The first (the timestamped cut
transcript) drives the video edit; this one is for the /recordings/N page - polished,
em-dash free, numbers formatted, brand rules enforced. Runs via Hermes (Claude CLI).
"""

from typing import Optional

from . import hermes
from .glossary import format_numbers


BRAND_SYSTEM = """You are the ZAO transcript editor. Turn a raw speech-to-text transcript into a clean, readable transcript for publication. Follow these rules without exception:

- NO emojis anywhere.
- NO em dashes. Use hyphens.
- NO decorative Unicode (checkmarks, warning triangles, etc.). Use text labels like [MUSIC], DONE.
- NO crypto/web3/onchain jargon in prose. Say "digital creators" or "builders".
- Use "100+" for the ZAO member count, never a specific number.
- Keep exact brand casing: WaveWarZ, COC Concertz, The ZAO, BetterCallZaal, Joseph Goats, SongJam, ZABAL, SANG, ZOE, ZOLs, FISHBOWLZ, Stilo World, ZAOstock, ZAO Music, ZAO DEVZ, ZABAL Gamez.
- Format numbers as digits: "point five SOL" -> "0.5 SOL", "eight thirty PM EST" -> "8:30pm EST".
- Tight, factual, warm. No marketing fluff (no "revolutionary", "game-changing").
- Fix obvious speech-to-text errors and punctuation, but DO NOT change the speaker's meaning, invent content, or remove substance.
- Preserve speaker labels if present. Output clean Markdown prose with paragraphs. Do NOT add a preamble or commentary - output only the transcript."""


def _transcript_to_text(segments: list) -> str:
    lines = []
    for seg in segments:
        speaker = seg.get("speaker")
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"{speaker}: {text}" if speaker else text)
    return "\n".join(lines)


def make_readable(segments: list, title: str = "", deterministic_only: bool = False) -> dict:
    """Produce a clean readable transcript.

    Returns {"markdown", "backend"}. When no LLM backend is available (or
    deterministic_only=True), falls back to a deterministic clean-up
    (number formatting + paragraph joining) so the pipeline never hard-fails.
    """
    raw = _transcript_to_text(segments)

    if deterministic_only:
        return {"markdown": _deterministic_readable(raw, title), "backend": "deterministic"}

    prompt = (
        f"Clean this transcript for the recording titled \"{title}\".\n\n"
        f"TRANSCRIPT:\n{raw}"
    )
    out = hermes.run_prompt(prompt, system=BRAND_SYSTEM)
    if not out:
        return {"markdown": _deterministic_readable(raw, title), "backend": "deterministic"}

    md = out.strip()
    if title and not md.lstrip().startswith("#"):
        md = f"# {title}\n\n{md}"
    return {"markdown": md, "backend": hermes.backend_name()}


def _deterministic_readable(raw: str, title: str) -> str:
    """No-LLM fallback: format numbers, strip em dashes, basic paragraphing."""
    text = format_numbers(raw).replace("—", "-").replace(" -- ", " - ")
    body = "\n\n".join(line.strip() for line in text.splitlines() if line.strip())
    return f"# {title}\n\n{body}" if title else body
