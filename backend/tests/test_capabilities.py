"""Capabilities report."""

from backend.services import capabilities


def test_shape(monkeypatch):
    cap = capabilities.get_capabilities()
    assert "core" in cap and "integrations" in cap and "summary" in cap
    assert cap["core"] and all("label" in c for c in cap["core"])
    assert all({"key", "label", "on", "hint"} <= set(i) for i in cap["integrations"])
    assert cap["summary"]["integrations_total"] == len(cap["integrations"])


def test_groq_toggle_reflected(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    cap = capabilities.get_capabilities()
    groq = next(i for i in cap["integrations"] if i["key"] == "groq")
    assert groq["on"] is True
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    cap2 = capabilities.get_capabilities()
    groq2 = next(i for i in cap2["integrations"] if i["key"] == "groq")
    assert groq2["on"] is False


def test_audd_toggle(monkeypatch):
    monkeypatch.delenv("AUDD_API_TOKEN", raising=False)
    cap = capabilities.get_capabilities()
    assert next(i for i in cap["integrations"] if i["key"] == "songid")["on"] is False
    monkeypatch.setenv("AUDD_API_TOKEN", "tok")
    cap = capabilities.get_capabilities()
    assert next(i for i in cap["integrations"] if i["key"] == "songid")["on"] is True


def test_zabalgames_path_toggle(monkeypatch):
    monkeypatch.setenv("STUDIO_ZABALGAMES_PATH", "/tmp/zg")
    cap = capabilities.get_capabilities()
    assert next(i for i in cap["integrations"] if i["key"] == "zabalgames")["on"] is True


def test_password_toggle(monkeypatch):
    monkeypatch.setenv("STUDIO_PASSWORD", "secret")
    cap = capabilities.get_capabilities()
    assert next(i for i in cap["integrations"] if i["key"] == "password")["on"] is True


def test_summary_counts_match(monkeypatch):
    cap = capabilities.get_capabilities()
    on = sum(1 for i in cap["integrations"] if i["on"])
    assert cap["summary"]["integrations_on"] == on


def test_every_integration_has_hint():
    cap = capabilities.get_capabilities()
    assert all(i["hint"] for i in cap["integrations"])
