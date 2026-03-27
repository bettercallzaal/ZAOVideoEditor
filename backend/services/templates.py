"""Template/preset management for processing settings."""

import json
from pathlib import Path

TEMPLATES_FILE = Path(__file__).parent.parent.parent / "shared" / "templates.json"


def _load_all() -> dict:
    """Load all templates from disk."""
    if not TEMPLATES_FILE.exists():
        return {}
    try:
        with open(TEMPLATES_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_all(templates: dict):
    """Save all templates to disk."""
    TEMPLATES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TEMPLATES_FILE, "w") as f:
        json.dump(templates, f, indent=2)


def save_template(name: str, settings: dict) -> dict:
    """Save a named preset with processing settings."""
    allowed_keys = {
        "quality", "engine", "use_intro", "intro_filename",
        "use_outro", "outro_filename", "remove_silence",
        "silence_threshold", "silence_margin", "refine_timestamps",
    }
    filtered = {k: v for k, v in settings.items() if k in allowed_keys}

    templates = _load_all()
    templates[name] = filtered
    _save_all(templates)
    return filtered


def load_template(name: str) -> dict | None:
    """Return a single preset by name, or None if not found."""
    templates = _load_all()
    return templates.get(name)


def list_templates() -> dict:
    """Return all presets as {name: settings}."""
    return _load_all()


def delete_template(name: str) -> bool:
    """Remove a preset. Returns True if it existed."""
    templates = _load_all()
    if name not in templates:
        return False
    del templates[name]
    _save_all(templates)
    return True
