"""ZABAL Gamez distribution casts: this-week (schedule-driven) + static announces."""

from backend.services import live_casts


LEADS = [
    {"name": "Tyler", "org": "Magnetiq", "topic": "the platform", "status": "confirmed",
     "date": "2026-06-15", "when": "Mon 4pm"},
    {"name": "Dan", "org": "", "topic": "Eden Fractal and the fractal ecosystem, the respect game, and how it all ties together",
     "status": "confirmed", "date": "2026-06-18", "when": "Thu 12pm"},
    {"name": "Future Person", "org": "X", "topic": "later", "status": "confirmed",
     "date": "2026-07-30"},  # outside window
    {"name": "Maybe", "org": "Y", "topic": "tbd", "status": "lead", "date": "2026-06-16"},  # not confirmed
]


def test_upcoming_lists_only_dated_confirmed_in_window():
    c = live_casts.upcoming_cast(LEADS, today="2026-06-13", window_days=7)
    assert c.startswith("This week at ZABAL Gamez:")
    assert "Tyler (Magnetiq)" in c
    assert "Dan -" in c            # no org, no "()"
    assert "Future Person" not in c   # outside 7-day window
    assert "Maybe" not in c           # not confirmed
    assert "RSVP on the calendar: luma.com/zao" in c


def test_upcoming_sorted_by_date():
    c = live_casts.upcoming_cast(LEADS, today="2026-06-13", window_days=7)
    assert c.index("Tyler") < c.index("Dan")


def test_upcoming_topic_truncated():
    c = live_casts.upcoming_cast(LEADS, today="2026-06-13", window_days=7)
    assert "..." in c  # Dan's long topic truncated


def test_upcoming_uses_date_when_no_when_field():
    leads = [{"name": "Solo", "org": "", "topic": "x", "status": "confirmed", "date": "2026-06-14"}]
    c = live_casts.upcoming_cast(leads, today="2026-06-13", window_days=7)
    assert "2026-06-14" in c


def test_upcoming_empty_when_nothing_dated():
    leads = [{"name": "A", "topic": "x", "status": "confirmed", "when": "any day in June"}]
    assert live_casts.upcoming_cast(leads, today="2026-06-13") == ""


def test_upcoming_bad_today_returns_empty():
    assert live_casts.upcoming_cast(LEADS, today="not-a-date") == ""


def test_no_em_dashes():
    c = live_casts.upcoming_cast(LEADS, today="2026-06-13", window_days=7)
    assert "—" not in c and "–" not in c


def test_static_casts_brand_clean():
    s = live_casts.static_casts()
    assert "zabalgamez.com/speakers" in s["speakers"]
    assert "The build is the application" in s["builder"]
    assert "—" not in s["speakers"] and "—" not in s["builder"]
