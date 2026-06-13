"""Distribution bundle assembly."""

import json
import zipfile
from pathlib import Path

from backend.services import bundle_service


def _project(tmp_path):
    d = tmp_path / "wavewarz-talk"
    for sub in ("transcripts", "clips", "metadata", "exports"):
        (d / sub).mkdir(parents=True)
    (d / "project.json").write_text(json.dumps({"title": "WaveWarZ Talk", "created_at": "2026-06-13"}))
    return d


def _entries(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        return set(z.namelist())


def test_full_bundle(tmp_path):
    d = _project(tmp_path)
    (d / "transcripts" / "x.readable.md").write_text("# Title\nclean transcript")
    (d / "transcripts" / "x.cut.md").write_text("[0:00] hi")
    (d / "clips" / "clip1_9x16.mp4").write_bytes(b"fakevideo")
    (d / "clips" / "clip1.copy.json").write_text(json.dumps(
        {"title": "Hot take", "caption": "watch this", "hashtags": ["zao", "#wavewarz"]}))
    (d / "metadata" / "insights.json").write_text(json.dumps(
        {"recap": "It was great", "chapters": [{"start": 65, "title": "Intro"}],
         "quotes": [{"text": "let's go"}]}))
    (d / "metadata" / "socials.json").write_text(json.dumps(
        {"episode": {"farcaster": "fc post", "x": "x post"}, "clips": [{"post": "clip post"}]}))

    res = bundle_service.build_bundle(d)
    assert Path(res["zip"]).exists()
    names = _entries(res["zip"])
    assert "transcript.md" in names
    assert "transcript-timestamped.md" in names
    assert "clips/clip1_9x16.mp4" in names
    assert "recap.md" in names
    assert "posts.md" in names
    assert "clip-copy.md" in names
    assert "manifest.json" in names
    assert res["manifest"]["clips"] == 1
    assert res["manifest"]["title"] == "WaveWarZ Talk"


def test_minimal_project_still_bundles(tmp_path):
    d = _project(tmp_path)  # no transcript, clips, insights, socials
    res = bundle_service.build_bundle(d)
    assert Path(res["zip"]).exists()
    names = _entries(res["zip"])
    assert names == {"manifest.json"}
    assert res["manifest"]["clips"] == 0
    assert res["manifest"]["has_recap"] is False


def test_recap_md_has_chapter_timestamp(tmp_path):
    d = _project(tmp_path)
    (d / "metadata" / "insights.json").write_text(json.dumps(
        {"recap": "r", "chapters": [{"start": 125, "title": "Deep dive"}]}))
    bundle_service.build_bundle(d)
    with zipfile.ZipFile(d / "exports" / "wavewarz-talk-bundle.zip") as z:
        recap = z.read("recap.md").decode()
    assert "[2:05] Deep dive" in recap


def test_corrupt_metadata_ignored(tmp_path):
    d = _project(tmp_path)
    (d / "metadata" / "insights.json").write_text("{ not json")
    res = bundle_service.build_bundle(d)
    assert res["manifest"]["has_recap"] is False
