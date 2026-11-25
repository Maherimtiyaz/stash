"""Calendar things follow the member's clock, not the server's (which runs on UTC)."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings  # noqa: E402
from app.instagram import DryRunMessenger  # noqa: E402
from app.main import create_app  # noqa: E402
from scripts.simulate import build  # noqa: E402
from tests.test_api import session_for  # noqa: E402
from tests.test_flow import ALICE, onboard, send  # noqa: E402


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


@pytest.fixture
def app_at(tmp_path):
    s = Settings(app_secret="test-app-secret", verify_token="vt", admin_token="admin-xyz", db_path=str(tmp_path / "t.db"),
                 worker_enabled=False, public_base_url="http://test", default_timezone="Asia/Kolkata")
    app = create_app(s, DryRunMessenger())
    with TestClient(app) as client:
        _, welcome = onboard(client, app)
        client.headers["Authorization"] = f"Bearer {session_for(client, app, welcome)}"
        send(client, build(ALICE, "reel", "Lemon garlic pasta #recipe"))
        send(client, build(ALICE, "reel", "Hidden cafes in Goa"))
        app.state.worker.tick()

        def at(moment, tz=None):
            app.state.library.clock = lambda: moment
            if tz:
                assert client.patch("/api/v1/me", json={"timezone": tz}).status_code == 200
            return client
        yield at, app


# ---------------------------------------------------------------- Plan: today and the week
def test_just_after_midnight_in_india_is_already_tomorrow(app_at):
    at, _ = app_at
    week = at(utc(2026, 11, 25, 20, 0), "Asia/Kolkata").get("/api/v1/plan").json()  # Thu 26 Nov, 01:30 in India
    assert week["today"] == "2026-11-26" and week["start"] == "2026-11-23"


def test_sunday_night_utc_is_monday_in_india_so_the_week_moves(app_at):
    at, _ = app_at
    week = at(utc(2026, 11, 29, 19, 0), "Asia/Kolkata").get("/api/v1/plan").json()  # Mon 30 Nov, 00:30 in India
    assert week["today"] == "2026-11-30" and week["start"] == "2026-11-30"
    assert at(utc(2026, 11, 29, 19, 0), "UTC").get("/api/v1/plan").json()["start"] == "2026-11-23"  # still Sunday in UTC


def test_california_is_still_yesterday(app_at):
    at, _ = app_at
    week = at(utc(2026, 11, 26, 3, 0), "America/Los_Angeles").get("/api/v1/plan").json()  # Wed 25 Nov, 19:00 there
    assert week["today"] == "2026-11-25"


def test_default_time_zone_until_the_app_reports_one(app_at):
    at, app = app_at
    with app.state.db.tx() as c:
        c.execute("UPDATE users SET timezone = ''")
    assert at(utc(2026, 11, 25, 20, 0)).get("/api/v1/plan").json()["today"] == "2026-11-26"  # DEFAULT_TIMEZONE=Asia/Kolkata


# ---------------------------------------------------------------- On this day
def test_on_this_day_uses_the_members_calendar(app_at):
    at, app = app_at
    with app.state.db.tx() as c:
        # Saved 26 Nov 2025 at 15:30 in India, and 27 Nov 2025 at 00:30 in India (still the 26th in UTC).
        c.execute("UPDATE saves SET created_at = '2025-11-26T10:00:00+00:00' WHERE caption LIKE 'Lemon%'")
        c.execute("UPDATE saves SET created_at = '2025-11-26T19:00:00+00:00' WHERE caption LIKE 'Hidden%'")
    india = at(utc(2026, 11, 26, 12, 0), "Asia/Kolkata").get("/api/v1/home").json()["on_this_day"]
    assert [s["caption"][:5] for s in india] == ["Lemon"]
    in_utc = at(utc(2026, 11, 26, 12, 0), "UTC").get("/api/v1/home").json()["on_this_day"]
    assert sorted(s["caption"][:5] for s in in_utc) == ["Hidde", "Lemon"]


# ---------------------------------------------------------------- Capsule "Later" = Saturday 10:00 on the member's clock
@pytest.mark.parametrize("moment,expected", [
    (utc(2026, 11, 25, 8, 0), "2026-11-28T04:30:00+00:00"),    # Wed → Sat 28, 10:00 India (04:30 UTC), not 10:00 UTC
    (utc(2026, 11, 27, 21, 30), "2026-11-28T04:30:00+00:00"),  # Sat 03:00 in India → later that morning
    (utc(2026, 11, 28, 5, 30), "2026-12-05T04:30:00+00:00"),   # Sat 11:00 in India → next Saturday
])
def test_capsule_later_is_saturday_morning_locally(app_at, moment, expected):
    at, _ = app_at
    client = at(moment, "Asia/Kolkata")
    sid = client.get("/api/v1/saves").json()["results"][0]["id"]
    assert client.post(f"/api/v1/saves/{sid}/review", json={"action": "later"}).json()["remind_at"] == expected


def test_device_time_zone_header_is_used_at_once_and_remembered(app_at):
    at, _ = app_at
    client = at(utc(2026, 11, 25, 20, 0), "UTC")
    week = client.get("/api/v1/plan", headers={"X-Timezone": "Asia/Kolkata"}).json()
    assert week["today"] == "2026-11-26"                                   # used on this very request
    assert client.get("/api/v1/me").json()["timezone"] == "Asia/Kolkata"   # and stored for DMs/reminders
    client.get("/api/v1/plan", headers={"X-Timezone": "Not/AZone"})       # junk is ignored
    assert client.get("/api/v1/me").json()["timezone"] == "Asia/Kolkata"
