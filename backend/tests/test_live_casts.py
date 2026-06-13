"""Day-of livestream casts from the ZABAL Gamez templates."""

import json

from backend.services import live_casts


def test_day_of_casts_fills_template():
    c = live_casts.day_of_casts(
        name="Adam Miller", org="MiDAO", topic="building miDAO",
        time="5:45pm", luma="https://luma.com/l1c6sgzc", handle="adammiller",
    )
    assert c["warning"].startswith("zm\n\n15 minutes out. Adam Miller of MiDAO")
    assert "building miDAO" in c["warning"]
    assert "5:45pm EST" in c["warning"]
    assert "luma.com/l1c6sgzc" in c["warning"]
    assert "zabalgames.com/live" in c["warning"]
    assert c["live_now"].startswith("zm\n\nLive now: @adammiller of MiDAO")


def test_day_of_drops_org_when_absent():
    c = live_casts.day_of_casts(name="Solo Dev", topic="a thing", handle="solo")
    assert "Solo Dev is up next" in c["warning"]
    assert " of " not in c["warning"].split("up next")[0]


def test_day_of_handle_falls_back_to_name():
    c = live_casts.day_of_casts(name="Jane Doe", topic="x")
    assert "@janedoe" in c["live_now"]


def test_no_em_dashes():
    c = live_casts.day_of_casts(name="A", org="B", topic="c - d", time="1pm")
    assert "—" not in c["warning"] and "—" not in c["live_now"]


def test_list_sessions_reads_leads(tmp_path, monkeypatch):
    p = tmp_path / "workshop-leads.json"
    p.write_text(json.dumps({
        "season": 1, "luma_calendar": "https://luma.com/zabal",
        "leads": [{"id": "001", "name": "Tyler", "org": "Magnetiq", "topic": "the platform",
                   "track": "builder", "status": "confirmed"}],
    }))
    monkeypatch.setenv("STUDIO_WORKSHOP_LEADS", str(p))
    ss = live_casts.list_sessions()
    assert len(ss) == 1
    assert ss[0]["name"] == "Tyler"
    assert ss[0]["luma"] == "https://luma.com/zabal"  # falls back to calendar
