"""Commands people type in Instagram DMs to @stash, with or right after a reel.

    #goa-trip              put it on the pile "Goa trip" (made if it doesn't exist)
    shelf gym              put it on a shelf (also: shelf:tech, in recipes)
    remind sat             remind me (tonight, tomorrow, sat 7pm, next week, in 3 days, 25 dec…)
    plan tue               plan it for a day
    done / skip            mark it tried / not for me
    note: 3rd café         keep a note (any other text sent with a reel is kept as a note too)
    find pasta             search my stash (on its own)

Plain keyword rules, no AI. Times are read in the member's own time zone.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .categories import normalise as shelf_for

DAYS = {"mon": 0, "monday": 0, "tue": 1, "tues": 1, "tuesday": 1, "wed": 2, "weds": 2, "wednesday": 2,
        "thu": 3, "thur": 3, "thurs": 3, "thursday": 3, "fri": 4, "friday": 4, "sat": 5, "saturday": 5,
        "sun": 6, "sunday": 6}
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
UNITS = {"min": "minutes", "mins": "minutes", "minute": "minutes", "minutes": "minutes", "m": "minutes",
         "h": "hours", "hr": "hours", "hrs": "hours", "hour": "hours", "hours": "hours",
         "d": "days", "day": "days", "days": "days", "w": "weeks", "wk": "weeks", "week": "weeks", "weeks": "weeks"}
DONE = {"done", "tried", "tried it", "did it", "made it", "cooked it", "✅"}
SKIP = {"skip", "nope", "not for me", "nah"}
DEFAULT_HOUR = 10   # "remind sat" → Saturday 10:00
TONIGHT_HOUR = 20

# A "when" phrase: day words, dates, relative times and clock times, in any order.
_TIME = r"(?:\bat\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)|(?:\bat\s+)?\d{1,2}:\d{2}|\bat\s+\d{1,2}"
_DAY = (r"tonight|today|tomorrow|tmrw|tmr|this\s+weekend|weekend|next\s+week|"
        r"(?:next\s+|this\s+)?(?:" + "|".join(sorted(DAYS, key=len, reverse=True)) + r")\b|"
        r"in\s+\d{1,3}\s*(?:" + "|".join(sorted(UNITS, key=len, reverse=True)) + r")\b|"
        r"\d{1,2}(?:st|nd|rd|th)?\s+(?:" + "|".join(MONTHS) + r")[a-z]*|"
        r"(?:" + "|".join(MONTHS) + r")[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?|\d{1,2}/\d{1,2}")
WHEN = rf"(?:(?:{_DAY})(?:\s+(?:{_TIME}))?|(?:{_TIME})(?:\s+(?:{_DAY}))?)"


@dataclass
class Commands:
    pile: str | None = None           # pile name as typed (#goa-trip → "goa trip")
    shelf: str | None = None          # a category name
    remind_at: datetime | None = None
    plan_day: date | None = None
    progress: str | None = None       # done | skip
    note: str = ""
    find: str | None = None
    help: bool = False
    problems: list[str] = field(default_factory=list)

    @property
    def targets_a_save(self) -> bool:
        return any([self.pile, self.shelf, self.remind_at, self.plan_day, self.progress, self.note])


def parse_when(phrase: str, now: datetime) -> datetime | None:
    """A phrase like 'sat 7pm', 'tomorrow', 'in 3 days', '25 dec' → an aware datetime in now's time zone."""
    p = re.sub(r"\s+", " ", phrase.lower().strip())
    tz = now.tzinfo
    day: date | None = None
    hour, minute = None, 0
    relative: timedelta | None = None

    # "at" only as a whole word: the "at" inside "sat" must not count.
    if m := re.search(r"(?:\bat\s+)?\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b|(?:\bat\s+)?\b(\d{1,2}):(\d{2})\b|\bat\s+(\d{1,2})\b", p):
        if m.group(1):
            hour, minute = int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0), int(m.group(2) or 0)
        elif m.group(4):
            hour, minute = int(m.group(4)), int(m.group(5))
        else:
            hour = int(m.group(6))
            hour += 12 if hour < 8 else 0          # "at 7" usually means the evening
        if hour > 23 or minute > 59:
            return None
        p = (p[:m.start()] + p[m.end():]).strip()

    today = now.date()
    if p in ("", "today"):
        day = today
    elif p == "tonight":
        day, hour = today, hour if hour is not None else TONIGHT_HOUR
    elif p in ("tomorrow", "tmrw", "tmr"):
        day = today + timedelta(days=1)
    elif p in ("weekend", "this weekend"):
        day = today + timedelta(days=(5 - today.weekday()) % 7)
    elif p == "next week":
        day = today + timedelta(days=7 - today.weekday())
    elif m := re.fullmatch(r"(next |this )?([a-z]+)", p):
        if m.group(2) not in DAYS:
            return None
        ahead = (DAYS[m.group(2)] - today.weekday()) % 7
        if m.group(1) == "next " and ahead == 0:
            ahead = 7
        day = today + timedelta(days=ahead)
    elif m := re.fullmatch(r"in (\d{1,3}) ?([a-z]+)", p):
        unit = UNITS.get(m.group(2))
        if not unit:
            return None
        relative = timedelta(**{unit: int(m.group(1))})
    elif m := re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)? ([a-z]{3})[a-z]*|([a-z]{3})[a-z]* (\d{1,2})(?:st|nd|rd|th)?|(\d{1,2})/(\d{1,2})", p):
        if m.group(1):
            d, mon = int(m.group(1)), MONTHS.get(m.group(2))
        elif m.group(3):
            d, mon = int(m.group(4)), MONTHS.get(m.group(3))
        else:
            d, mon = int(m.group(5)), int(m.group(6))   # day/month, as written in India and most places
        if not mon:
            return None
        try:
            day = date(today.year, mon, d)
        except ValueError:
            return None
        if day < today:
            day = date(today.year + 1, mon, d)
    else:
        return None

    if relative is not None:
        return (now + relative).replace(second=0, microsecond=0)
    if hour is None:
        hour = DEFAULT_HOUR
    when = datetime.combine(day, time(hour, minute), tz)
    if when <= now:
        # "remind sat" on Saturday afternoon, or "7pm" after 7pm: the next one, not the past.
        when += timedelta(days=7 if p in DAYS or (p.startswith(("this ", "next ")) and p.split()[-1] in DAYS) else 1)
    return when


