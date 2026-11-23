import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings  # noqa: E402
from app.instagram import DryRunMessenger  # noqa: E402
from app.main import create_app  # noqa: E402
from scripts.simulate import build  # noqa: E402
from tests.test_flow import ALICE, onboard, send  # noqa: E402


@pytest.fixture
def api(tmp_path):
    s = Settings(app_secret="test-app-secret", verify_token="vt", admin_token="admin-xyz",
                 db_path=str(tmp_path / "t.db"), worker_enabled=False, public_base_url="http://test")
    app = create_app(s, DryRunMessenger())
    with TestClient(app) as client:
        _, token = onboard(client, app)
        for cap in ["15 min paneer wrap #recipe", "Hidden cafes in Goa #travel", "SQL joins explained #coding"]:
            send(client, build(ALICE, "reel", cap))
        app.state.worker.tick()
        client.headers["Authorization"] = f"Bearer {session_for(client, app, token)}"
        yield client, app


def session_for(client, app, welcome_token: str) -> str:
    """Sign in the way the web app does: a one-time link swapped for a session."""
    link = app.state.access.create_login_link(int(welcome_token.split(".")[0]))
    r = client.post("/api/v1/session", json={"link": link}, headers={"Authorization": ""})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def ids(resp):
    return [s["id"] for s in resp.json()["results"]]


def test_requires_token(api):
    client, _ = api
    assert client.get("/api/v1/me").json()["name"] == "Alice"
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer 1.forged"}).status_code == 401
    assert client.get("/api/v1/saves", headers={"Authorization": ""}).status_code == 401


def test_other_users_cannot_see_my_saves(api):
    client, app = api
    _, bob_token = onboard(client, app, name="Bob", sender="1790000000000002")
    bob = {"Authorization": f"Bearer {session_for(client, app, bob_token)}"}
    assert client.get("/api/v1/saves", headers=bob).json()["results"] == []
    my_id = ids(client.get("/api/v1/saves"))[0]
    assert client.get(f"/api/v1/saves/{my_id}", headers=bob).status_code == 404
    assert client.patch(f"/api/v1/saves/{my_id}", json={"note": "x"}, headers=bob).status_code == 404


def test_search_words_and_filters(api):
    client, _ = api
    assert len(ids(client.get("/api/v1/saves"))) == 3
    goa = client.get("/api/v1/saves", params={"q": "goa"}).json()["results"]
    assert [s["category"] for s in goa] == ["Travel"]
    assert len(ids(client.get("/api/v1/saves", params={"q": "in:Recipes"}))) == 1
    assert len(ids(client.get("/api/v1/saves", params={"q": "#coding"}))) == 1
    assert ids(client.get("/api/v1/saves", params={"q": "is:done"})) == []


def test_update_status_note_board_plan(api):
    client, _ = api
    sid = ids(client.get("/api/v1/saves", params={"q": "goa"}))[0]
    board = client.post("/api/v1/boards", json={"name": "Goa trip"}).json()
    s = client.patch(f"/api/v1/saves/{sid}", json={
        "progress": "done", "note": "3rd cafe has the view", "board_id": board["id"],
        "plan_day": "2026-11-28", "remind_at": "2026-11-28T10:00"}).json()
    assert (s["progress"], s["board_name"], s["plan_day"]) == ("done", "Goa trip", "2026-11-28")
    # Search finds notes and board names, and filters by board.
    assert ids(client.get("/api/v1/saves", params={"q": "view"})) == [sid]
    assert ids(client.get("/api/v1/saves", params={"q": 'in:"Goa trip"'})) == [sid]
    assert client.get("/api/v1/boards").json()[0]["count"] == 1


def test_validation_errors(api):
    client, _ = api
    sid = ids(client.get("/api/v1/saves"))[0]
    assert client.patch(f"/api/v1/saves/{sid}", json={"progress": "maybe"}).status_code == 400
    assert client.patch(f"/api/v1/saves/{sid}", json={"plan_day": "next tuesday"}).status_code == 400
    assert client.patch(f"/api/v1/saves/{sid}", json={"board_id": 999}).status_code == 400
    assert client.patch(f"/api/v1/saves/{sid}", json={"caption": "hack"}).status_code == 400
    assert client.post("/api/v1/boards", json={"name": "  "}).status_code == 400
    client.post("/api/v1/boards", json={"name": "Food"})
    assert client.post("/api/v1/boards", json={"name": "food"}).status_code == 400


def test_delete_board_keeps_saves(api):
    client, _ = api
    sid = ids(client.get("/api/v1/saves"))[0]
    b = client.post("/api/v1/boards", json={"name": "Temp"}).json()
    client.patch(f"/api/v1/saves/{sid}", json={"board_id": b["id"]})
    assert client.delete(f"/api/v1/boards/{b['id']}").status_code == 200
    assert client.get(f"/api/v1/saves/{sid}").json()["board_id"] is None


def test_rediscover_review_flow(api):
    client, _ = api
    deck = client.get("/api/v1/rediscover").json()
    assert len(deck) == 3 and deck[0]["caption"].startswith("15 min")  # oldest first
    client.post(f"/api/v1/saves/{deck[0]['id']}/review", json={"action": "keep"})
    s = client.post(f"/api/v1/saves/{deck[1]['id']}/review", json={"action": "let_go"}).json()
    assert s["progress"] == "skip"
    s = client.post(f"/api/v1/saves/{deck[2]['id']}/review", json={"action": "later"}).json()
    assert s["remind_at"]
    assert client.get("/api/v1/rediscover").json() == []
    assert client.post(f"/api/v1/saves/{deck[0]['id']}/review", json={"action": "nope"}).status_code == 400


