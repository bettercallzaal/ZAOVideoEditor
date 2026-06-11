"""Ingest service: probe + availability with subprocess mocked (no network)."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from backend.services import ingest_service


def _fake_run(stdout="", returncode=0, stderr=""):
    def run(*args, **kwargs):
        return SimpleNamespace(stdout=stdout, returncode=returncode, stderr=stderr)
    return run


def test_yt_dlp_available_true(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout="2026.01.01", returncode=0))
    assert ingest_service.yt_dlp_available() is True


def test_yt_dlp_available_false_when_missing(monkeypatch):
    def raise_fnf(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr(subprocess, "run", raise_fnf)
    assert ingest_service.yt_dlp_available() is False


def test_probe_url_parses_metadata(monkeypatch):
    payload = {
        "title": "ZAO Stream", "duration": 3600, "uploader": "ZAO",
        "extractor_key": "Youtube", "is_live": False, "webpage_url": "https://x/y",
    }
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout=json.dumps(payload)))
    info = ingest_service.probe_url("https://youtube.com/watch?v=x")
    assert info["title"] == "ZAO Stream"
    assert info["duration"] == 3600
    assert info["extractor"] == "Youtube"
    assert info["is_live"] is False


def test_probe_url_raises_on_failure(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(returncode=1, stderr="ERROR: unsupported URL"))
    with pytest.raises(RuntimeError):
        ingest_service.probe_url("https://bad/url")


def test_progress_regex_matches():
    line = "[download]  45.2% of 12.34MiB at 1.00MiB/s ETA 00:07"
    m = ingest_service._PROGRESS_RE.search(line)
    assert m and float(m.group(1)) == 45.2


def test_supported_sources_nonempty():
    assert any(s["id"] == "youtube" for s in ingest_service.SUPPORTED_SOURCES)
