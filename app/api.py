"""JSON API for the web app. Every route needs the member's token: `Authorization: Bearer <token>`."""
from datetime import date

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query

from .access import Access
from .library import Invalid, Library, NotFound

EDITABLE = {"progress", "note", "board_id", "plan_day", "remind_at", "category"}


def build_router(access: Access, library: Library) -> APIRouter:
    r = APIRouter(prefix="/api/v1")

    def member(authorization: str = Header("")) -> dict:
        token = authorization.removeprefix("Bearer ").strip()
        user = access.user_from_token(token) if token else None
        if not user:
            raise HTTPException(401, "Your sign-in link isn't valid. Send LIBRARY to @stash for a new one.")
        return user

    def run(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except NotFound:
            raise HTTPException(404, "That save doesn't exist.")
        except Invalid as e:
            raise HTTPException(400, str(e))

    @r.get("/me")
    def me(user: dict = Depends(member)):
        return {"id": user["id"], "name": user["name"], "instagram_linked": bool(user["igsid"])}

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
