import hmac
import json
import mimetypes
import logging
from contextlib import asynccontextmanager

from fastapi import Body, Depends, FastAPI, Form, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from pathlib import Path

from . import pages
from .access import Access, AccessError
from .api import build_router
from .bot import Bot
from .config import Settings
from .db import Database, now
from .library import Library
from .reminders import DryRunMailer, DryRunPusher, Mailer, Pusher, Reminders, SmtpMailer, WebPusher
from . import security
from .instagram import DryRunMessenger, GraphMessenger, Messenger, parse_webhook, verify_signature
from .worker import Worker

log = logging.getLogger("stash")
mimetypes.add_type("application/manifest+json", ".webmanifest")  # the web app's install manifest


def create_app(settings: Settings | None = None, messenger: Messenger | None = None,
               mailer: Mailer | None = None, pusher: Pusher | None = None) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    s = settings or Settings.from_env()
    problems = security.secret_problems(s)
    if problems and s.is_production:
        raise RuntimeError("Refusing to start in production:\n- " + "\n- ".join(problems)
                           + "\nRun: python scripts/make_secrets.py")
    for p in problems:
        log.warning("Not safe for a live server: %s", p)
    db = Database(s.db_path)
    access = Access(db, s.secret_key, s.link_code_minutes)
    library = Library(db, default_tz=s.default_timezone)
    dist = Path(s.frontend_dist) if s.frontend_dist else None
    has_frontend = bool(dist and (dist / "index.html").is_file())
    bot = Bot(db, access, s.public_base_url, s.ig_username, app_path="/app" if has_frontend else "/library",
              library=library, default_tz=s.default_timezone)
    if messenger is None:
        messenger = DryRunMessenger() if s.dry_run else GraphMessenger(s.access_token, s.graph_version)
    if mailer is None:
        mailer = (SmtpMailer(s.smtp_host, s.smtp_port, s.smtp_user, s.smtp_password, s.mail_from or s.smtp_user, s.smtp_starttls)
                  if s.smtp_host else DryRunMailer())
    if pusher is None:
        pusher = WebPusher(s.vapid_private_key, s.vapid_subject) if s.vapid_private_key else DryRunPusher()
    reminders = Reminders(db, access, mailer, pusher, s.public_base_url, has_frontend)
    reminders.public_key = s.vapid_public_key
    worker = Worker(db, messenger, reminders=reminders, default_tz=s.default_timezone)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if s.worker_enabled:
            worker.start()
        log.info("Stash started (dry_run=%s)", s.dry_run)
        yield
        worker.stop()

    app = FastAPI(title="Stash DM backend", lifespan=lifespan)
    app.state.settings, app.state.db, app.state.access = s, db, access
    app.state.bot, app.state.worker, app.state.messenger = bot, worker, messenger
    security.install(app, s)
    app.state.reminders, app.state.mailer, app.state.pusher = reminders, mailer, pusher
    app.state.library = library
    app.include_router(build_router(access, library, reminders))

    # ------------------------------------------------------------------ Meta webhook
    @app.get("/webhooks/instagram")
    def verify_webhook(
        mode: str = Query("", alias="hub.mode"),
        token: str = Query("", alias="hub.verify_token"),
        challenge: str = Query("", alias="hub.challenge"),
    ):
        """Meta calls this once when you register the webhook URL."""
        if mode == "subscribe" and s.verify_token and token == s.verify_token:
            return PlainTextResponse(challenge)
        raise HTTPException(403, "verification failed")

    @app.post("/webhooks/instagram")
    async def receive_webhook(request: Request):
        raw = await request.body()
        if not verify_signature(raw, request.headers.get("x-hub-signature-256"), s.app_secret):
            raise HTTPException(401, "bad signature")
        try:
            payload = json.loads(raw)
        except ValueError:
            raise HTTPException(400, "invalid JSON")
        outcomes = []
        for msg in parse_webhook(payload):
            try:
                outcomes.append(bot.handle(msg))
            except Exception:
                # Never fail the whole delivery: Meta would retry it and eventually disable the webhook.
                log.exception("handling %s failed", msg.mid)
                outcomes.append("error")
        return {"ok": True, "outcomes": outcomes}

    # ------------------------------------------------------------------ invite + linking pages
    @app.get("/i/{code}", response_class=HTMLResponse)
    def invite(code: str):
        inv = access.get_invite(code)
        problem = access.invite_problem(inv)
        if problem:
            return HTMLResponse(pages.error_page(problem), status_code=404 if not inv else 410)
        return pages.invite_page(inv["code"], inv["note"])

    @app.post("/i/{code}")
    def accept_invite(code: str, name: str = Form(""), email: str = Form("")):
        try:
            uid = access.redeem_invite(code, name, email)
        except AccessError as e:
            inv = access.get_invite(code)
            if access.invite_problem(inv):
                return HTMLResponse(pages.error_page(str(e)), status_code=410)
            return HTMLResponse(pages.invite_page(inv["code"], inv["note"], str(e)), status_code=400)
        # Redirect so a page reload can't consume a second use of the invite.
        return RedirectResponse(f"/welcome?t={access.token_for(uid)}", status_code=303)

    def member(t: str = Query("")) -> dict:
        user = access.user_from_token(t)
        if not user:
            raise HTTPException(404, "Link not valid")
        return user

    @app.get("/welcome", response_class=HTMLResponse)
    def welcome(t: str = Query(""), user: dict = Depends(member)):
        lc = access.current_link_code(user["id"]) if not user["igsid"] else {"code": "", "expires_at": " " * 16}
        return pages.welcome_page(user["name"], lc["code"], lc["expires_at"], s.ig_username, bool(user["igsid"]), t)

    @app.get("/api/me")
    def me(user: dict = Depends(member)):
        return {"name": user["name"], "linked": bool(user["igsid"])}

    @app.get("/library", response_class=HTMLResponse)
    def library_page(t: str = Query(""), user: dict = Depends(member)):
        if has_frontend:
            return RedirectResponse(f"/app/?t={access.create_login_link(user['id'])}", status_code=302)
        with db.connect() as c:
            saves = [dict(r) for r in c.execute(
                "SELECT * FROM saves WHERE user_id = ? ORDER BY created_at DESC", (user["id"],))]
        return pages.library_page(user["name"], saves)

    # ------------------------------------------------------------------ admin
    def admin(authorization: str = Header("")):
        if not s.admin_token or not hmac.compare_digest(authorization.encode(), f"Bearer {s.admin_token}".encode()):
            raise HTTPException(401, "admin token required")

    def with_url(inv: dict) -> dict:
        return {**inv, "url": f"{s.public_base_url}/i/{inv['code']}"}

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page():
        return pages.ADMIN_HTML

    @app.post("/api/admin/invites", dependencies=[Depends(admin)])
    def create_invite(body: dict = Body(default={})):
        days = body.get("expires_in_days", 14)
        inv = access.create_invite(str(body.get("note", ""))[:80], int(body.get("max_uses", 1)), int(days) if days else None)
        return with_url(inv)

    @app.get("/api/admin/invites", dependencies=[Depends(admin)])
    def list_invites():
        return [with_url(i) for i in access.list_invites()]

    @app.post("/api/admin/invites/{code}/revoke", dependencies=[Depends(admin)])
    def revoke_invite(code: str):
        access.revoke_invite(code)
        return {"ok": True}

    @app.get("/api/admin/users", dependencies=[Depends(admin)])
    def list_users():
        return access.list_users()

    @app.post("/api/admin/users/{user_id}/status", dependencies=[Depends(admin)])
    def user_status(user_id: int, body: dict = Body(...)):
        status = body.get("status")
        if status not in ("active", "revoked"):
            raise HTTPException(400, "status must be active or revoked")
        access.set_user_status(user_id, status)
        return {"ok": True}

    @app.get("/api/admin/waitlist", dependencies=[Depends(admin)])
    def waitlist():
        with db.connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM waitlist ORDER BY created_at")]

    @app.post("/api/admin/waitlist/{igsid}/invite", dependencies=[Depends(admin)])
    def invite_from_waitlist(igsid: str):
        inv = access.create_invite("waitlist", 1, 14)
        with db.tx() as c:
            if not c.execute("SELECT 1 FROM waitlist WHERE igsid = ?", (igsid,)).fetchone():
                raise HTTPException(404, "not on waitlist")
            c.execute("UPDATE waitlist SET invited = 1 WHERE igsid = ?", (igsid,))
            # Instagram only allows replies within 24h of the person's last message.
            c.execute("INSERT INTO outbox(igsid, text, created_at) VALUES (?,?,?)",
                      (igsid, f"A spot opened up! Your Stash invite: {s.public_base_url}/i/{inv['code']}", now()))
        return with_url(inv)

    # ------------------------------------------------------------------ web app (built React files)
    if has_frontend:
        @app.get("/app", include_in_schema=False)
        @app.get("/app/{path:path}", include_in_schema=False)
        def web_app(path: str = ""):
            target = (dist / path).resolve()
            if path and target.is_file() and dist.resolve() in target.parents:
                return FileResponse(target)
            return FileResponse(dist / "index.html")  # client-side routes

    @app.get("/healthz")
    def health():
        return JSONResponse({"ok": True, "dry_run": s.dry_run})

    return app

