"""Social post generation - LLM via Hermes with deterministic fallback."""

from backend.services import social_gen


def test_episode_posts_fallback(monkeypatch):
    monkeypatch.setattr(social_gen.hermes, "run_prompt", lambda *a, **k: None)
    out = social_gen.episode_posts("# Talk\n\nWe launched WaveWarZ. It is live now.", title="Talk")
    assert out["backend"] == "deterministic"
    assert len(out["farcaster"]) <= 320
    assert len(out["x"]) <= 280
    assert "WaveWarZ" in out["farcaster"]


def test_episode_posts_uses_llm(monkeypatch):
    monkeypatch.setattr(social_gen.hermes, "run_prompt",
                        lambda *a, **k: '{"farcaster": "fc post", "x": "x post"}')
    monkeypatch.setattr(social_gen.hermes, "backend_name", lambda: "claude-cli")
    out = social_gen.episode_posts("# T\n\nbody here", title="T")
    assert out["farcaster"] == "fc post" and out["x"] == "x post"
    assert out["backend"] == "claude-cli"


def test_clip_post_fallback(monkeypatch):
    monkeypatch.setattr(social_gen.hermes, "run_prompt", lambda *a, **k: None)
    out = social_gen.clip_post("A surprising moment about Stilo World", title="Hook")
    assert out["post"] == "Hook"
    assert len(out["post"]) <= 280


def test_clip_post_truncates(monkeypatch):
    monkeypatch.setattr(social_gen.hermes, "run_prompt", lambda *a, **k: '{"post": "' + "x" * 400 + '"}')
    monkeypatch.setattr(social_gen.hermes, "backend_name", lambda: "claude-cli")
    out = social_gen.clip_post("text", title="t")
    assert len(out["post"]) <= 280
