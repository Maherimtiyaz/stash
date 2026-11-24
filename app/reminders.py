"""Reminders: when a save's remind_at passes, tell the member through the best channel available.

Order: Instagram DM (only allowed within 24 h of the member's last message to @stash), then phone/browser
push, then email. The first channel that works wins. Every channel has a dry-run version for local
development and tests, so nothing is sent until real credentials are configured.
"""
import json
import logging
import re
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from .access import Access
from .categories import UNSORTED
from .db import Database, now

log = logging.getLogger("stash.reminders")
DM_WINDOW = timedelta(hours=23)   # Instagram's limit is 24 h; keep a margin
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def parse_when(value: str | None) -> datetime | None:
    """ISO date-times from the app or older rows; naive values are treated as UTC."""
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- email
class Mailer:
    configured = False

    def send(self, to: str, subject: str, text: str) -> None:
        raise NotImplementedError


class DryRunMailer(Mailer):
    def __init__(self):
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, text: str) -> None:
        log.info("DRY-RUN email to %s: %s", to, subject)
        self.sent.append((to, subject, text))


class SmtpMailer(Mailer):
    configured = True

    def __init__(self, host: str, port: int, user: str, password: str, sender: str, starttls: bool = True):
        self.host, self.port, self.user, self.password, self.sender, self.starttls = host, port, user, password, sender, starttls

    def send(self, to: str, subject: str, text: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(text)
        with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
            if self.starttls:
                smtp.starttls()
            if self.user:
                smtp.login(self.user, self.password)
            smtp.send_message(msg)


# ---------------------------------------------------------------- web push
class PushGone(Exception):
    """The browser unsubscribed; forget this subscription."""


class Pusher:
    configured = False

    def send(self, sub: dict, payload: dict) -> None:
        raise NotImplementedError


class DryRunPusher(Pusher):
    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    def send(self, sub: dict, payload: dict) -> None:
        log.info("DRY-RUN push to %s…: %s", sub["endpoint"][:40], payload.get("title"))
        self.sent.append((sub["endpoint"], payload))


class WebPusher(Pusher):
    configured = True

    def __init__(self, private_key: str, subject: str):
        self.private_key, self.subject = private_key, subject

    def send(self, sub: dict, payload: dict) -> None:
        from pywebpush import WebPushException, webpush
        try:
            webpush(
                subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=json.dumps(payload), vapid_private_key=self.private_key,
                vapid_claims={"sub": self.subject}, ttl=24 * 3600, timeout=10,
            )
        except WebPushException as e:
            if e.response is not None and e.response.status_code in (404, 410):
                raise PushGone() from e
            raise


# ---------------------------------------------------------------- the reminder service
@dataclass
class Result:
    channel: str | None   # dm | push | email | None
    tried: dict[str, str]  # channel -> what happened


class Reminders:
    def __init__(self, db: Database, access: Access, mailer: Mailer, pusher: Pusher, base_url: str, has_app: bool):
        self.db, self.access, self.mailer, self.pusher = db, access, mailer, pusher
        self.base, self.has_app = base_url, has_app
        self.public_key = ""  # VAPID public key the browser needs to subscribe

    # ---- what a member has set up
    def channels(self, user_id: int) -> dict:
        with self.db.connect() as c:
            u = c.execute("SELECT u.email, a.last_message_at FROM users u LEFT JOIN ig_accounts a ON a.user_id = u.id "
                          "WHERE u.id = ?", (user_id,)).fetchone()
            devices = c.execute("SELECT COUNT(*) FROM push_subscriptions WHERE user_id = ?", (user_id,)).fetchone()[0]
        last = parse_when(u["last_message_at"]) if u else None
        until = last + DM_WINDOW if last else None
        return {
            "dm": {"open": bool(until and until > datetime.now(timezone.utc)), "until": until.isoformat() if until else None},
            "push": {"devices": devices, "public_key": self.public_key, "live": self.pusher.configured},
            "email": {"address": (u["email"] if u else "") or "", "live": self.mailer.configured},
        }

    def set_email(self, user_id: int, email: str) -> str:
        email = (email or "").strip()
        if email and (len(email) > 120 or not EMAIL_RE.match(email)):
            raise ValueError("That email address doesn't look right.")
        with self.db.tx() as c:
            c.execute("UPDATE users SET email = ? WHERE id = ?", (email, user_id))
        return email

    def subscribe(self, user_id: int, sub: dict) -> None:
        endpoint = str(sub.get("endpoint", ""))
        keys = sub.get("keys") or {}
        if not endpoint.startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
            raise ValueError("That isn't a valid push subscription.")
        with self.db.tx() as c:
            c.execute("INSERT OR REPLACE INTO push_subscriptions(endpoint, user_id, p256dh, auth, created_at) VALUES (?,?,?,?,?)",
                      (endpoint, user_id, keys["p256dh"], keys["auth"], now()))

    def unsubscribe(self, user_id: int, endpoint: str) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?", (user_id, endpoint))

    def upcoming(self, user_id: int) -> list[dict]:
        with self.db.connect() as c:
            rows = c.execute("SELECT id, caption, category, remind_at FROM saves WHERE user_id = ? AND remind_at IS NOT NULL "
                             "AND reminded_at IS NULL ORDER BY remind_at", (user_id,)).fetchall()
        return [dict(r) for r in rows]

    # ---- sending
    def _message(self, save: dict | None) -> tuple[str, str]:
        if save is None:
            return "Test reminder from Stash", "This is a test. Reminders for your saves will arrive like this."
        caption = re.sub(r"\s*#\w+", "", save["caption"] or "").strip() or "a save"
        title = caption if len(caption) <= 70 else caption[:67] + "…"
        shelf = save["category"] if save["category"] and save["category"] != UNSORTED else ""
        return f"Reminder: {title}", f"You asked Stash to remind you about this{f' ({shelf})' if shelf else ''}."

    def _app_link(self, user_id: int, save_id: int | None, sign_in: bool) -> str:
        if not self.has_app:
            return f"{self.base}/library?t={self.access.token_for(user_id)}"
        params = []
        if sign_in:
            params.append(f"t={self.access.create_login_link(user_id)}")
        if save_id:
            params.append(f"open={save_id}")
        return f"{self.base}/app/" + (f"?{'&'.join(params)}" if params else "")

    def deliver(self, user_id: int, save: dict | None, every_channel: bool = False) -> Result:
        """Send through the first working channel, or every channel when testing."""
        title, body = self._message(save)
        save_id = save["id"] if save else None
        ch = self.channels(user_id)
        tried: dict[str, str] = {}
        sent: str | None = None

        # 1. Instagram DM, only inside the 24 h window
        if not ch["dm"]["open"]:
            tried["dm"] = "not available: Instagram only allows it within 24 hours of your last message to @stash"
        else:
            with self.db.connect() as c:
                igsid = c.execute("SELECT igsid FROM ig_accounts WHERE user_id = ?", (user_id,)).fetchone()["igsid"]
            link = self._app_link(user_id, save_id, sign_in=True)
            with self.db.tx() as c:
                c.execute("INSERT INTO outbox(igsid, text, created_at) VALUES (?,?,?)", (igsid, f"⏰ {title}\n{body}\n{link}", now()))
            tried["dm"] = "sent"
            sent = "dm"

        # 2. Push to every subscribed device
        if sent and not every_channel:
            pass
        elif not ch["push"]["devices"]:
            tried["push"] = "off: no device has notifications turned on"
        else:
            with self.db.connect() as c:
                subs = [dict(r) for r in c.execute("SELECT * FROM push_subscriptions WHERE user_id = ?", (user_id,))]
            payload = {"title": title, "body": body, "url": self._app_link(user_id, save_id, sign_in=False), "tag": f"save-{save_id or 'test'}"}
            ok = 0
            for sub in subs:
                try:
                    self.pusher.send(sub, payload)
                    ok += 1
                except PushGone:
                    self.unsubscribe(user_id, sub["endpoint"])
                except Exception as e:  # noqa: BLE001 - one bad device must not stop the others
                    log.warning("push to %s failed: %s", sub["endpoint"][:40], e)
                    with self.db.tx() as c:
                        c.execute("UPDATE push_subscriptions SET last_error = ? WHERE endpoint = ?", (str(e)[:200], sub["endpoint"]))
            tried["push"] = f"sent to {ok} device{'s' if ok != 1 else ''}" if ok else "failed on every device"
            if ok and not sent:
                sent = "push"

        # 3. Email
        if sent and not every_channel:
            pass
        elif not ch["email"]["address"]:
            tried["email"] = "off: no email address saved"
        else:
            link = self._app_link(user_id, save_id, sign_in=True)
            text = f"{body}\n\nOpen it in Stash (this link works once, for 24 hours):\n{link}\n\nYou can change reminders in the app."
            try:
                self.mailer.send(ch["email"]["address"], title, text)
                tried["email"] = "sent"
                sent = sent or "email"
            except Exception as e:  # noqa: BLE001
                log.warning("email to user %s failed: %s", user_id, e)
                tried["email"] = "failed: the email server refused it"
        return Result(sent, tried)

    def process_due(self, limit: int = 50) -> int:
        """Called by the worker. Sends reminders whose time has come; each goes out once."""
        t = datetime.now(timezone.utc)
        with self.db.connect() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT s.id, s.user_id, s.caption, s.category, s.remind_at, s.progress FROM saves s JOIN users u ON u.id = s.user_id "
                "WHERE s.remind_at IS NOT NULL AND s.reminded_at IS NULL AND u.status = 'active' ORDER BY s.remind_at LIMIT ?",
                (limit * 4,))]
        due = [r for r in rows if (w := parse_when(r["remind_at"])) and w <= t][:limit]
        for r in due:
            if r["progress"] == "done":  # already tried it: no need to nag
                with self.db.tx() as c:
                    c.execute("UPDATE saves SET reminded_at = ?, remind_channel = 'skipped' WHERE id = ?", (now(), r["id"]))
                continue
            try:
                res = self.deliver(r["user_id"], r)
            except Exception:  # noqa: BLE001
                log.exception("reminder for save %s failed", r["id"])
                res = Result(None, {})
            with self.db.tx() as c:
                c.execute("UPDATE saves SET reminded_at = ?, remind_channel = ? WHERE id = ?", (now(), res.channel or "failed", r["id"]))
        return len(due)
