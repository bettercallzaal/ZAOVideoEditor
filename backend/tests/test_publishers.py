"""Publishers: credential handling + request construction (no live API calls)."""

import pytest

from backend.services import publishers


def test_status_shape(monkeypatch):
    monkeypatch.delenv("NEYNAR_API_KEY", raising=False)
    s = publishers.status()
    assert set(s) == {"farcaster", "x", "youtube"}


def test_farcaster_requires_creds(monkeypatch):
    monkeypatch.delenv("NEYNAR_API_KEY", raising=False)
    monkeypatch.delenv("FARCASTER_SIGNER_UUID", raising=False)
    assert publishers.farcaster_configured() is False
    with pytest.raises(RuntimeError, match="NEYNAR_API_KEY"):
        publishers.post_farcaster("hi")


def test_farcaster_posts_with_creds(monkeypatch):
    monkeypatch.setenv("NEYNAR_API_KEY", "k")
    monkeypatch.setenv("FARCASTER_SIGNER_UUID", "s")
    captured = {}

    class R:
        status_code = 200
        def json(self):
            return {"cast": {"hash": "0xabc"}}
    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"], captured["json"], captured["headers"] = url, json, headers
        return R()
    import requests
    monkeypatch.setattr(requests, "post", fake_post)

    out = publishers.post_farcaster("hello", embed_urls=["https://x.co/c.mp4"])
    assert captured["url"].endswith("/v2/farcaster/cast")
    assert captured["headers"]["x-api-key"] == "k"
    assert captured["json"]["signer_uuid"] == "s"
    assert captured["json"]["embeds"] == [{"url": "https://x.co/c.mp4"}]
    assert out["hash"] == "0xabc"


def test_x_requires_creds(monkeypatch):
    for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"):
        monkeypatch.delenv(k, raising=False)
    assert publishers.x_configured() is False
    with pytest.raises(RuntimeError, match="X_API_KEY"):
        publishers.post_x("hi")


def test_youtube_requires_credentials_file(monkeypatch, tmp_path):
    monkeypatch.setattr(publishers, "GOOGLE_CREDENTIALS", tmp_path / "nope.json")
    assert publishers.youtube_configured() is False
    with pytest.raises(RuntimeError):
        publishers.upload_youtube(str(tmp_path / "v.mp4"), "t")
