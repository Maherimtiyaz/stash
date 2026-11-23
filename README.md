# Stash

Invite-only app for organising saved Instagram reels. People send reels to **@stash** in DMs; Stash files them, replies "Saved to Recipes ✓", and gives each member a web app to search, rediscover, pin and plan their saves.

## What's in here

| File | Job |
|---|---|
| `app/main.py` | FastAPI routes: Meta webhook, invite pages, admin API, serves the web app at `/app` |
| `app/api.py` | JSON API for the web app (`/api/v1/*`) |
| `app/library.py` | Search, boards, statuses, Rediscover, week plan |
| `app/instagram.py` | Webhook signature check, payload parser, Send API client (+ dry-run client) |
| `app/access.py` | Invites, users, one-time link codes, signed page links |
| `app/bot.py` | What to do with each DM (link, save, waitlist, help) |
| `app/worker.py` | Background worker: categorise saves, send queued replies with retries |
| `app/db.py` | SQLite schema, plus column migrations for existing databases |
| `frontend/` | React + TypeScript web app (Vite): `src/views/` one file per tab, `src/components/Viewer.tsx` the save view, `src/components/ui.tsx` the reel card |
| `scripts/simulate.py` | Send signed fake webhooks to a running server |
| `scripts/seed_demo.py` | Fill a local database with a demo member and sample saves |
| `tests/` | DM flow, web API, database migration and shelf-sorting tests |

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

## The web app

