import hashlib
import hmac
import json
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings  # noqa: E402
from app.instagram import DryRunMessenger, parse_webhook  # noqa: E402
from app.main import create_app  # noqa: E402
from scripts.simulate import build  # noqa: E402

SECRET = "test-app-secret"
ADMIN = {"Authorization": "Bearer admin-xyz"}
ALICE = "1790000000000001"


@pytest.fixture
def env(tmp_path):
    s = Settings(app_secret=SECRET, verify_token="vt", admin_token="admin-xyz",
                 db_path=str(tmp_path / "t.db"), worker_enabled=False, public_base_url="http://test")
    messenger = DryRunMessenger()
    app = create_app(s, messenger)
    with TestClient(app) as client:
        yield client, app, messenger


def send(client, payload, secret=SECRET):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/webhooks/instagram", content=body,
                       headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})


def drain(app, messenger):
    messenger.sent.clear()
    app.state.worker.tick()
    return [t for _, t in messenger.sent]


def onboard(client, app, name="Alice", sender=ALICE):
    inv = client.post("/api/admin/invites", json={"note": name}, headers=ADMIN).json()
    r = client.post(f"/i/{inv['code']}", data={"name": name}, follow_redirects=False)
    assert r.status_code == 303
    welcome = client.get(r.headers["location"]).text
    code = re.search(r"STASH-[A-Z2-9]{6}", welcome).group(0)
    assert send(client, build(sender, "text", f"hi {code}")).json()["outcomes"] == ["linked"]
    return inv, r.headers["location"].split("t=")[1]


def test_webhook_verification(env):
    client, *_ = env
    ok = client.get("/webhooks/instagram", params={"hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    assert client.get("/webhooks/instagram", params={"hub.mode": "subscribe", "hub.verify_token": "no", "hub.challenge": "1"}).status_code == 403


def test_rejects_bad_signature(env):
    client, *_ = env
    assert send(client, build(ALICE, "text", "hi"), secret="wrong").status_code == 401


def test_stranger_is_told_invite_only_and_reel_not_stored(env):
    client, app, m = env
    assert send(client, build(ALICE, "reel", "pasta recipe")).json()["outcomes"] == ["invite-only"]
    assert "invite-only" in drain(app, m)[0]
    with app.state.db.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM saves").fetchone()[0] == 0


def test_waitlist_then_admin_invites_by_dm(env):
    client, app, m = env
    assert send(client, build(ALICE, "text", "waitlist")).json()["outcomes"] == ["waitlisted"]
    assert client.get("/api/admin/waitlist", headers=ADMIN).json()[0]["igsid"] == ALICE
    inv = client.post(f"/api/admin/waitlist/{ALICE}/invite", headers=ADMIN).json()
    assert inv["code"] in drain(app, m)[-1]


def test_full_flow_invite_link_save_reply(env):
    client, app, m = env
    inv, token = onboard(client, app)
    assert "You're in, Alice" in drain(app, m)[0]
    assert "Instagram linked" in client.get(f"/welcome?t={token}").text

    assert send(client, build(ALICE, "reel", "15 min paneer wrap, high protein #recipe")).json()["outcomes"] == ["queued"]
    assert drain(app, m) == ["Saved to Recipes ✓"]

    lib = client.get(f"/library?t={token}").text
    assert "Recipes" in lib and "paneer wrap" in lib

    # Invite was single-use.
    assert client.get(f"/i/{inv['code']}").status_code == 410


def test_link_in_text_and_dedupe(env):
    client, app, m = env
    onboard(client, app)
    url = "https://www.instagram.com/reel/Cabc123/?igsh=xyz"
    assert send(client, build(ALICE, "text", url)).json()["outcomes"] == ["queued"]
    drain(app, m)
    assert send(client, build(ALICE, "text", url)).json()["outcomes"] == ["already-saved"]


def test_meta_retry_is_idempotent(env):
    client, app, _ = env
    onboard(client, app)
    payload = build(ALICE, "reel", "goa trip cafes")
    assert send(client, payload).json()["outcomes"] == ["queued"]
    assert send(client, payload).json()["outcomes"] == ["duplicate-delivery"]


def test_revoked_member_blocked(env):
    client, app, m = env
    onboard(client, app)
    uid = client.get("/api/admin/users", headers=ADMIN).json()[0]["id"]
    client.post(f"/api/admin/users/{uid}/status", json={"status": "revoked"}, headers=ADMIN)
    assert send(client, build(ALICE, "reel", "workout")).json()["outcomes"] == ["revoked"]


def test_wrong_link_code_and_admin_auth(env):
    client, app, m = env
    assert send(client, build(ALICE, "text", "STASH-ZZZZZZ")).json()["outcomes"] == ["link-failed"]
    assert client.get("/api/admin/users").status_code == 401
    assert client.get("/library?t=1.forged").status_code == 404


def test_parser_tolerates_unknown_attachments():
    p = build(ALICE, "text", "x")
    p["entry"][0]["messaging"][0]["message"]["attachments"] = [{"type": "story_mention", "payload": {}}]
    assert parse_webhook(p)[0].shares == []


def test_welcome_links_expire_and_cannot_be_forged(env):
    client, app, _ = env
    _, token = onboard(client, app)
    access = app.state.access
    uid, exp, sig = token.split(".")
    assert access.user_from_token(token)["name"] == "Alice"
    assert access.user_from_token(f"{uid}.{int(exp) + 999}.{sig}") is None   # changed expiry → bad signature
    assert access.user_from_token(access.token_for(int(uid), days=-1)) is None  # expired
    assert access.user_from_token(f"{uid}.{sig}") is None                    # old two-part format
    assert client.get(f"/welcome?t={access.token_for(int(uid), days=-1)}").status_code == 404
