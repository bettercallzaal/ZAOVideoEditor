"""Hermes LLM pattern: run prompts through the `claude` CLI subprocess.

The ZAO convention: agents spawn the Claude Code CLI (Max-plan OAuth) instead of
direct API calls, so LLM steps have zero marginal cost. If the CLI is not
available, fall back to the existing Ollama/OpenAI client in content_gen.
"""

import subprocess
from typing import Optional


def claude_cli_available() -> bool:
    try:
        r = subprocess.run(["claude", "--version"], capture_output=True, timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_via_cli(prompt: str, timeout: int) -> Optional[str]:
    """Pipe the prompt into `claude -p` (print mode) and return its text."""
    try:
        r = subprocess.run(
            ["claude", "-p"],
            input=prompt, capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    out = (r.stdout or "").strip()
    return out or None


def _run_via_client(prompt: str) -> Optional[str]:
    """Fallback: the existing Ollama/OpenAI/Groq client from content_gen."""
    from .content_gen import _get_client
    client, model = _get_client()
    if not client:
        return None
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4096,
        )
        return (resp.choices[0].message.content or "").strip() or None
    except Exception:
        return None


def run_prompt(prompt: str, system: Optional[str] = None, timeout: int = 300) -> Optional[str]:
    """Run a prompt through Hermes (claude CLI), then the client fallback.

    Returns the model's text, or None if no backend is available. The system
    prompt is prepended into the message so it works identically across both
    backends.
    """
    full = f"{system.strip()}\n\n{prompt}" if system else prompt
    out = _run_via_cli(full, timeout)
    if out is not None:
        return out
    return _run_via_client(full)


def backend_name() -> str:
    """Which backend run_prompt would use right now (for diagnostics)."""
    if claude_cli_available():
        return "claude-cli"
    try:
        from .content_gen import _get_client
        _, model = _get_client()
        return f"client:{model}" if model else "none"
    except Exception:
        return "none"
