"""Publish bundle generation for /recordings/N."""

import json
from pathlib import Path

from backend.services import publish_service as ps


def test_slugify():
    assert ps.slugify("WaveWarZ Talk!") == "wavewarz-talk"
    assert ps.slugify("") == "untitled"


def test_transcript_filename_convention():
    fn = ps.transcript_filename("2026-06-10", "Hurricane Mike", "WaveWarZ")
    assert fn == "2026-06-10-hurricane-mike-wavewarz.md"


def test_recap_entry_with_and_without_youtube():
    e = ps.build_recap_entry(5, "Talk", "2026-06-10", "a summary", youtube_id="abc123")
    assert e["id"] == 5 and e["youtube"] == "abc123"
    e2 = ps.build_recap_entry(6, "Talk2", "2026-06-10", "x")
    assert "youtube" not in e2


def test_page_md_includes_clips_and_transcript():
    md = ps.build_page_md(
        3, "Talk", "2026-06-10", "Body paragraph here.",
        youtube_id="yt1", clips=[{"base": "c1", "copy": {"title": "Hook A"}}],
    )
    assert "# Recording 3: Talk" in md
    assert "Hook A" in md
    assert "Body paragraph here." in md
    assert "youtu.be/yt1" in md


def test_build_bundle_writes_files(tmp_path):
    result = {"title": "WaveWarZ Talk", "readable_markdown": "# WaveWarZ Talk\n\nWe launched it.\n"}
    bundle = ps.build_bundle(result, 7, "2026-06-10", presenter="Zaal", topic="WaveWarZ",
                             youtube_id="vid7", out_dir=str(tmp_path))
    assert bundle["recap_entry"]["summary"] == "We launched it."
    out = Path(bundle["output_dir"])
    assert (out / "transcripts" / "2026-06-10-zaal-wavewarz.md").exists()
    assert (out / "recordings" / "7.md").exists()
    assert (out / "recap-7.json").exists()


def test_merge_into_index_replaces_by_id(tmp_path):
    idx = tmp_path / "index.json"
    idx.write_text(json.dumps([{"id": 1, "title": "old"}, {"id": 2, "title": "two"}]))
    merged = ps.merge_into_index(idx, {"id": 1, "title": "new"})
    by_id = {e["id"]: e["title"] for e in merged}
    assert by_id[1] == "new" and by_id[2] == "two"
    assert [e["id"] for e in merged] == [1, 2]  # sorted, no dupes
