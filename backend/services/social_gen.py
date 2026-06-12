"""Generate social posts for a recording (episode-level + per-clip).

Brand-safe by construction: the system prompt bakes in the ZAO rules (no emojis,
no em dashes, no crypto/web3 jargon in public copy, "100+" for member count).
Runs via Hermes (claude CLI, zero cost) with a deterministic fallback so it never
hard-fails.
"""

from typing import Optional

from . import hermes


SOCIAL_SYSTEM = """You write short social posts for The ZAO. Rules, no exceptions:
- NO emojis. NO em dashes (use hyphens). NO decorative Unicode.
- NO crypto / web3 / onchain jargon in public copy. Say "digital creators" or "builders".
- Use "100+" for the ZAO member count, never a specific number.
- Keep exact brand casing: WaveWarZ, COC Concertz, The ZAO, BetterCallZaal, SongJam, ZABAL, ZAOstock, Stilo World, ZABAL Gamez.
- Tight, factual, warm. No marketing fluff (no "revolutionary", "game-changing").
Return ONLY the requested JSON, no markdown fences, no commentary."""


def _run_json(prompt: str):
    import json
    import re
    out = hermes.run_prompt(prompt, system=SOCIAL_SYSTEM, timeout=120)
    if not out:
        return None
    out = re.sub(r"<think>[\s\S]*?</think>\s*", "", out)
    m = re.search(r"[\[{][\s\S]*[\]}]", out)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except (ValueError, TypeError):
        return None


def episode_posts(readable_markdown: str, title: str = "") -> dict:
    """Draft a Farcaster post and an X post for the whole recording."""
    body = _strip_md(readable_markdown)[:6000]
    fallback = {
        "farcaster": f"New from The ZAO: {title}. {_first_sentence(body)}".strip()[:320],
        "x": f"{title}: {_first_sentence(body)}".strip()[:280],
        "backend": "deterministic",
    }
    if not body:
        return fallback

    data = _run_json(
        f'Recording titled "{title}". Write social posts about it. Return JSON:\n'
        '{"farcaster": "a post under 320 chars", "x": "a post under 280 chars"}\n\n'
        f"TRANSCRIPT:\n{body}"
    )
    if not data:
        return fallback
    return {
        "farcaster": (data.get("farcaster") or fallback["farcaster"])[:320],
        "x": (data.get("x") or fallback["x"])[:280],
        "backend": hermes.backend_name(),
    }


def clip_post(clip_text: str, title: str = "") -> dict:
    """Draft one short post for a single clip."""
    fallback = {"post": (title or _first_sentence(clip_text))[:280], "backend": "deterministic"}
    if not clip_text.strip():
        return fallback
    data = _run_json(
        f'Clip titled "{title}". Write ONE punchy social post (under 280 chars) that makes '
        'someone want to watch. Return JSON: {"post": "..."}\n\n'
        f"CLIP:\n{clip_text[:3000]}"
    )
    if not data:
        return fallback
    return {"post": (data.get("post") or fallback["post"])[:280], "backend": hermes.backend_name()}


def _strip_md(md: str) -> str:
    return "\n".join(line for line in md.splitlines() if not line.lstrip().startswith("#")).strip()


def _first_sentence(text: str) -> str:
    t = text.strip().replace("\n", " ")
    for sep in (". ", "! ", "? "):
        if sep in t:
            return t.split(sep)[0] + sep.strip()
    return t[:200]
