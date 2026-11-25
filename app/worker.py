"""Background worker: understands saves and sends queued replies.

The classifier here is keyword rules so the prototype runs with no API keys. In the real
build, `understand()` is where media fetch, speech-to-text, OCR and an LLM call go; the
rest of the pipeline stays the same.
"""
import logging
import threading
import time

from .categories import UNSORTED, guess
from .db import Database, now
from .instagram import Messenger

log = logging.getLogger("stash.worker")

def understand(caption: str, url: str) -> tuple[str, list[str]]:
    tags = [w.lstrip("#") for w in caption.split() if w.startswith("#")][:8]
    return guess(caption, url), tags


class Worker:
    def __init__(self, db: Database, messenger: Messenger, max_send_attempts: int = 5, reminders=None):
        self.db = db
        self.messenger = messenger
        self.reminders = reminders
        self.max_attempts = max_send_attempts
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def process_saves(self, limit: int = 20) -> int:
        with self.db.connect() as c:
            rows = c.execute(
                "SELECT s.*, a.igsid FROM saves s JOIN ig_accounts a ON a.user_id = s.user_id "
                "WHERE s.status = 'queued' ORDER BY s.id LIMIT ?", (limit,)
            ).fetchall()
        for r in rows:
            try:
                category, tags = understand(r["caption"], r["url"])
                with self.db.tx() as c:
                    c.execute(
                        "UPDATE saves SET category = ?, tags = ?, status = 'done', processed_at = ? WHERE id = ?",
                        (category, ",".join(tags), now(), r["id"]),
                    )
                    text = f"Saved to {category} ✓" if category != UNSORTED else "Saved ✓ (couldn't pick a category yet)"
                    c.execute("INSERT INTO outbox(igsid, text, created_at) VALUES (?,?,?)", (r["igsid"], text, now()))
            except Exception:
                log.exception("processing save %s failed", r["id"])
                with self.db.tx() as c:
                    c.execute("UPDATE saves SET status = 'failed' WHERE id = ?", (r["id"],))
        return len(rows)

    def flush_outbox(self, limit: int = 50) -> int:
        with self.db.connect() as c:
            rows = c.execute(
                "SELECT * FROM outbox WHERE status = 'pending' ORDER BY id LIMIT ?", (limit,)
            ).fetchall()
        sent = 0
        for r in rows:
            try:
                self.messenger.send_text(r["igsid"], r["text"])
                status, err = "sent", None
                sent += 1
            except Exception as e:  # network error, expired token, 24h window closed…
                status = "failed" if r["attempts"] + 1 >= self.max_attempts else "pending"
                err = str(e)[:300]
                log.warning("send to %s failed: %s", r["igsid"], err)
            with self.db.tx() as c:
                c.execute(
                    "UPDATE outbox SET status = ?, attempts = attempts + 1, last_error = ? WHERE id = ?",
                    (status, err, r["id"]),
                )
        return sent

    def tick(self) -> None:
        self.process_saves()
        if self.reminders:
            self.reminders.process_due()
        self.flush_outbox()  # after reminders, so reminder DMs go out in the same tick

    def start(self, interval: float = 1.0) -> None:
        def loop():
            while not self._stop.is_set():
                try:
                    self.tick()
                except Exception:
                    log.exception("worker tick failed")
                self._stop.wait(interval)
        self._thread = threading.Thread(target=loop, name="stash-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
