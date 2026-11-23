"""Decides what to do with each inbound DM. Writes to the DB only; replies go to the outbox."""
import logging

from .access import Access, AccessError
from .db import Database, now
from .instagram import Incoming

log = logging.getLogger("stash.bot")

HELP = (
    "Send me any reel or post (paper plane → @{username}) and I'll sort it into your Stash.\n"
    "Commands: LIBRARY = link to your saves · HELP = this message"
)
INVITE_ONLY = (
    "Stash is invite-only right now. If you have an invite, open your invite link and send me the "
    "code it shows (it looks like STASH-ABC123). No invite? Reply WAITLIST and we'll let you know."
)


class Bot:
    def __init__(self, db: Database, access: Access, public_base_url: str, ig_username: str, app_path: str = "/library"):
        self.db = db
        self.access = access
        self.base = public_base_url
        self.username = ig_username
        self.app_path = app_path
        self.link_note = " (link works once, for 24 hours)" if app_path == "/app" else ""

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
        if not msg.shares and msg.text.strip().upper() in ("LIBRARY", "LINK", "MY STASH"):
            url = self.library_url(user["id"])
            with self.db.tx() as c:
                self.reply(c, msg.sender, f"Your library{self.link_note}: {url}")
            return "library"
        with self.db.tx() as c:
            if not msg.shares:
                self.reply(c, msg.sender, HELP.format(username=self.username))
                return "help"
            queued, dupes = 0, []
            for s in msg.shares:
                existing = c.execute(
                    "SELECT category FROM saves WHERE user_id = ? AND item_key = ?", (user["id"], s.item_key)
                ).fetchone()
                if existing:
                    dupes.append(existing["category"] or "your Stash")
                    continue
                c.execute(
                    "INSERT INTO saves(user_id, mid, kind, item_key, url, caption, created_at) VALUES (?,?,?,?,?,?,?)",
                    (user["id"], msg.mid, s.kind, s.item_key, s.url, s.caption, now()),
                )
                queued += 1
            if dupes and not queued:
                self.reply(c, msg.sender, f"Already saved in {dupes[0]}.")
                return "already-saved"
        # The worker sends "Saved to <category>" once processing finishes.
        return "queued"
