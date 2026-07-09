"""Audiogram HTTP surface: path safety and the audio-only contract."""

import subprocess

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import project_utils


@pytest.fixture
def client(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    projects.mkdir()
    monkeypatch.setattr(project_utils, "PROJECTS_DIR", projects)

    import backend.routers.audiogram as router_mod
    monkeypatch.setattr(router_mod, "get_project_dir", project_utils.get_project_dir)

    monkeypatch.setenv("STUDIO_PASSWORD", "")
    return TestClient(app), projects


def _project(projects, name, media_name=None, seconds=2):
    d = projects / name
    (d / "input").mkdir(parents=True)
    (d / "processing").mkdir(parents=True)
    if media_name:
        args = ["ffmpeg", "-y", "-f", "lavfi",
                "-i", f"sine=frequency=440:duration={seconds}"]
        if media_name.endswith(".mp4") and "video" in media_name:
            args = ["ffmpeg", "-y", "-f", "lavfi",
                    "-i", f"testsrc=duration={seconds}:size=320x240:rate=10",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        args.append(str(d / "input" / ("main.mp4" if "mp4" in media_name else media_name)))
        subprocess.run(args, check=True, capture_output=True)
    return d


@pytest.mark.parametrize("bad", ["../etc", "..%2fetc", "a/b", "a\\b", ".."])
def test_traversal_names_are_rejected(client, bad):
    c, _ = client
    r = c.get(f"/api/audiogram/{bad}/status")
    assert r.status_code in (403, 404, 422), r.status_code


def test_status_404_for_unknown_project(client):
    c, _ = client
    assert c.get("/api/audiogram/nope/status").status_code == 404


def test_status_reports_audio_only(client):
    c, projects = client
    _project(projects, "space", "main.mp4")

    r = c.get("/api/audiogram/space/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["audio_only"] is True
    assert body["audiogram_exists"] is False
    assert body["duration"] == pytest.approx(2.0, abs=0.4)
    assert isinstance(body["can_burn_captions"], bool)


def test_render_rejects_a_project_that_already_has_video(client):
    c, projects = client
    _project(projects, "vid", "video.mp4")

    r = c.post("/api/audiogram/vid", json={})
    assert r.status_code == 400
    assert "already has a video stream" in r.json()["detail"]


def test_render_returns_a_task_id(client):
    c, projects = client
    _project(projects, "space", "main.mp4")

    r = c.post("/api/audiogram/space", json={"title": "Zaal x Kenny"})
    assert r.status_code == 200, r.text
    assert r.json()["task_id"]


def test_render_404_when_no_input_media(client):
    c, projects = client
    _project(projects, "empty")
    assert c.post("/api/audiogram/empty", json={}).status_code == 404
