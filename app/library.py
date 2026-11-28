"""A member's library: saves, boards, search, Rediscover and the week plan.

No AI here. Search is word matching plus filters; Rediscover is "oldest to-try saves you
haven't looked at in 30 days". Every query is scoped to one user_id.
"""
import re
import shlex
from datetime import date, datetime, timedelta, timezone

from .categories import ALL as CATEGORY_NAMES, UNSORTED, normalise as normalise_category
from .commands import parse_when, tz_for
from .db import Database, now

PROGRESS = ("try", "done", "skip")
IS_ALIASES = {"todo": "try", "try": "try", "done": "done", "skip": "skip", "skipped": "skip"}
REVIEW_COOLDOWN_DAYS = 30
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class NotFound(Exception):
    pass


class Invalid(Exception):
    pass


def _row_to_save(r) -> dict:
    return {
        "id": r["id"],
        "kind": r["kind"],
        "url": r["url"],
        "caption": r["caption"],
        "creator": r["creator"],
        "category": r["category"] or ("Processing" if r["status"] == "queued" else "Unsorted"),
        "tags": [t for t in (r["tags"] or "").split(",") if t],
        "progress": r["progress"],
        "note": r["note"],
        "board_id": r["board_id"],
        "board_name": r["board_name"],
        "plan_day": r["plan_day"],
        "remind_at": r["remind_at"],
        "saved_at": r["created_at"],
        "processing": r["status"],
    }


