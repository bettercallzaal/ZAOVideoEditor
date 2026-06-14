"""YouTube package: title, description with 0:00 chapters, tags."""

from backend.services import youtube_package as yp


INSIGHTS = {
    "recap": "A talk about building WaveWarZ and SongJam tooling.",
    "chapters": [
        {"start": 90, "title": "The pitch"},
        {"start": 0, "title": "Welcome"},
        {"start": 3725, "title": "Q and A"},
    ],
}


def test_chapters_sorted_and_first_is_zero():
    rows = yp.build_chapters(INSIGHTS["chapters"])
    assert rows[0] == "0:00 Welcome"
    assert rows[1] == "1:30 The pitch"
    assert rows[2] == "1:02:05 Q and A"  # hours formatting


def test_chapters_force_zero_when_missing():
    rows = yp.build_chapters([{"start": 30, "title": "Late start"}])
    assert rows[0] == "0:00 Intro"
    assert rows[1] == "0:30 Late start"


def test_chapters_empty():
    assert yp.build_chapters([]) == []


def test_tags_include_brand_mentions():
    tags = yp.build_tags(INSIGHTS)
    assert "WaveWarZ" in tags
    assert "SongJam" in tags
    assert "The ZAO" in tags  # base tag


def test_tags_extra_appended_dedup():
    tags = yp.build_tags(INSIGHTS, extra=["The ZAO", "custom"])
    assert tags.count("The ZAO") == 1
    assert "custom" in tags


def test_description_has_recap_and_chapters():
    desc = yp.build_description(INSIGHTS, footer="Watch more at zabalgames.com/live")
    assert "building WaveWarZ" in desc
    assert "Chapters:" in desc
    assert "0:00 Welcome" in desc
    assert "zabalgames.com/live" in desc


def test_description_no_em_dashes():
    ins = {"recap": "a - b", "chapters": [{"start": 0, "title": "x - y"}]}
    desc = yp.build_description({**ins, "recap": "a — b"})
    assert "—" not in desc


def test_package_shape():
    pkg = yp.build_package(INSIGHTS, title="My Talk")
    assert pkg["title"] == "My Talk"
    assert "Chapters:" in pkg["description"]
    assert isinstance(pkg["tags"], list) and pkg["tags"]
    assert pkg["chapters"][0].startswith("0:00")
