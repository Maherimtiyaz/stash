import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS invites (
    code        TEXT PRIMARY KEY,
    note        TEXT NOT NULL DEFAULT '',
    max_uses    INTEGER NOT NULL DEFAULT 1,
    uses        INTEGER NOT NULL DEFAULT 0,
    expires_at  TEXT,
    revoked     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL DEFAULT '',
    invite_code TEXT NOT NULL REFERENCES invites(code),
    status      TEXT NOT NULL DEFAULT 'active',   -- active | revoked
    created_at  TEXT NOT NULL
);
-- One-time code the user DMs to @stash to prove which Instagram account is theirs.
CREATE TABLE IF NOT EXISTS link_codes (
    code        TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    expires_at  TEXT NOT NULL,
    used_at     TEXT
);
-- Instagram-scoped sender ID (IGSID) -> Stash user.
CREATE TABLE IF NOT EXISTS ig_accounts (
    igsid       TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL UNIQUE REFERENCES users(id),
    linked_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS saves (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    mid          TEXT NOT NULL,
    kind         TEXT NOT NULL,               -- reel | post | link
    item_key     TEXT NOT NULL,               -- reel id or normalised URL, for dedupe
    url          TEXT NOT NULL DEFAULT '',
    caption      TEXT NOT NULL DEFAULT '',
    category     TEXT,
    tags         TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'queued',  -- queued | done | failed
    created_at   TEXT NOT NULL,
    processed_at TEXT,
    UNIQUE (user_id, item_key)
);
-- Every inbound message ID we've handled. Meta retries webhooks, so this makes handling idempotent.
CREATE TABLE IF NOT EXISTS seen_messages (
    mid         TEXT PRIMARY KEY,
    seen_at     TEXT NOT NULL
);
-- Replies are queued here and sent by the worker, so the webhook returns fast and sends can retry.
CREATE TABLE IF NOT EXISTS outbox (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    igsid       TEXT NOT NULL,
    text        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending | sent | failed
    attempts    INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT,
    created_at  TEXT NOT NULL
);
-- User-made boards (collections). A save sits on at most one board.
CREATE TABLE IF NOT EXISTS boards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    UNIQUE (user_id, name)
);
CREATE TABLE IF NOT EXISTS waitlist (
    igsid       TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    invited     INTEGER NOT NULL DEFAULT 0
);
"""


# Columns added after the first release. Applied to existing databases on start-up.
SAVE_COLUMNS = {
    "creator": "TEXT NOT NULL DEFAULT ''",
    "progress": "TEXT NOT NULL DEFAULT 'try'",     # try | done | skip (the person's own status)
    "note": "TEXT NOT NULL DEFAULT ''",
    "board_id": "INTEGER REFERENCES boards(id) ON DELETE SET NULL",
    "plan_day": "TEXT",                            # ISO date the person planned it for
    "remind_at": "TEXT",                           # ISO datetime (UTC)
    "reviewed_at": "TEXT",                         # last time it was shown in Rediscover
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str):
        self.path = path
        with self.connect() as c:
            c.executescript(SCHEMA)
            have = {r["name"] for r in c.execute("PRAGMA table_info(saves)")}
            for col, ddl in SAVE_COLUMNS.items():
                if col not in have:
                    c.execute(f"ALTER TABLE saves ADD COLUMN {col} {ddl}")
            c.execute("UPDATE saves SET category = 'Tech' WHERE category = 'Coding'")  # renamed shelf

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def tx(self):
        """A write transaction. BEGIN IMMEDIATE takes the write lock up front."""
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                yield c
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise
