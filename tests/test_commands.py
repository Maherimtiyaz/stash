import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.commands import parse, parse_when  # noqa: E402

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
    c = parse("remind me to buy chillies", NOW)                        # bare remind → tomorrow, rest is a note
    assert c.remind_at == at(2026, 11, 26, 10, 0) and c.note == "to buy chillies"
