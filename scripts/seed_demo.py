"""Fill a local database with a demo member, boards and sample saves, then print a sign-in link.

    DB_PATH=demo.db .venv/bin/python scripts/seed_demo.py

Only for local development. The saves are made-up examples.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.access import Access  # noqa: E402
from app.db import Database  # noqa: E402

SAMPLES = [
    # caption, creator, category, tags, days ago, board, progress, note
    ("Hidden cafés in Assagao, Goa", "@goadiaries", "Travel", "goa,cafe", 365, "Goa trip", "try", "3rd one has the sunset view"),
    ("15-min paneer bhurji wrap", "@desi.mealprep", "Recipes", "recipe,protein", 240, "Weeknight food", "try", ""),
    ("No-equipment core workout", "@fitwithkabir", "Fitness", "workout,abs", 21, None, "try", ""),
    ("Linen outfits for summer", "@stylebyzara", "Fashion", "fashion,linen", 180, "Summer fits", "try", ""),
    ("SQL joins in 60 seconds", "@codewithria", "Tech", "sql,interview", 150, "Job hunt", "done", ""),
    ("Best beach shacks in Palolem", "@travelwithmeera", "Travel", "goa,beach", 120, "Goa trip", "try", ""),
    ("Lemon garlic pasta", "@pastapalace", "Recipes", "pasta,dinner", 370, "Weeknight food", "done", "Add more chilli"),
    ("Scandi bedroom on a budget", "@homebyanya", "Home", "decor,bedroom", 60, "New flat", "try", ""),
    ("3 habits for better sleep", "@drsleepwell", "Health", "sleep,habits", 210, None, "try", ""),
    ("Scuba at Grande Island: what it costs", "@goadiaries", "Travel", "goa,scuba", 62, "Goa trip", "try", "₹3,500 per person"),
    ("System design: URL shortener", "@techinterviewbytes", "Tech", "systemdesign,interview", 125, "Job hunt", "try", "Asked at Flipkart"),
    ("Masala chai the right way", "@desi.mealprep", "Recipes", "chai,recipe", 2, "Weeknight food", "try", ""),
    ("Plants that survive a dark flat", "@greenroomhq", "Home", "plants,decor", 5, "New flat", "try", ""),
    ("White sneakers 5 ways", "@stylebyzara", "Fashion", "sneakers", 400, "Summer fits", "skip", ""),
    ("5 AI tools that save me hours", "@techwithtara", "Tech", "ai,tools", 9, None, "try", ""),
    ("Push-pull-legs split for beginners", "@gymwithdev", "Fitness", "gym,ppl", 33, None, "try", "Start Monday"),
    ("Kerala backwaters on a budget", "@travelwithmeera", "Travel", "kerala,budget", 95, None, "try", ""),
]


def main():
    db = Database(os.environ.get("DB_PATH", "stash.db"))
    access = Access(db, os.environ.get("SECRET_KEY", "dev-secret"))
    inv = access.create_invite("demo seed", 1, 1)
    uid = access.redeem_invite(inv["code"], "Priya")
    n = datetime.now(timezone.utc)
    with db.tx() as c:
        c.execute("INSERT INTO ig_accounts(igsid, user_id, linked_at) VALUES (?,?,?)", (f"demo-{uid}", uid, n.isoformat()))
        boards = {}
        for name in ["Goa trip", "Weeknight food", "New flat", "Summer fits", "Job hunt"]:
            boards[name] = c.execute("INSERT INTO boards(user_id, name, created_at) VALUES (?,?,?)",
                                     (uid, name, n.isoformat())).lastrowid
        for i, (cap, who, cat, tags, ago, board, prog, note) in enumerate(SAMPLES):
            when = n.replace(year=n.year - 1) if ago == 365 else n - timedelta(days=ago)
            c.execute(
                "INSERT INTO saves(user_id, mid, kind, item_key, url, caption, creator, category, tags, status,"
                " progress, note, board_id, created_at, processed_at) VALUES (?,?,?,?,?,?,?,?,?,'done',?,?,?,?,?)",
                (uid, f"seed-{uid}-{i}", "reel", f"seed:{uid}:{i}", "https://www.instagram.com/", cap, who, cat, tags,
                 prog, note, boards.get(board), when.isoformat(timespec="seconds"), when.isoformat(timespec="seconds")),
            )
    base = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    print(f"Demo member 'Priya' created with {len(SAMPLES)} saves.")
    print(f"Open: {base}/app/?t={access.token_for(uid)}")


if __name__ == "__main__":
    main()
