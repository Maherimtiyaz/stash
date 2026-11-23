"""Invite-only access: invites → users → Instagram account links."""
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

from .db import Database, now

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O/1/I, easy to read and type
LINK_CODE_RE = re.compile(r"\bSTASH-([A-Z2-9]{6})\b", re.I)


def _code(n: int) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


class AccessError(Exception):
    """User-facing reason an invite or link code can't be used."""


class Access:
    def __init__(self, db: Database, secret_key: str, link_code_minutes: int = 30):
        self.db = db
        self.secret = secret_key.encode()
        self.link_minutes = link_code_minutes

    # ---------- invites (admin) ----------
    def create_invite(self, note: str = "", max_uses: int = 1, expires_in_days: int | None = 14) -> dict:
        code = _code(8)
        expires = None
        if expires_in_days:
            expires = (datetime.now(timezone.utc) + timedelta(days=expires_in_days)).isoformat(timespec="seconds")
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO invites(code, note, max_uses, expires_at, created_at) VALUES (?,?,?,?,?)",
                (code, note, max(1, max_uses), expires, now()),
            )
        return self.get_invite(code)

    def get_invite(self, code: str) -> dict | None:
        with self.db.connect() as c:
            row = c.execute("SELECT * FROM invites WHERE code = ?", (code.upper(),)).fetchone()
        return dict(row) if row else None

    def list_invites(self) -> list[dict]:
        with self.db.connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM invites ORDER BY created_at DESC")]

    def revoke_invite(self, code: str) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE invites SET revoked = 1 WHERE code = ?", (code.upper(),))

    @staticmethod
    def invite_problem(inv: dict | None) -> str | None:
        if not inv:
            return "This invite link doesn't exist. Check the link or ask for a new one."
        if inv["revoked"]:
            return "This invite was cancelled. Ask the person who sent it for a new one."
        if inv["expires_at"] and inv["expires_at"] < now():
            return "This invite has expired. Ask for a new one."
        if inv["uses"] >= inv["max_uses"]:
            return "This invite has already been used. Ask for a new one."
        return None

    # ---------- users ----------
    def redeem_invite(self, code: str, name: str, email: str = "") -> int:
        """Consume one use of an invite and create the user, atomically."""
        name = name.strip()[:60]
        if not name:
            raise AccessError("Enter your name.")
        with self.db.tx() as c:
            inv = c.execute("SELECT * FROM invites WHERE code = ?", (code.upper(),)).fetchone()
            problem = self.invite_problem(dict(inv) if inv else None)
            if problem:
                raise AccessError(problem)
            c.execute("UPDATE invites SET uses = uses + 1 WHERE code = ?", (inv["code"],))
            cur = c.execute(
                "INSERT INTO users(name, email, invite_code, created_at) VALUES (?,?,?,?)",
                (name, email.strip()[:120], inv["code"], now()),
            )
            return cur.lastrowid

    def get_user(self, user_id: int) -> dict | None:
        with self.db.connect() as c:
            row = c.execute(
                "SELECT u.*, a.igsid FROM users u LEFT JOIN ig_accounts a ON a.user_id = u.id WHERE u.id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_users(self) -> list[dict]:
        with self.db.connect() as c:
            rows = c.execute(
                """SELECT u.*, a.igsid, a.linked_at,
                          (SELECT COUNT(*) FROM saves s WHERE s.user_id = u.id) AS saves
                   FROM users u LEFT JOIN ig_accounts a ON a.user_id = u.id
                   ORDER BY u.created_at DESC"""
            )
            return [dict(r) for r in rows]

    def set_user_status(self, user_id: int, status: str) -> None:
        assert status in ("active", "revoked")
        with self.db.tx() as c:
            c.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))

    def user_for_igsid(self, igsid: str) -> dict | None:
        with self.db.connect() as c:
            row = c.execute(
                "SELECT u.* FROM ig_accounts a JOIN users u ON u.id = a.user_id WHERE a.igsid = ?", (igsid,)
            ).fetchone()
        return dict(row) if row else None

    # ---------- linking an Instagram account ----------
    def current_link_code(self, user_id: int) -> dict:
        """Return an unexpired, unused link code for the user, creating one if needed."""
        with self.db.tx() as c:
            row = c.execute(
                "SELECT * FROM link_codes WHERE user_id = ? AND used_at IS NULL AND expires_at > ? "
                "ORDER BY expires_at DESC LIMIT 1",
                (user_id, now()),
            ).fetchone()
            if row:
                return dict(row)
            code = f"STASH-{_code(6)}"
            exp = (datetime.now(timezone.utc) + timedelta(minutes=self.link_minutes)).isoformat(timespec="seconds")
            c.execute("INSERT INTO link_codes(code, user_id, expires_at) VALUES (?,?,?)", (code, user_id, exp))
            return {"code": code, "user_id": user_id, "expires_at": exp, "used_at": None}

    def link_instagram(self, text: str, igsid: str) -> dict:
        """Find a link code in a DM and attach the sender's IGSID to that user."""
        m = LINK_CODE_RE.search(text or "")
        if not m:
            raise AccessError("no-code")
        code = f"STASH-{m.group(1).upper()}"
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM link_codes WHERE code = ?", (code,)).fetchone()
            if not row or row["used_at"]:
                raise AccessError("That code isn't valid. Open your invite page again to get a fresh one.")
            if row["expires_at"] < now():
                raise AccessError("That code has expired. Open your invite page again to get a fresh one.")
            user = c.execute("SELECT * FROM users WHERE id = ?", (row["user_id"],)).fetchone()
            if user["status"] != "active":
                raise AccessError("This Stash account is turned off.")
            taken = c.execute("SELECT user_id FROM ig_accounts WHERE igsid = ?", (igsid,)).fetchone()
            if taken and taken["user_id"] != user["id"]:
                raise AccessError("This Instagram account is already linked to another Stash account.")
            c.execute("UPDATE link_codes SET used_at = ? WHERE code = ?", (now(), code))
            # Re-linking replaces the user's previous Instagram account.
            c.execute("DELETE FROM ig_accounts WHERE user_id = ?", (user["id"],))
            c.execute("INSERT INTO ig_accounts(igsid, user_id, linked_at) VALUES (?,?,?)", (igsid, user["id"], now()))
            return dict(user)

    # ---------- signed links for the invite/welcome pages ----------
    WELCOME_LINK_DAYS = 7

    def _sign(self, payload: str) -> str:
        return hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()[:32]

    def token_for(self, user_id: int, days: int | None = None) -> str:
        """Signed `user.expiry.signature` token for the welcome page. Expires after a week."""
        exp = int((datetime.now(timezone.utc) + timedelta(days=days or self.WELCOME_LINK_DAYS)).timestamp())
        return f"{user_id}.{exp}.{self._sign(f'user:{user_id}:{exp}')}"

    def user_from_token(self, token: str) -> dict | None:
        try:
            uid_s, exp_s, sig = token.split(".", 2)
            uid, exp = int(uid_s), int(exp_s)
        except (ValueError, AttributeError):
            return None
        if not hmac.compare_digest(self._sign(f"user:{uid}:{exp}"), sig):
            return None
        if exp < datetime.now(timezone.utc).timestamp():
            return None
        user = self.get_user(uid)
        return user if user and user["status"] == "active" else None
