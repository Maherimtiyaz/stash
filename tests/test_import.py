import io
import json
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings  # noqa: E402
from app.importer import ImportProblem, parse_export  # noqa: E402
from app.instagram import DryRunMessenger  # noqa: E402
from app.main import create_app  # noqa: E402
from scripts.simulate import build  # noqa: E402
from tests.test_api import session_for  # noqa: E402
from tests.test_flow import ALICE, onboard, send  # noqa: E402

T = 1700000000  # 14 Nov 2023


def entry(user, href, ts=T, label="Saved on"):
    return {"title": user, "string_map_data": {label: {"href": href, "timestamp": ts}}}


# Shape of a current (2024–2026) JSON export: "Saved" only, in your_instagram_activity/saved/.
SAVED = {"saved_saved_media": [
    entry("goadiaries", "https://www.instagram.com/reel/C1goaCafe1/"),
    entry("desi.mealprep", "https://www.instagram.com/p/C2paneer22/", T + 60),
    entry("gymwithdev", "https://www.instagram.com/gymwithdev/reel/C3pplSplit/", (T + 120) * 1000),  # ms + username in URL
    entry("randomcat", "https://www.instagram.com/reel/C4catVideo/"),
    entry("goadiaries", "https://www.instagram.com/reel/C1goaCafe1/"),  # listed twice
]}
COLLECTIONS = {"saved_saved_collections": [
    {"title": "Collection", "string_map_data": {"Name": {"value": "Goa trip"}, "Creation Time": {"timestamp": T}}},
    {"string_map_data": {"Name": {"href": "https://www.instagram.com/reel/C1goaCafe1/", "value": "goadiaries"}, "Added Time": {"timestamp": T}}},
    {"string_map_data": {"Name": {"href": "https://www.instagram.com/p/C9onlyInColl/", "value": "travelwithmeera"}, "Added Time": {"timestamp": T}}},
    {"title": "Collection", "string_map_data": {"Name": {"value": "Recipes"}, "Creation Time": {"timestamp": T}}},
    {"string_map_data": {"Name": {"href": "https://www.instagram.com/p/C2paneer22/", "value": "desi.mealprep"}, "Added Time": {"timestamp": T}}},
]}


