"""JSON API for the web app. Every route needs the member's token: `Authorization: Bearer <token>`."""
from datetime import date

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query

from .access import Access, AccessError
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
        return {"id": user["id"], "name": user["name"], "instagram_linked": bool(user["igsid"]), "email": user["email"]}

    @r.patch("/me")
    def update_me(body: dict = Body(...), user: dict = Depends(member)):
        if set(body) - {"email"}:
            raise HTTPException(400, "Only email can be changed here.")
        try:
            return {"email": reminders.set_email(user["id"], str(body.get("email", "")))}
        except ValueError as e:
            raise HTTPException(400, str(e))

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
