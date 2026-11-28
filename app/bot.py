"""Decides what to do with each inbound DM. Writes to the DB only; replies go to the outbox."""
import logging
from datetime import datetime, timedelta, timezone

from .access import Access, AccessError
from .commands import Commands, apply, parse, problem_hint, shelf_label, tz_for
from .db import Database, now
from .instagram import Incoming

log = logging.getLogger("stash.bot")

HELP = (
    "Send me any reel or post (paper plane → @{username}) and I'll file it. "
    "Add these in the same message, or right after:\n"
    "#goa-trip → put it on a pile\n"
    "shelf gym → pick the shelf (tech, travel, recipes, gym…)\n"
    "remind sat 7pm → nudge me (tonight, tomorrow, next week, in 3 days, 25 dec)\n"
    "plan tue → plan it for a day\n"
    "done / skip → mark it tried / not for me\n"
    "note: … → keep a note (other text with a reel is kept as a note)\n"
    "find pasta → search your stash · LIBRARY → open the app"
)
RECENT = timedelta(minutes=15)       # follow-up commands apply to a save this fresh
COMMENT = timedelta(minutes=2)        # plain text this soon after a reel is the comment typed with it
INVITE_ONLY = (
    "Stash is invite-only right now. If you have an invite, open your invite link and send me the "
    "code it shows (it looks like STASH-ABC123). No invite? Reply WAITLIST and we'll let you know."
)


