"""ZABAL Gamez export - recaps.json block + transcript .md in the team's format."""

from backend.services import zabalgames_export as zx


SEGMENTS = [
    {"start": 0, "end": 4, "text": "Welcome to the workshop", "speaker": "Zaal"},
    {"start": 4, "end": 8, "text": "Let us talk WaveWarZ", "speaker": "Mike"},
]
INSIGHTS = {
    "recap": "A workshop about WaveWarZ - we walked the entry mechanics.",
    "chapters": [{"time": "00:00", "title": "Intro"}, {"time": "02:00", "title": "Entry timing"}],
    "quotes": [{"text": "Timing your entry is everything"}, {"text": "It costs 0.5 SOL"}],
}


def test_youtube_id_extracts():
    assert zx.youtube_id("https://youtu.be/abc12345678") == "abc12345678"
    assert zx.youtube_id("https://www.youtube.com/watch?v=abc12345678&t=3") == "abc12345678"
    assert zx.youtube_id("abc12345678") == "abc12345678"


def test_transcript_filename_convention():
    assert zx.transcript_filename("2026-06-12", "Hurricane Mike", "WaveWarZ") == \
        "2026-06-12-hurricane-mike-wavewarz.md"


def test_transcript_md_has_frontmatter_and_speakers():
    md = zx.transcript_md(SEGMENTS, "WaveWarZ Talk", "2026-06-12", "Mike",
                          track="Tokenomics", youtube="https://youtu.be/abc12345678")
    assert md.startswith("---")
    assert "presenter: Mike" in md
    assert "youtube: abc12345678" in md
    assert "**Zaal:** Welcome to the workshop" in md


def test_recaps_block_fields():
    b = zx.recaps_block(7, "WaveWarZ Talk", "2026-06-12", "Mike", INSIGHTS,
                        "data/streams/.../t.md", track="Tokenomics",
                        youtube="https://youtu.be/abc12345678")
    # exactly the fields the ZABAL Gamez team specified
    for f in ("date", "presenter", "track", "summary", "topics", "takeaways", "chapters", "youtube", "transcript"):
        assert f in b
    assert b["topics"] == ["Intro", "Entry timing"]
    assert b["takeaways"][0] == "Timing your entry is everything"
    assert b["youtube"] == "abc12345678"


def test_build_export_writes_files(tmp_path):
    bundle = zx.build_export(7, "WaveWarZ Talk", "2026-06-12", "Mike", SEGMENTS, INSIGHTS,
                            track="Tokenomics", youtube="abc12345678", out_dir=tmp_path)
    assert (tmp_path / "2026-06-12-mike-wavewarz-talk.md").exists()
    assert (tmp_path / "recaps-block-7.json").exists()
    assert bundle["recaps_block"]["id"] == 7


def test_em_dash_stripped():
    md = zx.transcript_md([{"text": "we shipped it - then iterated", "speaker": "Z"}],
                          "T", "2026-06-12", "Z")
    assert "—" not in md


def test_glossary_path_env(monkeypatch, tmp_path):
    import importlib
    custom = tmp_path / "g.json"
    custom.write_text('{"safe": {"foo": "Foo"}, "review": []}')
    monkeypatch.setenv("STUDIO_GLOSSARY_PATH", str(custom))
    import backend.services.glossary as g
    importlib.reload(g)
    try:
        assert g.load_corrections()["safe"]["foo"] == "Foo"
    finally:
        monkeypatch.delenv("STUDIO_GLOSSARY_PATH", raising=False)
        importlib.reload(g)