def parse(text: str, now: datetime) -> Commands:
    c = Commands()
    t = (text or "").strip()
    low = t.lower()
    if low in ("help", "commands", "?", "how", "how does this work"):
        c.help = True
        return c
    if m := re.match(r"^(?:find|search|look for)\s+(.+)$", t, re.I):
        c.find = m.group(1).strip()[:100]
        return c

    # #pile (the member's own tag, not a reel caption)
    if m := re.search(r"(?<![\w&])#([A-Za-z][^\s#]{0,39})", t):
        c.pile = re.sub(r"[-_]+", " ", m.group(1)).strip()
        t = (t[:m.start()] + t[m.end():]).strip()

    # shelf gym / shelf:tech / in recipes (only when the word is a real shelf)
    for m in re.finditer(r"\b(?:shelf|in)\s*:?\s*([a-z][a-z &]{1,20}?)(?=$|[\s,.;!])", t, re.I):
        if shelf := shelf_for(m.group(1).strip()):
            c.shelf = shelf
            t = (t[:m.start()] + t[m.end():]).strip()
            break

    # remind <when>. "remind" alone, or "remind me to/about …", means tomorrow;
    # "remind <a word that isn't a time>" is reported, not guessed.
    if m := re.search(rf"\bremind(?:\s+me)?(?:\s+(?:on|at))?(?:\s+(?P<when>{WHEN}))?", t, re.I):
        after = t[m.end():].strip()
        end = m.end()
        if m.group("when"):
            when = parse_when(m.group("when"), now)
        elif not after or re.match(r"(?:me\s+)?(?:to|about|that)\b", after, re.I):
            when = parse_when("tomorrow", now)
        else:
            when = None
            end = m.end() + (len(t[m.end():]) - len(t[m.end():].lstrip())) + len(after.split()[0])  # drop the unreadable word
        if when:
            c.remind_at = when
        else:
            c.problems.append("remind")
        t = (t[:m.start()] + t[end:]).strip()

    # plan <day>
    if m := re.search(rf"\bplan(?:\s+it)?(?:\s+(?:for|on))?\s+(?P<when>{WHEN})", t, re.I):
        when = parse_when(m.group("when"), now)
        if when:
            c.plan_day = when.date()
        else:
            c.problems.append("plan")
        t = (t[:m.start()] + t[m.end():]).strip()
    elif m := re.match(r"^plan(?:\s+it)?(?:\s+(?:for|on))?\s+\S+", t, re.I):
        c.problems.append("plan")             # clearly a command, but the day wasn't readable
        t = t[m.end():].strip()

    rest = re.sub(r"\s+", " ", t).strip(" ,.;-")
    if rest.lower() in DONE:
        c.progress = "done"
    elif rest.lower() in SKIP:
        c.progress = "skip"
    elif rest:
        c.note = re.sub(r"^note\s*:?\s*", "", rest, flags=re.I).strip()[:500]
    return c