def parse_query(q: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Split a search into free words and filters: in:"Goa trip" by:@someone is:todo."""
    try:
        parts = shlex.split(q or "")
    except ValueError:  # unbalanced quote: fall back to plain splitting
        parts = (q or "").replace('"', " ").split()
    words, filters = [], []
    for p in parts:
        m = re.match(r"^(in|by|is):(.+)$", p, re.I)
        if m:
            filters.append((m.group(1).lower(), m.group(2).strip().lower()))
        else:
            words.append(p.lower())
    return words, filters


class Library:
    def __init__(self, db: Database, default_tz: str = "UTC"):
        self.db = db
        self.default_tz = default_tz
        self.clock = lambda: datetime.now(timezone.utc)   # replaced in tests to check midnight edge cases

    def _local_now(self, tz_name: str | None) -> datetime:
        """'Now' on the member's own clock: Plan's today, On this day and Saturday all use it."""
        return self.clock().astimezone(tz_for(tz_name, self.default_tz))

    SELECT = ("SELECT s.*, b.name AS board_name FROM saves s "
              "LEFT JOIN boards b ON b.id = s.board_id WHERE s.user_id = ?")

    # ------------------------------------------------------------ saves
    def _all(self, user_id: int, extra: str = "", args: tuple = ()) -> list[dict]:
        with self.db.connect() as c:
            rows = c.execute(f"{self.SELECT} {extra}", (user_id, *args)).fetchall()
        return [_row_to_save(r) for r in rows]

    def get(self, user_id: int, save_id: int) -> dict:
        found = self._all(user_id, "AND s.id = ?", (save_id,))
        if not found:
            raise NotFound()
        return found[0]

    def search(self, user_id: int, q: str = "", limit: int = 200) -> list[dict]:
        words, filters = parse_query(q)
        out = []
        for s in self._all(user_id, "ORDER BY s.created_at DESC, s.id DESC"):
            ok = True
            for key, val in filters:
                if key == "in":
                    cat = normalise_category(val)
                    ok = (cat is not None and s["category"] == cat) or val == (s["board_name"] or "").lower()
                elif key == "by":
                    ok = s["creator"].lower().lstrip("@") == val.lstrip("@")
                elif key == "is":
                    ok = s["progress"] == IS_ALIASES.get(val, val)
                if not ok:
                    break
            if not ok:
                continue
            hay = " ".join([s["caption"], s["creator"], s["category"], s["note"],
                            " ".join("#" + t for t in s["tags"]), s["board_name"] or ""]).lower()
            if all(w in hay for w in words):
                out.append(s)
            if len(out) >= limit:
                break
        return out

    def update(self, user_id: int, save_id: int, changes: dict) -> dict:
        self.get(user_id, save_id)  # 404 if not theirs
        sets, args = [], []
        if "progress" in changes:
            if changes["progress"] not in PROGRESS:
                raise Invalid("progress must be try, done or skip")
            sets.append("progress = ?"); args.append(changes["progress"])
        if "category" in changes:
            cat = normalise_category(str(changes["category"] or ""))
            if not cat:
                raise Invalid(f"category must be one of: {', '.join(CATEGORY_NAMES)}")
            sets.append("category = ?"); args.append(cat)
        if "note" in changes:
            note = str(changes["note"] or "")
            if len(note) > 2000:
                raise Invalid("note is too long (2,000 characters max)")
            sets.append("note = ?"); args.append(note)
        if "board_id" in changes:
            bid = changes["board_id"]
            if bid is not None:
                self._board(user_id, int(bid))
            sets.append("board_id = ?"); args.append(bid)
        if "plan_day" in changes:
            d = changes["plan_day"]
            if d is not None and not (isinstance(d, str) and DATE_RE.match(d)):
                raise Invalid("plan_day must be a date like 2026-11-24, or null")
            sets.append("plan_day = ?"); args.append(d)
        if "remind_at" in changes:
            r = changes["remind_at"]
            if r is not None:
                try:
                    when = datetime.fromisoformat(str(r).replace("Z", "+00:00"))
                except ValueError:
                    raise Invalid("remind_at must be an ISO date and time, or null")
                # Stored in UTC; a naive time is taken as UTC.
                r = (when if when.tzinfo else when.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds")
            # A new (or cleared) time means the reminder is due again.
            sets.append("remind_at = ?"); args.append(r)
            sets.append("reminded_at = NULL"); sets.append("remind_channel = NULL")
        if sets:
            with self.db.tx() as c:
                c.execute(f"UPDATE saves SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
                          (*args, save_id, user_id))
        return self.get(user_id, save_id)

    def delete(self, user_id: int, save_id: int) -> None:
        with self.db.tx() as c:
            if not c.execute("DELETE FROM saves WHERE id = ? AND user_id = ?", (save_id, user_id)).rowcount:
                raise NotFound()

    # ------------------------------------------------------------ boards
    def _board(self, user_id: int, board_id: int) -> dict:
        with self.db.connect() as c:
            r = c.execute("SELECT * FROM boards WHERE id = ? AND user_id = ?", (board_id, user_id)).fetchone()
        if not r:
            raise Invalid("that board doesn't exist")
        return dict(r)

    def boards(self, user_id: int) -> list[dict]:
        with self.db.connect() as c:
            rows = c.execute(
                """SELECT b.id, b.name, b.created_at, COUNT(s.id) AS count
                   FROM boards b LEFT JOIN saves s ON s.board_id = b.id
                   WHERE b.user_id = ? GROUP BY b.id ORDER BY b.created_at, b.id""", (user_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def create_board(self, user_id: int, name: str) -> dict:
        name = (name or "").strip()[:40]
        if not name:
            raise Invalid("give the board a name")
        with self.db.tx() as c:
            if c.execute("SELECT 1 FROM boards WHERE user_id = ? AND name = ? COLLATE NOCASE", (user_id, name)).fetchone():
                raise Invalid(f"you already have a board called {name}")
            cur = c.execute("INSERT INTO boards(user_id, name, created_at) VALUES (?,?,?)", (user_id, name, now()))
        return {"id": cur.lastrowid, "name": name, "count": 0}

    def rename_board(self, user_id: int, board_id: int, name: str) -> dict:
        self._board(user_id, board_id)
        name = (name or "").strip()[:40]
        if not name:
            raise Invalid("give the board a name")
        with self.db.tx() as c:
            c.execute("UPDATE boards SET name = ? WHERE id = ? AND user_id = ?", (name, board_id, user_id))
        return next(b for b in self.boards(user_id) if b["id"] == board_id)

    def delete_board(self, user_id: int, board_id: int) -> None:
        self._board(user_id, board_id)
        with self.db.tx() as c:
            c.execute("UPDATE saves SET board_id = NULL WHERE board_id = ? AND user_id = ?", (board_id, user_id))
            c.execute("DELETE FROM boards WHERE id = ? AND user_id = ?", (board_id, user_id))

    # ------------------------------------------------------------ shelves (categories)
    def categories(self, user_id: int) -> list[dict]:
        """Every shelf in display order with how many saves are on it (empty shelves included)."""
        with self.db.connect() as c:
            rows = c.execute(
                "SELECT COALESCE(category, ?) AS cat, COUNT(*) AS n, SUM(progress = 'try') AS todo "
                "FROM saves WHERE user_id = ? GROUP BY cat", (UNSORTED, user_id)
            ).fetchall()
        counts = {r["cat"]: (r["n"], r["todo"] or 0) for r in rows}
        return [{"name": c, "count": counts.get(c, (0, 0))[0], "todo": counts.get(c, (0, 0))[1]} for c in CATEGORY_NAMES]

    # ------------------------------------------------------------ home, rediscover, plan
    def home(self, user_id: int, tz_name: str | None = None) -> dict:
        local = self._local_now(tz_name)
        today, tz = local.date(), local.tzinfo
        saves = self._all(user_id, "ORDER BY s.created_at DESC, s.id DESC")

        def saved_on(s) -> date | None:   # the day it was saved, on the member's calendar
            try:
                d = datetime.fromisoformat(s["saved_at"])
            except ValueError:
                return None
            return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(tz).date()

        on_this_day = [s for s in saves if (d := saved_on(s)) and (d.month, d.day) == (today.month, today.day) and d.year < today.year]
        return {
            "recent": saves[:8],
            "on_this_day": on_this_day[:3],
            "counts": {
                "total": len(saves),
                "todo": sum(s["progress"] == "try" for s in saves),
                "done": sum(s["progress"] == "done" for s in saves),
            },
        }

    def rediscover(self, user_id: int, limit: int = 20) -> list[dict]:
        cutoff = (self.clock() - timedelta(days=REVIEW_COOLDOWN_DAYS)).isoformat(timespec="seconds")
        return self._all(
            user_id,
            "AND s.progress = 'try' AND s.plan_day IS NULL AND s.status = 'done' "
            "AND (s.reviewed_at IS NULL OR s.reviewed_at < ?) ORDER BY s.created_at ASC, s.id ASC LIMIT ?",
            (cutoff, limit),
        )

    def review(self, user_id: int, save_id: int, action: str, remind_at: str | None = None, tz_name: str | None = None) -> dict:
        if action not in ("keep", "let_go", "later"):
            raise Invalid("action must be keep, let_go or later")
        changes: dict = {}
        if action == "let_go":
            changes["progress"] = "skip"
        elif action == "later":
            # "Later" = Saturday 10:00 on the member's clock (today if it's Saturday before 10).
            changes["remind_at"] = remind_at or parse_when("sat", self._local_now(tz_name)).isoformat()
        save = self.update(user_id, save_id, changes)
        with self.db.tx() as c:
            c.execute("UPDATE saves SET reviewed_at = ? WHERE id = ? AND user_id = ?", (now(), save_id, user_id))
        return save

    def plan(self, user_id: int, start: date | None = None, tz_name: str | None = None) -> dict:
        today = self._local_now(tz_name).date()
        start = start or (today - timedelta(days=today.weekday()))
        days = [(start + timedelta(days=i)).isoformat() for i in range(7)]
        planned = self._all(user_id, "AND s.plan_day BETWEEN ? AND ? ORDER BY s.plan_day, s.id", (days[0], days[-1]))
        pile = self._all(user_id, "AND s.progress = 'try' AND s.plan_day IS NULL ORDER BY s.created_at DESC LIMIT 40")
        return {
            "start": days[0],
            "today": today.isoformat(),
            "days": [{"date": d, "saves": [s for s in planned if s["plan_day"] == d]} for d in days],
            "pile": pile,
        }

