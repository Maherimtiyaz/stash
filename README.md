# Stash DM backend (prototype)

Invite-only backend for Stash. People send Instagram reels to **@stash** in DMs; Stash files them and replies "Saved to Recipes ✓".

## What's in here

| File | Job |
|---|---|
| `app/main.py` | FastAPI routes: Meta webhook, invite pages, library, admin API |
| `app/instagram.py` | Webhook signature check, payload parser, Send API client (+ dry-run client) |
| `app/access.py` | Invites, users, one-time link codes, signed page links |
| `app/bot.py` | What to do with each DM (link, save, waitlist, help) |
| `app/worker.py` | Background worker: categorise saves, send queued replies with retries |
| `app/db.py` | SQLite schema |
| `scripts/simulate.py` | Send signed fake webhooks to a running server |
| `tests/test_flow.py` | End-to-end tests of every path |

## Run locally (no Meta account needed)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
IG_APP_SECRET=demo-secret IG_VERIFY_TOKEN=vt ADMIN_TOKEN=admin-demo .venv/bin/uvicorn app.main:create_app --factory --port 8000
```

With no `IG_ACCESS_TOKEN` the server runs in **dry-run**: replies are logged instead of sent.

1. Open http://localhost:8000/admin, sign in with `admin-demo`, create an invite.
2. Open the invite link, enter a name. The next page shows a code like `STASH-QD5YZW`.
3. Pretend to DM it, then share reels:

```bash
IG_APP_SECRET=demo-secret .venv/bin/python scripts/simulate.py code STASH-QD5YZW
```

```bash
IG_APP_SECRET=demo-secret .venv/bin/python scripts/simulate.py reel "15 min paneer wrap #recipe"
```

Tests:

```bash
.venv/bin/python -m pytest -q
```

## Connect real Instagram

1. Create a **Business or Creator** Instagram account for @stash.
2. developers.facebook.com → Create app → add **Instagram** → "API setup with Instagram login". Add the @stash account and generate a token (`IG_ACCESS_TOKEN`). Copy the app secret (`IG_APP_SECRET`).
3. Deploy this server on HTTPS (Railway, Render, Fly.io, a VPS + Caddy). For quick tests: `ngrok http 8000`.
4. In the app's Webhooks settings: callback `https://<your-domain>/webhooks/instagram`, verify token = `IG_VERIFY_TOKEN`, subscribe to **messages**.
5. While the Meta app is in **development mode**, only Instagram accounts added as testers in the app's roles can trigger webhooks. That is enough for a private beta of a few friends. For more people, submit App Review for `instagram_business_manage_messages` (Advanced Access).
6. **First real test:** share a reel to @stash and look at the server log. Confirm the `ig_reel` attachment fields (`reel_video_id`, `title`, `url`) match `app/instagram.py`, and adjust the parser if Meta's payload differs.

## How invite-only works

- Admin creates an invite (single-use or N uses, expiry) → link `/i/<code>`.
- Person opens it, enters a name → account created, invite use consumed (atomically).
- Welcome page shows a 30-minute code `STASH-XXXXXX`. They DM it to @stash.
- The webhook sees the code, links their Instagram sender ID (IGSID) to the account. From then on, anything they send is saved.
- Anyone else who DMs @stash gets "Stash is invite-only" and nothing is stored. Replying `WAITLIST` adds them to the admin waitlist, where one click DMs them an invite (Instagram only allows this within 24 h of their last message).
- Admin can cancel invites and turn members off at any time.

## Known limits of the prototype

- Categories come from keyword rules on the caption. Next step: fetch media, transcribe, and call an LLM in `worker.understand()`.
- SQLite + an in-process worker thread. For production: Postgres and a separate worker (Celery/RQ/arq) with the same tables.
- Page links (`/welcome`, `/library`) are signed but don't expire. Add expiry or a real login before a public launch.
- No rate limiting on the webhook or invite pages yet.
