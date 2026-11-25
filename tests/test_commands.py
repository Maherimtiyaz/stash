import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.commands import parse, parse_when  # noqa: E402
from app.config import Settings  # noqa: E402
from app.instagram import DryRunMessenger  # noqa: E402
from app.main import create_app  # noqa: E402
from scripts.simulate import build  # noqa: E402
from tests.test_api import session_for  # noqa: E402
from tests.test_flow import ALICE, drain, onboard, send  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 25, 14, 30, tzinfo=IST)   # Wednesday 2:30 pm in India


def at(*a):
    return datetime(*a, tzinfo=IST)


# ---------------------------------------------------------------- the parser
@pytest.mark.parametrize("phrase,expected", [
    ("tonight", at(2026, 11, 25, 20, 0)),
    ("tomorrow", at(2026, 11, 26, 10, 0)),
    ("tomorrow at 7pm", at(2026, 11, 26, 19, 0)),
    ("sat", at(2026, 11, 28, 10, 0)),
    ("saturday 7:30pm", at(2026, 11, 28, 19, 30)),
    ("wed", at(2026, 12, 2, 10, 0)),          # today's 10:00 has passed → next Wednesday
    ("7pm", at(2026, 11, 25, 19, 0)),
    ("at 7", at(2026, 11, 25, 19, 0)),         # "at 7" means the evening
    ("next week", at(2026, 11, 30, 10, 0)),
    ("weekend", at(2026, 11, 28, 10, 0)),
    ("in 3 days", at(2026, 11, 28, 14, 30)),
    ("in 2 hours", at(2026, 11, 25, 16, 30)),
    ("25 dec", at(2026, 12, 25, 10, 0)),
    ("dec 25th", at(2026, 12, 25, 10, 0)),
    ("1/2", at(2027, 2, 1, 10, 0)),            # day/month; already past this year → next year
    ("10 jan", at(2027, 1, 10, 10, 0)),
])
def test_when_phrases(phrase, expected):
    assert parse_when(phrase, NOW) == expected


@pytest.mark.parametrize("phrase", ["blah", "31 feb", "25:00", "in 3 fortnights", "13/13"])
def test_unreadable_times(phrase):
    assert parse_when(phrase, NOW) is None


def test_everything_in_one_message():
    c = parse("#goa-trip remind sat 7pm plan fri shelf travel note: book the 3rd café", NOW)
    assert (c.pile, c.shelf, c.plan_day) == ("goa trip", "Travel", date(2026, 11, 27))
    assert c.remind_at == at(2026, 11, 28, 19, 0) and c.note == "book the 3rd café" and not c.problems


@pytest.mark.parametrize("text,field,value", [
    ("done", "progress", "done"), ("tried it", "progress", "done"), ("not for me", "progress", "skip"),
    ("shelf gym", "shelf", "Fitness"), ("shelf:tech", "shelf", "Tech"), ("in recipes", "shelf", "Recipes"),
    ("this looks amazing", "note", "this looks amazing"), ("note: 2 tbsp only", "note", "2 tbsp only"),
    ("find pasta", "find", "pasta"), ("search goa cafes", "find", "goa cafes"), ("help", "help", True),
])
def test_single_commands(text, field, value):
    assert getattr(parse(text, NOW), field) == value


def test_things_that_are_not_commands():
    assert parse("in goa next month", NOW).shelf is None              # "goa" isn't a shelf
    assert parse("#1 recipe ever", NOW).pile is None                  # tags start with a letter
    c = parse("remind me to buy chillies", NOW)                        # "remind me to …" → tomorrow, rest is a note
    assert c.remind_at == at(2026, 11, 26, 10, 0) and c.note == "to buy chillies"
    c = parse("remind someday", NOW)                                   # not a time: reported, not guessed
    assert c.remind_at is None and c.problems == ["remind"] and c.note == ""
    assert parse("remind", NOW).remind_at == at(2026, 11, 26, 10, 0)


# ---------------------------------------------------------------- through the bot
@pytest.fixture
def chat(tmp_path):
    s = Settings(app_secret="test-app-secret", verify_token="vt", admin_token="admin-xyz", db_path=str(tmp_path / "t.db"),
                 worker_enabled=False, public_base_url="http://test", default_timezone="Asia/Kolkata")
    m = DryRunMessenger()
    app = create_app(s, m)
    with TestClient(app) as client:
        _, welcome = onboard(client, app)
        app.state.worker.tick()
        m.sent.clear()
        auth = {"Authorization": f"Bearer {session_for(client, app, welcome)}"}

        def say(text=None, reel=None):
            if reel is not None:
                p = build(ALICE, "reel", reel)
                if text:
                    p["entry"][0]["messaging"][0]["message"]["text"] = text
            else:
                p = build(ALICE, "text", text)
            outcome = send(client, p).json()["outcomes"][0]
            return outcome, drain(app, m)   # drain runs the worker and returns what it sent

        def saves():
            return client.get("/api/v1/saves", headers=auth).json()["results"]

        yield type("Chat", (), dict(say=staticmethod(say), saves=staticmethod(saves), client=client, app=app, auth=auth))


