"""Bonfire memory ingest - opt-in, secret-safe, PII-scrubbed."""

import pytest

from backend.services import bonfire


def test_not_configured(monkeypatch):
    monkeypatch.delenv("BONFIRE_API_KEY", raising=False)
    monkeypatch.delenv("BONFIRE_ID", raising=False)
    monkeypatch.setattr(bonfire, "_ENV_FILES", [])  # don't read ~/.zao in the test
    assert bonfire.configured() is False
    with pytest.raises(RuntimeError, match="not configured"):
        bonfire.post_episode("n", "b")


def test_scrub_redacts_third_party_email_keeps_zao():
    out = bonfire._scrub("ping someone@randomcorp.com and zaal@thezao.com")
    assert "<redacted-email>" in out
    assert "zaal@thezao.com" in out


def test_refuses_secret_in_body(monkeypatch):
    monkeypatch.setenv("BONFIRE_API_KEY", "k")
    monkeypatch.setenv("BONFIRE_ID", "b")
    monkeypatch.setattr(bonfire, "_ENV_FILES", [])
    secret = "ghp_" + "a" * 36
    with pytest.raises(RuntimeError, match="secret"):
        bonfire.post_episode("name", f"here is a token {secret}")


def test_build_episode_body():
    body = bonfire.build_episode_body(
        "WaveWarZ Talk", "We launched it.",
        chapters=[{"title": "Intro"}, {"title": "Tokenomics"}],
        quotes=[{"text": "Timing is everything"}], date="2026-06-12",
    )
    assert "WaveWarZ Talk" in body and "We launched it." in body
    assert "Intro, Tokenomics" in body
    assert "Timing is everything" in body


def test_post_recording_calls_api(monkeypatch):
    monkeypatch.setenv("BONFIRE_API_KEY", "k")
    monkeypatch.setenv("BONFIRE_ID", "bid")
    monkeypatch.setattr(bonfire, "_ENV_FILES", [])
    captured = {}

    class R:
        status_code = 200
        text = "ok"
    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"], captured["json"], captured["headers"] = url, json, headers
        return R()
    import requests
    monkeypatch.setattr(requests, "post", fake_post)

    out = bonfire.post_recording("Demo", {"recap": "A summary."}, date="2026-06-12")
    assert out["posted"] is True
    assert captured["url"].endswith("/knowledge_graph/episode/create")
    assert captured["headers"]["Authorization"] == "Bearer k"
    assert captured["json"]["bonfire_id"] == "bid"
    assert captured["json"]["source"] == "text"


def test_post_recording_requires_recap(monkeypatch):
    monkeypatch.setenv("BONFIRE_API_KEY", "k")
    monkeypatch.setenv("BONFIRE_ID", "bid")
    monkeypatch.setattr(bonfire, "_ENV_FILES", [])
    with pytest.raises(RuntimeError, match="recap"):
        bonfire.post_recording("Demo", {"recap": ""})
