"""Access-password middleware: open when unset, gated when set."""

import base64

from backend.auth import _check, _expected


def _basic(user, pw):
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


def test_open_when_no_password(monkeypatch):
    monkeypatch.delenv("STUDIO_PASSWORD", raising=False)
    assert _expected() == ""


def test_check_accepts_correct_password():
    assert _check(_basic("anyone", "hunter2"), "hunter2") is True


def test_check_rejects_wrong_password():
    assert _check(_basic("anyone", "nope"), "hunter2") is False


def test_check_ignores_username():
    # username is ignored; only the password matters
    assert _check(_basic("", "hunter2"), "hunter2") is True


def test_check_rejects_non_basic():
    assert _check("Bearer abc", "hunter2") is False
    assert _check("", "hunter2") is False