def test_commands_with_the_reel(chat):
    outcome, replies = chat.say("#goa-trip remind sat plan fri note: 3rd café has the view", reel="Hidden cafes in Goa")
    assert outcome == "queued"
    s = chat.saves()[0]
    assert s["board_name"] == "Goa trip" and s["plan_day"] and s["note"] == "3rd café has the view"
    reply = replies[0]
    assert reply.startswith("Saved to Travel ✓") and "pile “Goa trip”" in reply and "reminder Sat" in reply and "10:00" in reply
    # stored in UTC: 10:00 India = 04:30 UTC
    assert s["remind_at"].endswith("04:30:00+00:00")


def test_follow_up_text_applies_to_the_reel_just_sent(chat):
    chat.say(reel="15 min paneer wrap #recipe")
    outcome, replies = chat.say("#weeknight-food plan tomorrow")
    assert outcome == "updated"
    s = chat.saves()[0]
    assert s["board_name"] == "Weeknight food" and s["plan_day"]
    assert replies[0].startswith("Got it for “15 min paneer wrap”") and "new pile “Weeknight food”" in replies[0]


def test_existing_pile_is_matched_loosely(chat):
    chat.client.post("/api/v1/boards", json={"name": "Goa trip"}, headers=chat.auth)
    chat.say("#goatrip", reel="Scuba at Grande Island")
    assert chat.saves()[0]["board_name"] == "Goa trip"
    assert len(chat.client.get("/api/v1/boards", headers=chat.auth).json()) == 1


def test_shelf_command_beats_the_guess(chat):
    _, replies = chat.say("shelf gym", reel="Paneer protein bowl #recipe")
    assert chat.saves()[0]["category"] == "Fitness" and replies[0].startswith("Saved to Gym & Fitness ✓")


def test_done_and_skip(chat):
    chat.say(reel="Lemon pasta #recipe")
    chat.say("done")
    assert chat.saves()[0]["progress"] == "done"
    chat.say("skip")
    assert chat.saves()[0]["progress"] == "skip"


def test_comment_typed_with_the_reel_becomes_a_note(chat):
    chat.say(reel="Lemon pasta #recipe")
    outcome, _ = chat.say("omg making this sunday")
    assert outcome == "updated" and chat.saves()[0]["note"] == "omg making this sunday"


def test_chatting_later_gets_help_not_a_note(chat):
    chat.say(reel="Lemon pasta #recipe")
    with chat.app.state.db.tx() as c:
        c.execute("UPDATE saves SET created_at = ?", ((datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),))
    outcome, replies = chat.say("hello there")
    assert outcome == "help" and "#goa-trip" in replies[0] and chat.saves()[0]["note"] == ""


def test_commands_without_a_recent_save(chat):
    outcome, replies = chat.say("remind sat")
    assert outcome == "no-recent-save" and "Send me a reel first" in replies[0]


def test_unreadable_time_is_explained(chat):
    chat.say(reel="Lemon pasta #recipe")
    outcome, replies = chat.say("plan someday")
    assert outcome == "updated" and "couldn't read that time" in replies[0] and "plan tue" in replies[0]


def test_resending_a_reel_with_a_pile_updates_it(chat):
    chat.say(reel="Lemon pasta #recipe")
    reel_payload = build(ALICE, "text", "https://www.instagram.com/reel/Cabc123/ #dinners")
    send(chat.client, reel_payload)
    chat.app.state.worker.tick()
    outcome, replies = chat.say("https://www.instagram.com/reel/Cabc123/ #date-night")
    assert outcome == "already-saved" and "Updated: new pile “Date night”" in replies[0]


def test_find_in_dm(chat):
    chat.say(reel="Lemon garlic pasta #recipe")
    chat.say(reel="Hidden cafes in Goa")
    outcome, replies = chat.say("find pasta")
    assert outcome == "find" and "Lemon garlic pasta" in replies[0] and "Goa" not in replies[0]
    _, replies = chat.say("find sushi")
    assert "Nothing in your stash matches “sushi”" in replies[0]


def test_help(chat):
    outcome, replies = chat.say("help")
    assert outcome == "help" and "remind sat 7pm" in replies[0] and "find pasta" in replies[0]


def test_member_time_zone_is_used(chat):
    chat.client.patch("/api/v1/me", json={"timezone": "Europe/London"}, headers=chat.auth)
    chat.say("remind tomorrow", reel="Lemon pasta #recipe")
    assert chat.saves()[0]["remind_at"].endswith("T10:00:00+00:00")   # 10:00 in London (UTC in winter)
    assert chat.client.patch("/api/v1/me", json={"timezone": "Mars/Base"}, headers=chat.auth).status_code == 400
    assert chat.client.get("/api/v1/me", headers=chat.auth).json()["timezone"] == "Europe/London"
