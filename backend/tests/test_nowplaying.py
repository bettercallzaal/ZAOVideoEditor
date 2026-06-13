"""Now playing: parse, post, source fetch, song ID."""

from backend.services import nowplaying


def test_parse_artist_dash_title():
    assert nowplaying.parse_track("Daft Punk - Around the World") == {
        "artist": "Daft Punk", "title": "Around the World"}


def test_parse_title_by_artist():
    assert nowplaying.parse_track("Around the World by Daft Punk") == {
        "artist": "Daft Punk", "title": "Around the World"}


def test_parse_bare_title():
    assert nowplaying.parse_track("Untitled Jam") == {"artist": "", "title": "Untitled Jam"}


def test_parse_strips_now_playing_prefix():
    assert nowplaying.parse_track("Now Playing: Stilo World - Anthem")["title"] == "Anthem"


def test_post_with_artist_is_brand_clean():
    p = nowplaying.now_playing_post("Anthem", "Stilo World")
    assert "[MUSIC] Now playing: Anthem by Stilo World" in p["farcaster"]
    assert "—" not in p["farcaster"] and "—" not in p["x"]
    assert "zabalgames.com/live" in p["farcaster"]


def test_post_without_artist():
    p = nowplaying.now_playing_post("Untitled Jam")
    assert "Now playing: Untitled Jam" in p["x"]


def test_post_empty_title_errors():
    assert nowplaying.now_playing_post("")["error"]


def test_post_custom_live_url_and_handle():
    p = nowplaying.now_playing_post("Anthem", "Stilo World",
                                    live_url="https://x.com/live", handle="@stilo")
    assert "https://x.com/live" in p["farcaster"]
    assert "@stilo" in p["farcaster"]


def test_fetch_source_url():
    p = nowplaying.fetch_source("https://np.example/now", fetcher=lambda u: "DJ Set - Track One\n")
    assert p["artist"] == "DJ Set"
    assert p["title"] == "Track One"


def test_fetch_source_file(tmp_path):
    f = tmp_path / "now.txt"
    f.write_text("Stilo World - Anthem\nnext line ignored")
    p = nowplaying.fetch_source(str(f))
    assert p["title"] == "Anthem"


def test_fetch_source_empty():
    assert nowplaying.fetch_source("")["error"]


def test_fetch_source_error_caught():
    def boom(u):
        raise RuntimeError("404")
    p = nowplaying.fetch_source("https://np.example/x", fetcher=boom)
    assert p["error"] == "404"


def test_recognize_no_token():
    assert nowplaying.recognize("x.webm", token="")["error"]


def test_recognize_hit():
    def poster(path, token):
        return {"result": {"artist": "Daft Punk", "title": "One More Time"}}
    out = nowplaying.recognize("x.webm", token="k", poster=poster)
    assert out == {"artist": "Daft Punk", "title": "One More Time"}


def test_recognize_no_match():
    assert nowplaying.recognize("x.webm", token="k", poster=lambda p, t: {"result": None})["error"] == "No match"


def test_recognize_error_caught():
    def boom(p, t):
        raise RuntimeError("network down")
    assert nowplaying.recognize("x.webm", token="k", poster=boom)["error"] == "network down"
