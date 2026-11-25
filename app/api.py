"""JSON API for the web app. Every route needs the member's token: `Authorization: Bearer <token>`."""
from datetime import date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, File, Header, HTTPException, Query, UploadFile

from .access import Access, AccessError
from .importer import MAX_UPLOAD, ImportProblem, apply_import, list_imports, parse_export, undo_import
from .library import Invalid, Library, NotFound
from .reminders import Reminders

EDITABLE = {"progress", "note", "board_id", "plan_day", "remind_at", "category"}


def build_router(access: Access, library: Library, reminders: Reminders) -> APIRouter:
    r = APIRouter(prefix="/api/v1")

    def bearer(authorization: str = Header("")) -> str:
        return authorization.removeprefix("Bearer ").strip()

    def member(token: str = Depends(bearer)) -> dict:
        user = access.user_from_session(token)
        if not user:
            raise HTTPException(401, "You're signed out. Send LIBRARY to @stash on Instagram for a sign-in link.")
        return user

    @r.post("/session")
    def start_session(body: dict = Body(...)):
        """Swap a single-use sign-in link for a 30-day session."""
        try:
            return access.exchange_login_link(str(body.get("link", "")))
        except AccessError as e:
            raise HTTPException(401, str(e))

    @r.delete("/session")
    def end_session(token: str = Depends(bearer)):
        access.revoke_session(token)
        return {"ok": True}

    def run(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except NotFound:
            raise HTTPException(404, "That save doesn't exist.")
        except Invalid as e:
            raise HTTPException(400, str(e))

    @r.get("/me")
    def me(user: dict = Depends(member)):
        return {"id": user["id"], "name": user["name"], "instagram_linked": bool(user["igsid"]), "email": user["email"],
                "timezone": user.get("timezone") or ""}

    @r.patch("/me")
    def update_me(body: dict = Body(...), user: dict = Depends(member)):
        if not body or set(body) - {"email", "timezone"}:
            raise HTTPException(400, "Only email and timezone can be changed here.")
        out = {}
        if "timezone" in body:
            name = str(body["timezone"] or "")[:64]
            try:
                ZoneInfo(name)
            except Exception:  # noqa: BLE001 - unknown or malformed zone name
                raise HTTPException(400, "That isn't a time zone name like Asia/Kolkata.")
            with access.db.tx() as c:
                c.execute("UPDATE users SET timezone = ? WHERE id = ?", (name, user["id"]))
            out["timezone"] = name
        if "email" in body:
            try:
                out["email"] = reminders.set_email(user["id"], str(body.get("email", "")))
            except ValueError as e:
                raise HTTPException(400, str(e))
        return out

    # ---- importing saves from Instagram's "Download your information" export
    @r.post("/import")
    async def import_export(file: UploadFile = File(...), user: dict = Depends(member)):
        data = await file.read(MAX_UPLOAD + 1)
        try:
            parsed = parse_export(data, file.filename or "")
            return apply_import(access.db, user["id"], parsed, file.filename or "export")
        except ImportProblem as e:
            raise HTTPException(400, str(e))

    @r.get("/imports")
    def imports(user: dict = Depends(member)):
        return list_imports(access.db, user["id"])

    @r.delete("/imports/{import_id}")
    def undo(import_id: int, user: dict = Depends(member)):
        try:
            return undo_import(access.db, user["id"], import_id)
        except ImportProblem as e:
            raise HTTPException(404 if "exist" in str(e) else 400, str(e))

    # ---- reminders
    @r.get("/reminders")
    def reminder_settings(user: dict = Depends(member)):
        return {"channels": reminders.channels(user["id"]), "upcoming": reminders.upcoming(user["id"])}

    @r.post("/reminders/test")
    def test_reminder(user: dict = Depends(member)):
        res = reminders.deliver(user["id"], None, every_channel=True)
        return {"sent": res.channel is not None, "channels": res.tried}

    @r.post("/push/subscribe")
    def push_subscribe(body: dict = Body(...), user: dict = Depends(member)):
        try:
            reminders.subscribe(user["id"], body.get("subscription") or {})
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @r.post("/push/unsubscribe")
    def push_unsubscribe(body: dict = Body(...), user: dict = Depends(member)):
        reminders.unsubscribe(user["id"], str(body.get("endpoint", "")))
        return {"ok": True}

    @r.get("/home")
    def home(user: dict = Depends(member)):
        return library.home(user["id"])

    @r.get("/saves")
    def saves(q: str = Query("", max_length=200), user: dict = Depends(member)):
        return {"query": q, "results": library.search(user["id"], q)}

    @r.get("/saves/{save_id}")
    def get_save(save_id: int, user: dict = Depends(member)):
        return run(library.get, user["id"], save_id)

    @r.patch("/saves/{save_id}")
    def patch_save(save_id: int, body: dict = Body(...), user: dict = Depends(member)):
        unknown = set(body) - EDITABLE
        if unknown:
            raise HTTPException(400, f"Can't change: {', '.join(sorted(unknown))}")
        return run(library.update, user["id"], save_id, body)

    @r.delete("/saves/{save_id}")
    def delete_save(save_id: int, user: dict = Depends(member)):
        run(library.delete, user["id"], save_id)
        return {"ok": True}

    @r.get("/categories")
    def categories(user: dict = Depends(member)):
        return library.categories(user["id"])

    @r.get("/boards")
    def boards(user: dict = Depends(member)):
        return library.boards(user["id"])

    @r.post("/boards")
    def create_board(body: dict = Body(...), user: dict = Depends(member)):
        return run(library.create_board, user["id"], str(body.get("name", "")))

    @r.patch("/boards/{board_id}")
    def rename_board(board_id: int, body: dict = Body(...), user: dict = Depends(member)):
        return run(library.rename_board, user["id"], board_id, str(body.get("name", "")))

    @r.delete("/boards/{board_id}")
    def delete_board(board_id: int, user: dict = Depends(member)):
        run(library.delete_board, user["id"], board_id)
        return {"ok": True}

    @r.get("/rediscover")
    def rediscover(user: dict = Depends(member)):
        return library.rediscover(user["id"])

    @r.post("/saves/{save_id}/review")
    def review(save_id: int, body: dict = Body(...), user: dict = Depends(member)):
        return run(library.review, user["id"], save_id, str(body.get("action", "")), body.get("remind_at"))

    @r.get("/plan")
    def plan(start: str | None = Query(None), user: dict = Depends(member)):
        try:
            d = date.fromisoformat(start) if start else None
        except ValueError:
            raise HTTPException(400, "start must be a date like 2026-11-23")
        return library.plan(user["id"], d)

    return r
