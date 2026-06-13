"""Cross-recording library search."""

import json

from backend.services import library_search


def _make_project(root, name, title, created_at, segments):
    d = root / name
    (d / "transcripts").mkdir(parents=True)
    (d / "project.json").write_text(json.dumps({"title": title, "created_at": created_at}))
    (d / "transcripts" / f"{name}.cut.json").write_text(json.dumps(segments))
    return d


def test_finds_phrase_across_projects(tmp_path):
    _make_project(tmp_path, "a", "Show A", "2026-06-01", [
        {"start": 10.0, "end": 12.0, "text": "We talked about WaveWarZ today"},
        {"start": 20.0, "end": 22.0, "text": "Nothing here"},
    ])
    _make_project(tmp_path, "b", "Show B", "2026-06-05", [
        {"start": 5.0, "end": 7.0, "text": "wavewarz is the prediction game"},
    ])
    res = library_search.search_transcripts(tmp_path, "wavewarz")
    assert len(res) == 2
    # newest first
    assert res[0]["project"] == "b"
    assert res[0]["matches"][0]["start"] == 5.0
    assert res[1]["count"] == 1


def test_case_insensitive(tmp_path):
    _make_project(tmp_path, "a", "A", "2026-06-01", [
        {"start": 1.0, "end": 2.0, "text": "SongJam Spaces tooling"},
    ])
    assert library_search.search_transcripts(tmp_path, "songjam")
    assert library_search.search_transcripts(tmp_path, "SPACES")


def test_no_match_returns_empty(tmp_path):
    _make_project(tmp_path, "a", "A", "2026-06-01", [
        {"start": 1.0, "end": 2.0, "text": "hello world"},
    ])
    assert library_search.search_transcripts(tmp_path, "nonexistent") == []


def test_empty_query_returns_empty(tmp_path):
    _make_project(tmp_path, "a", "A", "2026-06-01", [{"start": 0, "end": 1, "text": "x"}])
    assert library_search.search_transcripts(tmp_path, "  ") == []


def test_limit_per_project(tmp_path):
    segs = [{"start": float(i), "end": float(i) + 1, "text": "match here"} for i in range(10)]
    _make_project(tmp_path, "a", "A", "2026-06-01", segs)
    res = library_search.search_transcripts(tmp_path, "match", limit_per_project=3)
    assert res[0]["count"] == 3


def test_missing_dir(tmp_path):
    assert library_search.search_transcripts(tmp_path / "nope", "x") == []


def test_skips_unprocessed_projects(tmp_path):
    # project dir with no project.json is ignored
    (tmp_path / "stray").mkdir()
    _make_project(tmp_path, "a", "A", "2026-06-01", [{"start": 0, "end": 1, "text": "found it"}])
    res = library_search.search_transcripts(tmp_path, "found")
    assert len(res) == 1
