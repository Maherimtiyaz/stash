"""Fill a local database with a demo member, boards and sample saves, then print a sign-in link.

    DB_PATH=demo.db .venv/bin/python scripts/seed_demo.py            # one link
    DB_PATH=demo.db .venv/bin/python scripts/seed_demo.py --links 3  # several (each works once)
    DB_PATH=demo.db .venv/bin/python scripts/seed_demo.py --json     # machine-readable, used by frontend/e2e

Only for local development. The saves are made-up examples.
"""
import json
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
        # As if the member just messaged @stash, so Instagram's 24-hour DM window is open.
        c.execute("INSERT INTO ig_accounts(igsid, user_id, linked_at, last_message_at) VALUES (?,?,?,?)",
                  (f"demo-{uid}", uid, n.isoformat(), n.isoformat()))
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
    n = int(sys.argv[sys.argv.index("--links") + 1]) if "--links" in sys.argv else 1
    links = [f"{base}/app/?t={access.create_login_link(uid)}" for _ in range(n)]
    if "--json" in sys.argv:   # for the browser tests: each test makes its own member
        print(json.dumps({"user_id": uid, "igsid": f"demo-{uid}", "links": links, "saves": len(SAMPLES)}))
        return
    print(f"Demo member 'Priya' created with {len(SAMPLES)} saves. Each link works once, for 24 hours:")
    for link in links:
        print(f"Open: {link}")


if __name__ == "__main__":
    main()