def export_zip(saved=SAVED, collections=COLLECTIONS, extra=None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("your_instagram_activity/saved/saved_posts.json", json.dumps(saved))
        if collections is not None:
            z.writestr("your_instagram_activity/saved/saved_collections.json", json.dumps(collections))
        z.writestr("media/other/photo.jpg", b"\xff\xd8 not read")
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return buf.getvalue()


# ---------------------------------------------------------------- parsing
def test_parses_current_json_export():
    p = parse_export(export_zip(), "instagram-priya.zip")
    by = {i.code: i for i in p.items}
    assert set(by) == {"C1goaCafe1", "C2paneer22", "C3pplSplit", "C4catVideo", "C9onlyInColl"}
    assert by["C1goaCafe1"].username == "@goadiaries" and by["C1goaCafe1"].kind == "reel"
    assert by["C1goaCafe1"].collections == ["Goa trip"] and by["C2paneer22"].collections == ["Recipes"]
    assert by["C2paneer22"].kind == "post" and by["C2paneer22"].url == "https://www.instagram.com/p/C2paneer22/"
    assert by["C3pplSplit"].saved_at.timestamp() == T + 120          # milliseconds understood
    assert by["C9onlyInColl"].collections == ["Goa trip"]             # only in a collection, still imported
    assert p.collections == ["Goa trip", "Recipes"]
    assert not any("photo.jpg" in f for f in p.files)                 # media ignored


def test_parses_older_json_layout_and_bare_json_file():
    old = {"saved_media": [["goadiaries", {"href": "https://instagram.com/p/OldPost01/", "timestamp": T}]]}
    p = parse_export(json.dumps(old).encode(), "saved_posts.json")
    assert [(i.code, i.username) for i in p.items] == [("OldPost01", "@goadiaries")]


def test_parses_html_export():
    html = ('<html><body><div><div class="_a6-p"><a target="_blank" href="https://www.instagram.com/reel/HtmlReel01/">'
            'goadiaries</a></div><div>Nov 14, 2023 10:13 pm</div></div></body></html>')
    p = parse_export(export_zip(saved={}, collections=None, extra={"saved/saved_posts.html": html}), "x.zip")
    assert [(i.code, i.username, i.kind) for i in p.items] == [("HtmlReel01", "@goadiaries", "reel")]


@pytest.mark.parametrize("data,name,msg", [
    (b"hello", "notes.txt", "isn't valid JSON"),
    (b"PK\x03\x04garbage", "x.zip", "damaged"),
    (json.dumps({"likes": []}).encode(), "saved_posts.json", "doesn't list any saved posts"),
])
def test_clear_errors_for_wrong_files(data, name, msg):
    with pytest.raises(ImportProblem) as e:
        parse_export(data, name)
    assert msg in str(e.value)


def test_zip_without_saved_files():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("your_instagram_activity/likes/liked_posts.json", "{}")
    with pytest.raises(ImportProblem) as e:
        parse_export(buf.getvalue(), "x.zip")
    assert "picked “Saved”" in str(e.value)


def test_zip_bomb_is_refused(monkeypatch):
    monkeypatch.setattr("app.importer.MAX_MEMBER", 1000)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("saved/saved_posts.json", b" " * 100_000)  # compresses to almost nothing
    with pytest.raises(ImportProblem) as e:
        parse_export(buf.getvalue(), "x.zip")
    assert "unexpectedly large" in str(e.value)


# ---------------------------------------------------------------- through the API
@pytest.fixture
def api(tmp_path):
    s = Settings(app_secret="test-app-secret", verify_token="vt", admin_token="admin-xyz",
                 db_path=str(tmp_path / "t.db"), worker_enabled=False, public_base_url="http://test")
    app = create_app(s, DryRunMessenger())
    with TestClient(app) as client:
        _, welcome = onboard(client, app)
        client.headers["Authorization"] = f"Bearer {session_for(client, app, welcome)}"
        yield client, app


def upload(client, data=None, name="instagram-priya.zip"):
    return client.post("/api/v1/import", files={"file": (name, data or export_zip(), "application/zip")})


def test_import_adds_saves_piles_and_shelves(api):
    client, _ = api
    r = upload(client).json()
    assert (r["found"], r["added"], r["duplicates"]) == (5, 5, 0)
    assert r["piles_created"] == ["Goa trip", "Recipes"]
    assert r["shelves"]["Travel"] == 2 and r["shelves"]["Recipes"] == 1 and r["shelves"]["Fitness"] == 1
    assert list(r["shelves"])[-1] == "Unsorted"                       # unsorted listed last
    saves = {s["url"]: s for s in client.get("/api/v1/saves").json()["results"]}
    goa = saves["https://www.instagram.com/reel/C1goaCafe1/"]
    assert (goa["board_name"], goa["category"], goa["creator"], goa["processing"]) == ("Goa trip", "Travel", "@goadiaries", "done")
    assert goa["saved_at"].startswith("2023-11-14")                   # keeps when it was saved on Instagram
    assert {b["name"]: b["count"] for b in client.get("/api/v1/boards").json()} == {"Goa trip": 2, "Recipes": 1}


def test_import_twice_and_existing_saves_are_not_duplicated(api):
    client, app = api
    send(client, build(ALICE, "text", "https://www.instagram.com/reel/C1goaCafe1/"))  # saved earlier via DM
    r = upload(client).json()
    assert (r["added"], r["duplicates"], r["put_on_piles"]) == (4, 1, 1)
    assert upload(client).json()["added"] == 0
    assert len(client.get("/api/v1/saves").json()["results"]) == 5


def test_imported_saves_do_not_trigger_dms(api):
    client, app = api
    app.state.worker.tick()            # send the earlier welcome DM first
    app.state.messenger.sent.clear()
    upload(client)
    app.state.worker.tick()
    assert app.state.messenger.sent == []


def test_undo_removes_saves_and_new_empty_piles_only(api):
    client, _ = api
    keep = client.post("/api/v1/boards", json={"name": "Recipes"}).json()   # existed before the import
    r = upload(client).json()
    assert r["piles_created"] == ["Goa trip"]
    assert client.delete(f"/api/v1/imports/{r['id']}").json() == {"removed": 5, "piles_removed": 1}
    assert client.get("/api/v1/saves").json()["results"] == []
    assert [b["id"] for b in client.get("/api/v1/boards").json()] == [keep["id"]]
    assert client.delete(f"/api/v1/imports/{r['id']}").status_code == 400            # already undone
    assert client.get("/api/v1/imports").json()[0]["undone_at"]


def test_other_members_cannot_undo_my_import(api):
    client, app = api
    r = upload(client).json()
    _, bob = onboard(client, app, name="Bob", sender="1790000000000002")
    bob_auth = {"Authorization": f"Bearer {session_for(client, app, bob)}"}
    assert client.delete(f"/api/v1/imports/{r['id']}", headers=bob_auth).status_code == 404
    assert client.get("/api/v1/imports", headers=bob_auth).json() == []


def test_api_errors_and_limits(api):
    client, _ = api
    bad = upload(client, b"just text", "notes.txt")
    assert bad.status_code == 400 and "valid JSON" in bad.json()["detail"]
    too_big = client.post("/api/v1/import", content=b"x", headers={"Content-Length": str(61 * 1024 * 1024)})
    assert too_big.status_code == 413
    assert client.post("/api/v1/import", files={"file": ("x.zip", export_zip(), "application/zip")},
                       headers={"Authorization": ""}).status_code == 401
    codes = [upload(client).status_code for _ in range(6)]
    assert 429 in codes