def tz_for(name: str | None, default: str = "UTC") -> ZoneInfo:
    for candidate in (name, default, "UTC"):
        try:
            if candidate:
                return ZoneInfo(candidate)
        except Exception:  # noqa: BLE001 - unknown or malformed zone name
            continue
    return ZoneInfo("UTC")


def when_label(dt: datetime, tz: ZoneInfo) -> str:
    """'Sat 28 Nov, 10:00' in the member's time zone."""
    return dt.astimezone(tz).strftime("%a %-d %b, %H:%M")


def day_label(d: date) -> str:
    return d.strftime("%a %-d %b")


# ---------------------------------------------------------------- applying commands to saves
LABELS = {"Fitness": "Gym & Fitness"}


def shelf_label(category: str | None) -> str:
    return LABELS.get(category or "", category or "Unsorted")


def _squash(s: str) -> str:
    return re.sub(r"[\s_-]+", "", s.lower())


def pile_id(c, user_id: int, tag: str, created_at: str) -> tuple[int, str, bool]:
    """Find a pile matching the tag (#goatrip, #goa-trip and 'Goa trip' are the same) or make one."""
    for row in c.execute("SELECT id, name FROM boards WHERE user_id = ?", (user_id,)):
        if _squash(row["name"]) == _squash(tag):
            return row["id"], row["name"], False
    name = tag.strip()[:40]
    name = name[:1].upper() + name[1:]
    bid = c.execute("INSERT INTO boards(user_id, name, created_at) VALUES (?,?,?)", (user_id, name, created_at)).lastrowid
    return bid, name, True


def apply(c, user_id: int, save_ids: list[int], cmds: Commands, tz, stamp: str) -> list[str]:
    """Write the commands onto the saves (inside the caller's transaction). Returns what changed, for the reply."""
    if not save_ids:
        return []
    marks = ",".join("?" * len(save_ids))
    parts: list[str] = []

    def update(sql: str, *args):
        c.execute(f"UPDATE saves SET {sql} WHERE user_id = ? AND id IN ({marks})", (*args, user_id, *save_ids))

    if cmds.pile:
        bid, name, made = pile_id(c, user_id, cmds.pile, stamp)
        update("board_id = ?", bid)
        parts.append(f"{'new ' if made else ''}pile “{name}”")
    if cmds.shelf:
        update("category = ?", cmds.shelf)
        parts.append(f"shelf {shelf_label(cmds.shelf)}")
    if cmds.remind_at:
        utc = cmds.remind_at.astimezone(ZoneInfo("UTC")).isoformat(timespec="seconds")
        update("remind_at = ?, reminded_at = NULL, remind_channel = NULL", utc)
        parts.append(f"reminder {when_label(cmds.remind_at, tz)}")
    if cmds.plan_day:
        update("plan_day = ?", cmds.plan_day.isoformat())
        parts.append(f"planned for {day_label(cmds.plan_day)}")
    if cmds.progress:
        update("progress = ?", cmds.progress)
        parts.append("marked tried ✓" if cmds.progress == "done" else "marked not for me")
    if cmds.note:
        update("note = CASE WHEN note = '' THEN ? ELSE note || char(10) || ? END", cmds.note, cmds.note)
        parts.append("note saved")
    return parts


def problem_hint(cmds: Commands) -> str:
    bits = {"remind": "remind sat 7pm, remind tomorrow, remind in 3 days",
            "plan": "plan tue, plan tomorrow, plan 25 dec"}
    return " ".join(f"I couldn't read that time for “{p}”. Try: {bits[p]}." for p in cmds.problems)
