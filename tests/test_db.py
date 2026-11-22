import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_existing_database_is_migrated(tmp_path):
    import sqlite3
    from app.db import Database
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE saves (id INTEGER PRIMARY KEY, user_id INTEGER, mid TEXT, kind TEXT, item_key TEXT,"
                " url TEXT, caption TEXT, category TEXT, tags TEXT, status TEXT, created_at TEXT, processed_at TEXT)")
    con.commit(); con.close()
    Database(str(path))
    cols = {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(saves)")}
    assert {"progress", "note", "board_id", "plan_day", "remind_at", "reviewed_at", "creator"} <= cols


def test_old_coding_shelf_renamed(tmp_path):
    import sqlite3
    from app.db import Database
    path = str(tmp_path / "x.db")
    Database(path)
    con = sqlite3.connect(path)
    con.execute("INSERT INTO saves(user_id, mid, kind, item_key, category, created_at) VALUES (1,'m','reel','k','Coding','2026-01-01')")
    con.commit(); con.close()
    Database(path)
    assert sqlite3.connect(path).execute("SELECT category FROM saves").fetchone()[0] == "Tech"
