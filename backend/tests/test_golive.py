"""Go-live detection."""

from backend.services import golive


def test_live_stream_detected():
    def prober(url):
        return {"is_live": True, "title": "ZABAL Gamez Live", "uploader": "ZAO",
                "extractor": "youtube", "webpage_url": url}
    out = golive.check_live("https://youtube.com/watch?v=abc", prober=prober)
    assert out["live"] is True
    assert out["title"] == "ZABAL Gamez Live"
    assert out["error"] == ""


def test_not_live():
    def prober(url):
        return {"is_live": False, "title": "An old VOD", "webpage_url": url}
    out = golive.check_live("https://youtube.com/watch?v=abc", prober=prober)
    assert out["live"] is False
    assert out["title"] == "An old VOD"


def test_probe_failure_is_caught():
    def prober(url):
        raise RuntimeError("yt-dlp could not resolve the URL")
    out = golive.check_live("https://youtube.com/watch?v=abc", prober=prober)
    assert out["live"] is False
    assert "could not resolve" in out["error"]


def test_bad_url_rejected_without_probing():
    called = {"n": 0}
    def prober(url):
        called["n"] += 1
        return {"is_live": True}
    out = golive.check_live("not-a-url", prober=prober)
    assert out["live"] is False
    assert called["n"] == 0
    assert "valid http" in out["error"]
