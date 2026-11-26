"""Makes instagram-export.zip: a made-up "Download your information" export (Saved only, JSON) with
300 saves from 13 creators and 4 collections, shaped like Instagram's real files. Deterministic.

    python frontend/e2e/fixtures/make_export.py
"""
import io
import json
import random
import zipfile
from pathlib import Path

random.seed(7)
CREATORS = ["goadiaries", "travelwithmeera", "desi.mealprep", "pastapalace", "gymwithdev", "fitwithkabir", "codewithria",
            "techwithtara", "stylebyzara", "homebyanya", "memes.daily", "catsofinsta", "randomfacts"]
COLLECTIONS = {"Goa trip": ["goadiaries", "travelwithmeera"], "Recipes": ["desi.mealprep", "pastapalace"],
               "Gym": ["gymwithdev", "fitwithkabir"], "Tech stuff": ["codewithria", "techwithtara"]}
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"

items = []
for i in range(300):
    code = "C" + "".join(random.choice(LETTERS) for _ in range(10))
    items.append((code, random.choice(CREATORS), random.choice(["reel", "reel", "p"]), int(1640995200 + i * 86400 * 1.7)))

saved = {"saved_saved_media": [
    {"title": who, "string_map_data": {"Saved on": {"href": f"https://www.instagram.com/{kind}/{code}/", "timestamp": ts}}}
    for code, who, kind, ts in items]}
collections = {"saved_saved_collections": []}
for name, members in COLLECTIONS.items():
    collections["saved_saved_collections"].append(
        {"title": "Collection", "string_map_data": {"Name": {"value": name}, "Creation Time": {"timestamp": 1640995200}}})
    for code, who, kind, ts in items:
        if who in members and random.random() < 0.8:
            collections["saved_saved_collections"].append(
                {"string_map_data": {"Name": {"href": f"https://www.instagram.com/{kind}/{code}/", "value": who},
                                     "Added Time": {"timestamp": ts}}})

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    root = "instagram-demo-2026-11-24/"
    for name, data in [("your_instagram_activity/saved/saved_posts.json", json.dumps(saved, indent=2)),
                       ("your_instagram_activity/saved/saved_collections.json", json.dumps(collections, indent=2)),
                       ("start_here.html", "<html>Your information</html>")]:
        info = zipfile.ZipInfo(root + name, date_time=(2026, 11, 24, 0, 0, 0))   # fixed, so the bytes never change
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, data)
(Path(__file__).parent / "instagram-export.zip").write_bytes(buf.getvalue())
print("wrote instagram-export.zip,", len(buf.getvalue()), "bytes")
