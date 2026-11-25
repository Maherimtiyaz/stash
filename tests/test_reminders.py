import base64
import json
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings  # noqa: E402
from app.instagram import DryRunMessenger  # noqa: E402
from app.main import create_app  # noqa: E402
from app.reminders import DryRunMailer, DryRunPusher, SmtpMailer, WebPusher  # noqa: E402
from scripts.simulate import build  # noqa: E402
from tests.test_api import session_for  # noqa: E402
from tests.test_flow import ALICE, drain, onboard, send  # noqa: E402

PAST = "2020-01-01T09:00:00+00:00"
SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "BPk", "auth": "xyz"}}


@pytest.fixture
def r(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html>")
    s = Settings(app_secret="test-app-secret", verify_token="vt", admin_token="admin-xyz", frontend_dist=str(dist),
                 db_path=str(tmp_path / "t.db"), worker_enabled=False, public_base_url="http://test")
    m, mail, push = DryRunMessenger(), DryRunMailer(), DryRunPusher()
    app = create_app(s, m, mailer=mail, pusher=push)
    with TestClient(app) as client:
        _, welcome = onboard(client, app)
        send(client, build(ALICE, "reel", "Lemon garlic pasta #recipe"))
        app.state.worker.tick()
        drain(app, m)
        client.headers["Authorization"] = f"Bearer {session_for(client, app, welcome)}"
        sid = client.get("/api/v1/saves").json()["results"][0]["id"]
        yield type("R", (), dict(client=client, app=app, m=m, mail=mail, push=push, sid=sid))


def close_dm_window(app):
    with app.state.db.tx() as c:
        c.execute("UPDATE ig_accounts SET last_message_at = ?", ((datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),))


def remind(r, when=PAST):
    assert r.client.patch(f"/api/v1/saves/{r.sid}", json={"remind_at": when}).status_code == 200


def channel(r):
    with r.app.state.db.connect() as c:
        return c.execute("SELECT remind_channel FROM saves WHERE id = ?", (r.sid,)).fetchone()[0]


def test_dm_inside_the_24h_window(r):
    remind(r)
    r.m.sent.clear()
    r.app.state.worker.tick()
    assert channel(r) == "dm"
    text = r.m.sent[0][1]
    assert "Reminder: Lemon garlic pasta\n" in text and "#recipe" not in text
    assert "/app/?t=l_" in text and text.endswith(f"&open={r.sid}")  # signs in, then opens the save
    r.app.state.worker.tick()  # sent once only
    assert len(r.m.sent) == 1


def test_push_when_dm_window_closed(r):
    close_dm_window(r.app)
    r.client.post("/api/v1/push/subscribe", json={"subscription": SUB})
    r.client.patch("/api/v1/me", json={"email": "alice@example.com"})
    remind(r)
    r.app.state.worker.tick()
    assert channel(r) == "push" and r.mail.sent == []
    endpoint, payload = r.push.sent[0]
    assert endpoint == SUB["endpoint"] and payload["url"] == f"http://test/app/?open={r.sid}"
    assert payload["title"] == "Reminder: Lemon garlic pasta"


def test_email_as_last_resort(r):
    close_dm_window(r.app)
    r.client.patch("/api/v1/me", json={"email": "alice@example.com"})
    remind(r)
    r.app.state.worker.tick()
    assert channel(r) == "email"
    to, subject, text = r.mail.sent[0]
    assert to == "alice@example.com" and subject == "Reminder: Lemon garlic pasta" and "works once" in text
    assert f"/app/?t=l_" in text and f"&open={r.sid}" in text


def test_nothing_set_up_is_recorded(r):
    close_dm_window(r.app)
    remind(r)
    r.app.state.worker.tick()
    assert channel(r) == "failed"


def test_not_due_yet_and_rescheduling(r):
    remind(r, (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat())
    r.app.state.worker.tick()
    assert channel(r) is None
    remind(r)  # move it into the past → due again
    r.app.state.worker.tick()
    assert channel(r) == "dm"
    remind(r)  # setting a time again re-arms it
    assert channel(r) is None


def test_times_are_stored_in_utc(r):
    s = r.client.patch(f"/api/v1/saves/{r.sid}", json={"remind_at": "2030-05-01T20:00:00+05:30"}).json()
    assert s["remind_at"] == "2030-05-01T14:30:00+00:00"


def test_tried_saves_are_not_nagged(r):
    r.client.patch(f"/api/v1/saves/{r.sid}", json={"progress": "done"})
    remind(r)
    r.m.sent.clear()
    r.app.state.worker.tick()
    assert channel(r) == "skipped" and r.m.sent == []


def test_gone_devices_are_forgotten(r):
    from app.reminders import PushGone

    class Gone(DryRunPusher):
        def send(self, sub, payload):
            raise PushGone()
    r.app.state.reminders.pusher = Gone()
    close_dm_window(r.app)
    r.client.post("/api/v1/push/subscribe", json={"subscription": SUB})
    remind(r)
    r.app.state.worker.tick()
    assert r.client.get("/api/v1/reminders").json()["channels"]["push"]["devices"] == 0


def test_settings_api_and_validation(r):
    c = r.client
    ch = c.get("/api/v1/reminders").json()["channels"]
    assert ch["dm"]["open"] is True and ch["push"]["devices"] == 0 and ch["email"]["address"] == ""
    assert c.patch("/api/v1/me", json={"email": "not-an-email"}).status_code == 400
    assert c.patch("/api/v1/me", json={"name": "x"}).status_code == 400
    assert c.patch("/api/v1/me", json={"email": "a@b.co"}).json()["email"] == "a@b.co"
    assert c.post("/api/v1/push/subscribe", json={"subscription": {"endpoint": "http://insecure"}}).status_code == 400
    remind(r, (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    assert [u["id"] for u in c.get("/api/v1/reminders").json()["upcoming"]] == [r.sid]


def test_test_reminder_reports_every_channel_and_is_limited(r):
    r.client.patch("/api/v1/me", json={"email": "a@b.co"})
    res = r.client.post("/api/v1/reminders/test").json()
    assert res["sent"] is True
    assert res["channels"]["dm"] == "sent" and res["channels"]["email"] == "sent" and res["channels"]["push"].startswith("off")
    codes = [r.client.post("/api/v1/reminders/test").status_code for _ in range(6)]
    assert 429 in codes


def test_bot_message_reopens_the_dm_window(r):
    close_dm_window(r.app)
    assert r.client.get("/api/v1/reminders").json()["channels"]["dm"]["open"] is False
    send(r.client, build(ALICE, "text", "hi"))
    assert r.client.get("/api/v1/reminders").json()["channels"]["dm"]["open"] is True


# ---------------------------------------------------------------- real channel implementations

def test_web_push_is_encrypted_for_the_browser():
    """Send a real Web Push request to a local endpoint and decrypt it with the 'browser' keys."""
    import http_ece
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from py_vapid import Vapid02

    got = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            got["body"] = self.rfile.read(int(self.headers["Content-Length"]))
            got["headers"] = dict(self.headers)
            self.send_response(201)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.handle_request, daemon=True).start()

    browser_key = ec.generate_private_key(ec.SECP256R1())
    auth = b"0123456789abcdef"
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    pub = browser_key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    v = Vapid02()
    v.generate_keys()
    raw_private = b64(v.private_key.private_numbers().private_value.to_bytes(32, "big"))

    WebPusher(raw_private, "mailto:test@example.com").send(
        {"endpoint": f"http://127.0.0.1:{srv.server_port}/push", "p256dh": b64(pub), "auth": b64(auth)},
        {"title": "Reminder: Lemon pasta", "url": "/app/?open=1"})
    srv.server_close()
    plain = http_ece.decrypt(got["body"], private_key=browser_key, auth_secret=auth, version="aes128gcm")
    assert json.loads(plain)["title"] == "Reminder: Lemon pasta"
    headers = {k.lower(): v for k, v in got["headers"].items()}
    assert headers["authorization"].startswith("vapid t=") and headers["content-encoding"] == "aes128gcm"


def test_smtp_mailer_sends_a_proper_message(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            sent["tls"] = True

        def login(self, u, p):
            sent["login"] = u

        def send_message(self, msg):
            sent["msg"] = msg

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    SmtpMailer("smtp.example.com", 587, "user", "pw", "Stash <hi@stash.app>").send("a@b.co", "Reminder: x", "Body")
    assert sent["server"] == ("smtp.example.com", 587) and sent["tls"] and sent["login"] == "user"
    assert sent["msg"]["To"] == "a@b.co" and sent["msg"]["From"] == "Stash <hi@stash.app>"