def test_plan_week(api):
    client, _ = api
    sid = ids(client.get("/api/v1/saves"))[0]
    client.patch(f"/api/v1/saves/{sid}", json={"plan_day": "2026-11-24"})
    week = client.get("/api/v1/plan", params={"start": "2026-11-23"}).json()
    assert [d["date"] for d in week["days"]][:2] == ["2026-11-23", "2026-11-24"]
    assert [s["id"] for s in week["days"][1]["saves"]] == [sid]
    assert sid not in [s["id"] for s in week["pile"]]
    assert client.get("/api/v1/plan", params={"start": "soon"}).status_code == 400


def test_home_and_delete(api):
    client, app = api
    n = datetime.now(timezone.utc)
    last_year = n.replace(year=n.year - 1, day=28 if (n.month, n.day) == (2, 29) else n.day)
    with app.state.db.tx() as c:  # pretend one save is from exactly a year ago
        c.execute("UPDATE saves SET created_at = ? WHERE id = (SELECT MIN(id) FROM saves)",
                  (last_year.isoformat(timespec="seconds"),))
    h = client.get("/api/v1/home").json()
    assert h["counts"] == {"total": 3, "todo": 3, "done": 0}
    assert len(h["on_this_day"]) == 1
    sid = h["recent"][0]["id"]
    assert client.delete(f"/api/v1/saves/{sid}").status_code == 200
    assert client.get(f"/api/v1/saves/{sid}").status_code == 404


def test_shelves_sorting_and_aliases(api):
    client, app = api
    shelves = {c["name"]: c["count"] for c in client.get("/api/v1/categories").json()}
    assert list(shelves)[:4] == ["Tech", "Travel", "Recipes", "Fitness"]  # display order
    assert (shelves["Recipes"], shelves["Travel"], shelves["Tech"], shelves["Fitness"]) == (1, 1, 1, 0)
    # Friendly words work as filters: "gym" means Fitness, "food" means Recipes, "coding" means Tech.
    assert len(ids(client.get("/api/v1/saves", params={"q": "in:food"}))) == 1
    assert len(ids(client.get("/api/v1/saves", params={"q": "in:coding"}))) == 1
    assert ids(client.get("/api/v1/saves", params={"q": "in:gym"})) == []


def test_move_save_to_another_shelf(api):
    client, _ = api
    sid = ids(client.get("/api/v1/saves", params={"q": "paneer"}))[0]
    assert client.patch(f"/api/v1/saves/{sid}", json={"category": "gym"}).json()["category"] == "Fitness"
    assert ids(client.get("/api/v1/saves", params={"q": "in:Fitness"})) == [sid]
    assert client.patch(f"/api/v1/saves/{sid}", json={"category": "Snacks"}).status_code == 400



def test_sign_in_links_work_once_and_sessions_can_end(api):
    client, app = api
    uid = client.get("/api/v1/me").json()["id"]
    link = app.state.access.create_login_link(uid)
    no_auth = {"Authorization": ""}
    first = client.post("/api/v1/session", json={"link": link}, headers=no_auth)
    assert first.status_code == 200 and first.json()["token"].startswith("s_")
    again = client.post("/api/v1/session", json={"link": link}, headers=no_auth)
    assert again.status_code == 401 and "already used" in again.json()["detail"]
    assert client.post("/api/v1/session", json={"link": "l_guess"}, headers=no_auth).status_code == 401
    me = {"Authorization": f"Bearer {first.json()['token']}"}
    assert client.get("/api/v1/me", headers=me).status_code == 200
    assert client.delete("/api/v1/session", headers=me).status_code == 200
    assert client.get("/api/v1/me", headers=me).status_code == 401   # signed out for real


def test_old_links_and_welcome_tokens_cannot_call_the_api(api):
    client, app = api
    welcome = app.state.access.token_for(client.get("/api/v1/me").json()["id"])
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {welcome}"}).status_code == 401


def test_expired_link_and_turned_off_member(api):
    client, app = api
    access = app.state.access
    uid = client.get("/api/v1/me").json()["id"]
    stale = access.create_login_link(uid)
    with app.state.db.tx() as c:
        c.execute("UPDATE login_links SET expires_at = '2000-01-01T00:00:00+00:00' WHERE token_hash = ?", (access._hash(stale),))
    assert client.post("/api/v1/session", json={"link": stale}, headers={"Authorization": ""}).status_code == 401
    access.set_user_status(uid, "revoked")   # admin turns the member off → existing sessions end
    assert client.get("/api/v1/me").status_code == 401


def test_only_hashes_are_stored(api):
    client, app = api
    link = app.state.access.create_login_link(client.get("/api/v1/me").json()["id"])
    with app.state.db.connect() as c:
        stored = [r[0] for r in c.execute("SELECT token_hash FROM login_links UNION SELECT token_hash FROM sessions")]
    assert link not in stored and all(len(h) == 64 for h in stored)


def test_bot_and_library_page_hand_out_single_use_links(tmp_path):
    from tests.test_flow import drain
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>Stash</title>")
    s = Settings(app_secret="test-app-secret", verify_token="vt", admin_token="admin-xyz", db_path=str(tmp_path / "t.db"),
                 worker_enabled=False, public_base_url="http://test", frontend_dist=str(dist))
    m = DryRunMessenger()
    app = create_app(s, m)
    with TestClient(app) as client:
        _, welcome = onboard(client, app)
        drain(app, m)
        send(client, build(ALICE, "text", "LIBRARY"))
        reply = drain(app, m)[0]
        assert "works once" in reply and "/app/?t=l_" in reply
        link = reply.split("t=")[1].strip()
        assert client.post("/api/v1/session", json={"link": link}).status_code == 200
        r = client.get(f"/library?t={welcome}", follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"].startswith("/app/?t=l_")
        assert client.get("/app/").status_code == 200
