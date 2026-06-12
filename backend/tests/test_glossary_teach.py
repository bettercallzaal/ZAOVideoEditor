"""Teaching the glossary + LLM clip-plan fallback."""

import json

from backend.services import glossary
from backend.services import recordings_export as rx


def test_add_safe_correction_persists(tmp_path):
    p = tmp_path / "corr.json"
    glossary.add_safe_correction("zabal gomez", "ZABAL Gamez", path=p)
    data = json.loads(p.read_text())
    assert data["safe"]["zabal gomez"] == "ZABAL Gamez"
    # idempotent overwrite
    glossary.add_safe_correction("zabal gomez", "ZABAL Gamez", path=p)
    assert json.loads(p.read_text())["safe"]["zabal gomez"] == "ZABAL Gamez"


def test_add_safe_correction_requires_both():
    import pytest
    with pytest.raises(ValueError):
        glossary.add_safe_correction("", "X")


def test_taught_term_then_applies(tmp_path):
    p = tmp_path / "corr.json"
    glossary.add_safe_correction("zabal gomez", "ZABAL Gamez", path=p)
    corr = glossary.load_corrections(p)
    out, changes = glossary.apply_safe_corrections("welcome to the Zabal Gomez workshop", corr)
    assert "ZABAL Gamez" in out


def test_plan_clips_falls_back_to_keyword_without_llm(monkeypatch):
    # force the LLM path to raise so the keyword detector is used
    import backend.services.content_gen as cg
    def boom(*a, **k):
        raise RuntimeError("no llm")
    monkeypatch.setattr(cg, "generate_recap_and_clips", boom)
    segs = [{"id": i, "start": i * 10, "end": i * 10 + 8,
             "text": f"this is a really insightful point number {i} about strategy",
             "words": []} for i in range(8)]
    plan = rx.plan_clips(segs, use_llm=True)
    assert isinstance(plan, list)
