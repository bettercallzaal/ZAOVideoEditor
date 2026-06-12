"""Opt-in: push a recording's recap into the ZABAL Bonfire knowledge graph.

Bonfire is ZAO's knowledge-graph memory (zabal.bonfires.ai). Posting a recording's
recap turns it into queryable institutional memory - "what did we say about X" months
later. This is OPT-IN: nothing posts unless the user explicitly asks (a button click /
an explicit API call). The episode body is a natural-language prose recap; Bonfire's
auto-extraction turns it into graph nodes.

Credentials: BONFIRE_API_KEY + BONFIRE_ID (+ optional BONFIRE_API_URL) from the
environment, or from ~/.zao/zao.env / ~/.zao/bonfire.env if not already exported.
The key is never written to disk by this code and never included in any episode body.
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DEFAULT_API_URL = "https://tnt-v2.api.bonfires.ai"
_ENV_FILES = [Path.home() / ".zao" / "zao.env", Path.home() / ".zao" / "bonfire.env"]

# Refuse to post anything that looks like a secret (mirrors secret-hygiene.md).
_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{36}|"
    r"Bearer\s+[A-Za-z0-9._-]{20,}|\b[0-9a-fA-F]{64}\b|BEGIN (?:RSA |EC )?PRIVATE KEY)"
)
# Redact raw emails / phone numbers from third parties before they enter the graph.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\+?\d{1,3}[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
_EMAIL_ALLOW = {"zaal@thezao.com", "hello@thezao.com", "support@thezao.com", "zaalp99@gmail.com"}


def _load_env_files():
    for f in _ENV_FILES:
        if not f.exists():
            continue
        try:
            for line in f.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                if k in ("BONFIRE_API_KEY", "BONFIRE_ID", "BONFIRE_API_URL") and not os.environ.get(k):
                    os.environ[k] = v.strip().strip('"').strip("'")
        except OSError:
            pass


def _creds() -> tuple:
    if not (os.environ.get("BONFIRE_API_KEY") and os.environ.get("BONFIRE_ID")):
        _load_env_files()
    return (
        os.environ.get("BONFIRE_API_KEY", "").strip(),
        os.environ.get("BONFIRE_ID", "").strip(),
        os.environ.get("BONFIRE_API_URL", DEFAULT_API_URL).strip() or DEFAULT_API_URL,
    )


def configured() -> bool:
    key, bid, _ = _creds()
    return bool(key and bid)


def _scrub(text: str) -> str:
    """Redact third-party emails / phones (keep ZAO public addresses)."""
    def _email(m):
        return m.group(0) if m.group(0).lower() in _EMAIL_ALLOW else "<redacted-email>"
    text = _EMAIL_RE.sub(_email, text)
    text = _PHONE_RE.sub("<redacted-phone>", text)
    return text


def post_episode(name: str, body: str, source_tag: str = "recording") -> dict:
    """Post one natural-language episode. Raises on missing creds or a secret in body."""
    key, bid, url = _creds()
    if not (key and bid):
        raise RuntimeError("Bonfire not configured: set BONFIRE_API_KEY + BONFIRE_ID (or ~/.zao/zao.env)")
    body = _scrub(body)
    if _SECRET_RE.search(body) or _SECRET_RE.search(name):
        raise RuntimeError("Refusing to post: the episode contains a secret-shaped string")

    import requests
    payload = {
        "bonfire_id": bid,
        "name": name[:200],
        "episode_body": body,
        "source": "text",
        "source_description": source_tag,
        "reference_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }
    r = requests.post(
        f"{url}/knowledge_graph/episode/create",
        json=payload, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        timeout=20,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"Bonfire post failed ({r.status_code}): {r.text[:160]}")
    return {"posted": True, "name": payload["name"]}


def build_episode_body(title: str, recap: str, chapters: Optional[list] = None,
                       quotes: Optional[list] = None, date: str = "") -> str:
    """Assemble a prose recap episode body from the Studio's insights."""
    lines = [f"Recording: {title}." + (f" Date: {date}." if date else ""), "", recap.strip()]
    if chapters:
        lines += ["", "Topics covered: " + ", ".join(c.get("title", "") for c in chapters if c.get("title")) + "."]
    if quotes:
        lines += ["", "Notable points:"]
        for q in quotes[:5]:
            t = (q.get("text") or "").strip()
            if t:
                lines.append(f"- {t}")
    return "\n".join(lines)


def post_recording(title: str, insights: dict, date: str = "") -> dict:
    """Build + post a single recap episode for a recording (opt-in caller)."""
    body = build_episode_body(
        title, insights.get("recap", ""),
        insights.get("chapters"), insights.get("quotes"), date,
    )
    if not body.strip() or not insights.get("recap"):
        raise RuntimeError("No recap to post - extract key moments first")
    name = f"{title}" + (f" ({date})" if date else "")
    return post_episode(name, body, source_tag="zao-recording")
