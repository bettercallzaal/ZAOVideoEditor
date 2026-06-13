"""ZABAL Gamez export - recaps.json entry + transcript .md in the team's real format."""

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
OPTS = {
    "title": "Building WaveWarZ", "date": "2026-06-12", "presenter": "Hurricane Mike",
    "handle": "@hurricane", "org": "WaveWarZ", "track": "builder", "type": "workshop",
    "youtube": "https://youtu.be/abc12345678", "number": 8, "episode": 3,
}


def test_youtube_id_extracts():
    assert zx.youtube_id("https://youtu.be/abc12345678") == "abc12345678"
    assert zx.youtube_id("https://www.youtube.com/watch?v=abc12345678&t=3") == "abc12345678"


def test_transcript_filename_convention():
    assert zx.transcript_filename("2026-06-12", "Hurricane Mike", "WaveWarZ") == \
        "2026-06-12-hurricane-mike-wavewarz.md"


def test_transcript_md_frontmatter_matches_schema():
    md = zx.transcript_md(SEGMENTS, "Building WaveWarZ", "2026-06-12T00:00:00.000Z",
                          "Hurricane Mike", track="builder",
                          youtube="https://youtu.be/abc12345678", episode=3)
    assert "show: ZABAL Gamez Workshops" in md
    assert "host: Zaal" in md
    assert "episode: 3" in md
    assert "youtube: https://youtu.be/abc12345678" in md
    assert "**Zaal:** Welcome to the workshop" in md


def test_recaps_entry_has_real_fields():
    e = zx.recaps_entry(OPTS, INSIGHTS, "data/streams/.../t.md")
    for f in ("date", "type", "title", "presenter", "track", "format", "summary",
              "topics", "takeaways", "share_topics", "transcript"):
        assert f in e
    assert e["type"] == "workshop"
    assert e["handle"] == "@hurricane"          # optional, included when present
    assert e["org"] == "WaveWarZ"
    assert e["page"] == "/recordings/8"
    assert e["youtube"] == "https://youtu.be/abc12345678"
    assert e["topics"] == ["Intro", "Entry timing"]
    assert e["takeaways"][0] == "Timing your entry is everything"
    assert len(e["share_topics"]) >= 1


def test_recaps_entry_omits_empty_optionals():
    e = zx.recaps_entry({"title": "T", "date": "2026-06-12", "presenter": "P"}, INSIGHTS, "t.md")
    assert "handle" not in e and "org" not in e and "youtube" not in e and "page" not in e


def test_build_export_writes_files(tmp_path):
    bundle = zx.build_export(OPTS, SEGMENTS, INSIGHTS, out_dir=tmp_path)
    assert (tmp_path / "2026-06-12-hurricane-mike-building-wavewarz.md").exists()
    assert (tmp_path / "recaps-entry-8.json").exists()
    assert bundle["recaps_entry"]["title"] == "Building WaveWarZ"
    assert "T00:00:00.000Z" in bundle["transcript_md"]  # ISO date in frontmatter


def test_em_dash_stripped():
    md = zx.transcript_md([{"text": "we shipped it - then iterated", "speaker": "Z"}],
                          "T", "2026-06-12T00:00:00.000Z", "Z")
    assert "—" not in md
