import base64
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import Settings  # noqa: E402
from app.instagram import DryRunMessenger  # noqa: E402
from app.main import create_app  # noqa: E402

STRONG = dict(secret_key="k" * 40, admin_token="a" * 30, app_secret="meta-app-secret", verify_token="v" * 20,
              public_base_url="https://stash.example")


def make(tmp_path, **kw):
    s = Settings(db_path=str(tmp_path / "t.db"), worker_enabled=False, **{**STRONG, **kw})
    return create_app(s, DryRunMessenger())


def test_sign_in_link_guessing_is_rate_limited(tmp_path):
    with TestClient(make(tmp_path)) as c:
        codes = [c.post("/api/v1/session", json={"link": f"l_guess{i}"}).status_code for i in range(12)]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]


def test_429_says_when_to_retry(tmp_path):
    with TestClient(make(tmp_path)) as c:
        for _ in range(10):
            c.post("/i/NOPE", data={"name": "x"})
        r = c.post("/i/NOPE", data={"name": "x"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1 and "Too many" in r.json()["detail"]


def test_limits_are_per_visitor_behind_a_proxy(tmp_path):
    with TestClient(make(tmp_path, trust_proxy=True)) as c:
        for _ in range(10):
            c.post("/api/v1/session", json={"link": "l_x"}, headers={"X-Forwarded-For": "1.1.1.1"})
        assert c.post("/api/v1/session", json={"link": "l_x"}, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429
        assert c.post("/api/v1/session", json={"link": "l_x"}, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 401


def test_rate_limits_can_be_turned_off(tmp_path):
    with TestClient(make(tmp_path, rate_limits=False)) as c:
        assert all(c.post("/api/v1/session", json={"link": "l_x"}).status_code == 401 for _ in range(15))


def test_security_headers(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html>")
    with TestClient(make(tmp_path, frontend_dist=str(dist), app_env="production")) as c:
        app_page = c.get("/app/")
        api = c.get("/api/v1/me")
        health = c.get("/healthz")
    assert "frame-ancestors 'none'" in app_page.headers["Content-Security-Policy"]
    assert "script-src 'self'" in app_page.headers["Content-Security-Policy"]
    for r in (app_page, api, health):
        assert r.headers["Referrer-Policy"] == "no-referrer"
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        assert "max-age" in r.headers["Strict-Transport-Security"]
    assert api.headers["Cache-Control"] == "no-store"


def test_production_refuses_weak_secrets(tmp_path):
    with pytest.raises(RuntimeError) as e:
        make(tmp_path, app_env="production", secret_key="dev-secret", admin_token="short", public_base_url="http://x")
    msg = str(e.value)
    assert "SECRET_KEY" in msg and "ADMIN_TOKEN" in msg and "PUBLIC_BASE_URL" in msg and "make_secrets" in msg
    make(tmp_path, app_env="production")  # strong values start fine


def test_development_only_warns(tmp_path, caplog):
    make(tmp_path, secret_key="dev-secret")
    assert any("SECRET_KEY" in r.getMessage() for r in caplog.records)


def test_admin_token_still_checked(tmp_path):
    with TestClient(make(tmp_path)) as c:
        assert c.get("/api/admin/users", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.get("/api/admin/users", headers={"Authorization": f"Bearer {'a' * 30}"}).status_code == 200


def test_make_secrets_prints_strong_values():
    out = subprocess.run([sys.executable, str(ROOT / "scripts/make_secrets.py")], capture_output=True, text=True).stdout
    values = dict(line.split("=", 1) for line in out.splitlines() if "=" in line and not line.startswith("#"))
    s = Settings(secret_key=values["SECRET_KEY"], admin_token=values["ADMIN_TOKEN"], verify_token=values["IG_VERIFY_TOKEN"],
                 app_secret="x-meta", public_base_url="https://stash.example")
    from app.security import secret_problems
    assert secret_problems(s) == [] and values["APP_ENV"] == "production"
    # The VAPID pair works for real Web Push signing.
    from py_vapid import Vapid02
    assert Vapid02.from_string(values["VAPID_PRIVATE_KEY"]).public_key is not None
    assert len(base64.urlsafe_b64decode(values["VAPID_PUBLIC_KEY"] + "==")) == 65