class Bot:
    def __init__(self, db: Database, access: Access, public_base_url: str, ig_username: str, app_path: str = "/library",
                 library=None, default_tz: str = "UTC"):
        self.db = db
        self.access = access
        self.base = public_base_url
        self.username = ig_username
        self.app_path = app_path
        self.link_note = " (link works once, for 24 hours)" if app_path == "/app" else ""
        self.library = library
        self.default_tz = default_tz

    def reply(self, c, igsid: str, text: str) -> None:
        c.execute("INSERT INTO outbox(igsid, text, created_at) VALUES (?,?,?)", (igsid, text, now()))

    def library_url(self, user_id: int) -> str:
        """Web app: a single-use sign-in link (24 h). Fallback page: a signed 7-day link."""
        if self.app_path == "/app":
            return f"{self.base}/app/?t={self.access.create_login_link(user_id)}"
        return f"{self.base}{self.app_path}?t={self.access.token_for(user_id)}"

    def handle(self, msg: Incoming) -> str:
        """Returns a short outcome label (used in logs and tests)."""
        if msg.is_echo or not msg.mid or not msg.sender:
            return "ignored"
        with self.db.tx() as c:
            # Meta retries deliveries; handle each message ID once.
            if c.execute("SELECT 1 FROM seen_messages WHERE mid = ?", (msg.mid,)).fetchone():
                return "duplicate-delivery"
            c.execute("INSERT INTO seen_messages(mid, seen_at) VALUES (?,?)", (msg.mid, now()))

        user = self.access.user_for_igsid(msg.sender)
        if user is None:
            return self._handle_stranger(msg)
        # Instagram lets the bot message this person for 24 hours after this (used for reminders).
        with self.db.tx() as c:
            c.execute("UPDATE ig_accounts SET last_message_at = ? WHERE igsid = ?", (now(), msg.sender))
        if user["status"] != "active":
            with self.db.tx() as c:
                self.reply(c, msg.sender, "Your Stash access is turned off. Reach out to the person who invited you.")
            return "revoked"
        return self._handle_member(user, msg)

    # ---------- unknown sender ----------
    def _handle_stranger(self, msg: Incoming) -> str:
        try:
            user = self.access.link_instagram(msg.text, msg.sender)
        except AccessError as e:
            reason = str(e)
            with self.db.tx() as c:
                if reason != "no-code":
                    self.reply(c, msg.sender, reason)
                    return "link-failed"
                if msg.text.strip().upper() == "WAITLIST":
                    c.execute("INSERT OR IGNORE INTO waitlist(igsid, created_at) VALUES (?,?)", (msg.sender, now()))
                    self.reply(c, msg.sender, "You're on the waitlist. We'll message you here when a spot opens.")
                    return "waitlisted"
                # Reels from strangers are not stored.
                self.reply(c, msg.sender, INVITE_ONLY)
                return "invite-only"
        url = self.library_url(user["id"])  # writes to the DB, so not inside the reply transaction
        with self.db.tx() as c:
            self.reply(
                c, msg.sender,
                f"You're in, {user['name']}! Your Instagram is now linked to Stash.\n"
                f"From now on, send me any reel and I'll file it.\nYour library{self.link_note}: {url}",
            )
        return "linked"

    # ---------- linked member ----------
    def _handle_member(self, user: dict, msg: Incoming) -> str:
        text = msg.text.strip()
        if not msg.shares and text.upper() in ("LIBRARY", "LINK", "MY STASH"):
            url = self.library_url(user["id"])
            with self.db.tx() as c:
                self.reply(c, msg.sender, f"Your library{self.link_note}: {url}")
            return "library"

        tz = tz_for(user.get("timezone"), self.default_tz)
        cmds = parse(text, datetime.now(tz)) if text else Commands()
        stamp = now()

        if not msg.shares:
            return self._text_only(user, msg, cmds, tz, stamp)

        with self.db.tx() as c:
            new_ids, dupes = [], []
            for s in msg.shares:
                existing = c.execute("SELECT id, category FROM saves WHERE user_id = ? AND item_key = ?",
                                     (user["id"], s.item_key)).fetchone()
                if existing:
                    dupes.append(existing)
                    continue
                cur = c.execute(
                    "INSERT INTO saves(user_id, mid, kind, item_key, url, caption, created_at) VALUES (?,?,?,?,?,?,?)",
                    (user["id"], msg.mid, s.kind, s.item_key, s.url, s.caption, stamp),
                )
                new_ids.append(cur.lastrowid)
            # Commands apply to the new saves, and also to ones already saved (e.g. re-sent with #pile).
            parts = apply(c, user["id"], new_ids + [d["id"] for d in dupes], cmds, tz, stamp)
            hint = problem_hint(cmds)
            if dupes and not new_ids:
                done = f" Updated: {' · '.join(parts)}." if parts else ""
                self.reply(c, msg.sender, f"Already saved in {shelf_label(dupes[0]['category'])}.{done} {hint}".strip())
                return "already-saved"
            if hint:
                self.reply(c, msg.sender, hint)
        # The worker sends "Saved to <shelf> ✓ · pile … · reminder …" once processing finishes.
        return "queued"

    def _text_only(self, user: dict, msg: Incoming, cmds: Commands, tz, stamp: str) -> str:
        if cmds.help:
            with self.db.tx() as c:
                self.reply(c, msg.sender, HELP.format(username=self.username))
            return "help"
        if cmds.find:
            return self._find(user, msg, cmds.find)

        with self.db.connect() as c:
            latest = c.execute("SELECT id, caption, created_at FROM saves WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                               (user["id"],)).fetchone()
        age = datetime.now(timezone.utc) - datetime.fromisoformat(latest["created_at"]) if latest else None
        only_text = cmds.note and not any([cmds.pile, cmds.shelf, cmds.remind_at, cmds.plan_day, cmds.progress, cmds.problems])

        if only_text and not (age is not None and age <= COMMENT):
            with self.db.tx() as c:          # just chatting: show what Stash understands
                self.reply(c, msg.sender, HELP.format(username=self.username))
            return "help"
        if not (cmds.targets_a_save or cmds.problems):
            with self.db.tx() as c:
                self.reply(c, msg.sender, HELP.format(username=self.username))
            return "help"
        if age is None or age > RECENT:
            with self.db.tx() as c:
                self.reply(c, msg.sender, "Send me a reel first, then add #pile, remind sat, plan tue… in the same message "
                                          "or right after. For older saves, use the app (send LIBRARY).")
            return "no-recent-save"
        with self.db.tx() as c:
            parts = apply(c, user["id"], [latest["id"]], cmds, tz, stamp)
            title = (latest["caption"] or "your last save").split("#")[0].strip()[:50] or "your last save"
            msg_text = f"Got it for “{title}”: {' · '.join(parts)}." if parts else ""
            self.reply(c, msg.sender, f"{msg_text} {problem_hint(cmds)}".strip())
        return "updated"

    def _find(self, user: dict, msg: Incoming, query: str) -> str:
        results = self.library.search(user["id"], query)[:3] if self.library else []
        if not results:
            text = f"Nothing in your stash matches “{query}”. Try one word, or a creator like by:@name."
        else:
            lines = [f"{i}. {(s['caption'] or 'Instagram ' + s['kind']).split('#')[0].strip()[:60]} ({shelf_label(s['category'])})\n{s['url']}"
                     for i, s in enumerate(results, 1)]
            more = "" if len(results) < 3 else "\nMore in the app: send LIBRARY."
            text = f"Found in your stash:\n" + "\n".join(lines) + more
        with self.db.tx() as c:
            self.reply(c, msg.sender, text)
        return "find"