Four tabs on a floating dock, one library. Every save is drawn as a bold 9:16 "reel cover" (a colour and pattern per category, big title, stickers for planned day and reminder, a stamp once you've tried it).

- **Shelves**: every save is sorted automatically onto a shelf: Tech, Travel, Recipes, Gym & Fitness, Fashion, Health, Money, Books, Home (or Unsorted). Home shows one row per shelf with counts and "See all", or switch to "Newest". Tap a shelf chip to filter. If Stash picks the wrong shelf, move the save from its view. Sorting uses keyword rules in `app/categories.py`.
- **Search** (home): your whole stash as a wall of reels. Type what you remember and matching reels light up while the rest fade. Searches captions, creators, `#tags`, your notes and pile names. Filters: `in:Recipes` (also `in:gym`, `in:tech`, `in:food`), `in:"Goa trip"`, `by:@creator`, `is:todo`, `is:done`, plus one-tap chips. Results are grouped by shelf. Enter opens the first match. Type `/` for commands: `/tech`, `/travel`, `/gym`…, `/todo`, `/done`, `/random`, `/capsule`, `/piles`, `/plan`. "On this day" is pinned to the wall with a strip of tape.
- **Capsule**: forgotten to-try saves, one card at a time, with a postmark showing when you saved it. Drag the card or tap **Keep**, **Later** (back on Saturday) or **Let go**; arrow keys work too. A reviewed save returns after 30 days.
- **Piles**: each board is a fanned stack of its reels. Open a pile to see it as a Pinterest-style moodboard; create, rename and delete piles.
- **Plan**: the week. Drag a reel from "Someday" onto a day (or tap it, then tap a day). Drag a planned slip back to Someday to unplan it.

Opening a save shows it large next to everything you can do with it: **I tried it** (with a small confetti burst) or **Not for me**, day tickets for planning, **Nudge me** reminders, pile stickers (you can make a new pile right there) and a sticky note for your own note. Full screen on phones, a card on desktop. Light and dark themes follow the device.

**Sign-in:** the bot's welcome message and the `LIBRARY` command send a private link (`/app/?t=…`) that works **once, for 24 hours**. The app swaps it for a 30-day session, removes it from the address bar, and **Sign out** ends the session on the server. A used or expired link shows a clear message; send `LIBRARY` again for a new one.

### Run it locally

Build the frontend once (Node 18+), and the FastAPI server serves it at `/app`:

```bash
cd frontend && npm install && npm run build && cd ..
```

```bash
DB_PATH=demo.db .venv/bin/python scripts/seed_demo.py
```

```bash
DB_PATH=demo.db IG_APP_SECRET=demo-secret ADMIN_TOKEN=admin-demo .venv/bin/uvicorn app.main:create_app --factory --port 8000
```

Open the link that `seed_demo.py` printed. For frontend work with hot reload, keep the server running and start Vite in another terminal (it proxies `/api` to port 8000):

```bash
cd frontend && npm run dev
```

Then open `http://localhost:5173/app/?t=<token from the seed link>`.

### API

All routes need `Authorization: Bearer <token>`.

| Method | Path | Does |
|---|---|---|
| GET | `/api/v1/me` | Signed-in member |
| GET | `/api/v1/home` | Recent saves, "on this day", counts |
| GET | `/api/v1/categories` | Shelves in display order with counts |
| GET | `/api/v1/saves?q=` | Search (words + filters) |
| GET / PATCH / DELETE | `/api/v1/saves/{id}` | Read, change `progress` `note` `board_id` `plan_day` `remind_at` `category`, delete |
| GET / POST | `/api/v1/boards` | List, create |
| PATCH / DELETE | `/api/v1/boards/{id}` | Rename, delete (saves are kept) |
| GET | `/api/v1/rediscover` | Rediscover deck |
| POST | `/api/v1/saves/{id}/review` | `{"action": "keep" | "let_go" | "later"}` |
| GET | `/api/v1/plan?start=YYYY-MM-DD` | Week plan and someday pile |

## Connect real Instagram

1. Create a **Business or Creator** Instagram account for @stash.
2. developers.facebook.com → Create app → add **Instagram** → "API setup with Instagram login". Add the @stash account and generate a token (`IG_ACCESS_TOKEN`). Copy the app secret (`IG_APP_SECRET`).
3. Deploy this server on HTTPS (Railway, Render, Fly.io, a VPS + Caddy). For quick tests: `ngrok http 8000`.
4. In the app's Webhooks settings: callback `https://<your-domain>/webhooks/instagram`, verify token = `IG_VERIFY_TOKEN`, subscribe to **messages**.
5. While the Meta app is in **development mode**, only Instagram accounts added as testers in the app's roles can trigger webhooks. That is enough for a private beta of a few friends. For more people, submit App Review for `instagram_business_manage_messages` (Advanced Access).
6. **First real test:** share a reel to @stash and look at the server log. Confirm the `ig_reel` attachment fields (`reel_video_id`, `title`, `url`) match `app/instagram.py`, and adjust the parser if Meta's payload differs.

## Security

| Protection | How |
|---|---|
| Sign-in links | Single-use, expire after 24 hours. Only SHA-256 hashes are stored. |
| Sessions | 30 days, ended by **Sign out** or when an admin turns the member off. Only hashes are stored. |
| Welcome-page links | Signed with an expiry (7 days) that can't be edited. |
| Rate limits | Per visitor and per minute: 10 sign-in link swaps, 10 invite submissions, 60 admin calls, 300 web app API calls. Over the limit → `429` with `Retry-After`. |
| Headers | `no-referrer` (links never leak to other sites), `nosniff`, no framing, strict Content-Security-Policy on the web app, no caching of API responses, HSTS in production. |
| Secrets | With `APP_ENV=production` the server won't start with weak or missing secrets and lists what to fix. |
| Admin token | Compared in constant time. Leave `ADMIN_TOKEN` empty to turn the admin panel off. |

**Before going live**, generate secrets and paste them into your host's environment settings (never commit them):

```bash
python scripts/make_secrets.py
```

Also set `IG_APP_SECRET` from your Meta app, `PUBLIC_BASE_URL=https://your-domain`, and `TRUST_PROXY=1` if the app runs behind your host's proxy (Railway, Render and Fly.io all do), so limits apply per visitor instead of per proxy.

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
- Rate limits are kept in memory, so they reset on restart and don't add up across several server processes. Use Redis when running more than one.
- Reminders are stored but not sent yet. Instagram only allows bot DMs within 24 h of the member's last message, so delivery needs email or web push.
- Search scans a member's saves in Python. Fine for thousands of saves; move to SQLite FTS5 or Postgres full-text search beyond that.
- Saves have no thumbnails yet; cards use a colour per category until media fetching exists.
- Plan "today" uses the server's UTC date, so it can be a day off near midnight in other time zones.
