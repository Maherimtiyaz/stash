"""Import saves from Instagram's "Download your information" export.

People request the export in Accounts Center, choose "Saved", and get a ZIP. Inside are
saved_posts.json (every saved post/reel with the owner's username and when it was saved) and
saved_collections.json (their Instagram collections). Instagram has changed the layout over the
years and offers an HTML version too, so this parser does not depend on one exact shape: it walks
the JSON looking for post links next to a timestamp and a username, and reads collection headers
in order. Unknown files in the ZIP are ignored and never written to disk.
"""
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape

from .categories import UNSORTED, guess
from .db import Database, now

POST_RE = re.compile(r"https?://(?:www\.)?instagram\.com/(?:[A-Za-z0-9._]+/)?(?P<kind>p|reel|reels|tv)/(?P<code>[A-Za-z0-9_-]{5,})")
MAX_UPLOAD = 50 * 1024 * 1024        # the "Saved"-only export is usually well under 1 MB
MAX_MEMBER = 20 * 1024 * 1024        # per file inside the ZIP, uncompressed (stops zip bombs)
MAX_ITEMS = 20_000


class ImportProblem(Exception):
    """A user-facing reason the file can't be imported."""


@dataclass
class Item:
    code: str
    kind: str                 # reel | post
    url: str
    username: str = ""
    saved_at: datetime | None = None
    collections: list[str] = field(default_factory=list)

    @property
    def item_key(self) -> str:   # same key the bot uses for pasted links, so they dedupe
        return f"ig:{self.code}"


@dataclass
class Parsed:
    items: list[Item]
    collections: list[str]
    files: list[str]


def _post(href: str) -> tuple[str, str, str] | None:
    m = POST_RE.search(href or "")
    if not m:
        return None
    kind = "post" if m["kind"] == "p" else "reel"
    url = f"https://www.instagram.com/{'p' if kind == 'post' else 'reel'}/{m['code']}/"
    return m["code"], kind, url


def _when(ts) -> datetime | None:
    try:
        t = float(ts)
    except (TypeError, ValueError):
        return None
    if t > 1e11:          # milliseconds
        t /= 1000
    if not 946684800 < t < 4102444800:   # 2000..2100
        return None
    return datetime.fromtimestamp(t, tz=timezone.utc)


def _username(text: str) -> str:
    t = (text or "").strip().lstrip("@")
    return f"@{t}" if re.fullmatch(r"[A-Za-z0-9._]{1,30}", t) else ""


# ---------------------------------------------------------------- JSON
def _find_links(node, out: list[Item], hint_user: str = "") -> None:
    """Depth-first search for {href: post-url, timestamp} with a username nearby."""
    if isinstance(node, dict):
        user = _username(str(node.get("title", ""))) or hint_user
        href, ts = node.get("href"), node.get("timestamp")
        if isinstance(href, str) and (p := _post(href)):
            out.append(Item(*p, username=_username(str(node.get("value", ""))) or user, saved_at=_when(ts)))
        for v in node.values():
            _find_links(v, out, user)
    elif isinstance(node, list):
        # Old exports: ["username", {"href": ..., "timestamp": ...}]
        if len(node) == 2 and isinstance(node[0], str) and isinstance(node[1], dict):
            _find_links(node[1], out, _username(node[0]) or hint_user)
            return
        for v in node:
            _find_links(v, out, hint_user)


def _collections_json(data) -> tuple[list[str], dict[str, list[str]], dict[str, tuple[str, str]]]:
    """Collections come as a flat list: a header entry with the collection name, then its posts."""
    entries = []
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                entries.extend(v)
    elif isinstance(data, list):
        entries = data
    names: list[str] = []
    membership: dict[str, list[str]] = {}
    links: dict[str, tuple[str, str]] = {}
    current = ""
    for e in entries:
        if not isinstance(e, dict):
            continue
        smd = e.get("string_map_data") or {}
        name_field = smd.get("Name") or {}
        href = name_field.get("href") or ""
        p = _post(href)
        if p is None and not any(_post(str((v or {}).get("href", ""))) for v in smd.values() if isinstance(v, dict)):
            current = str(name_field.get("value") or e.get("title") or "").strip()[:40]
            if current and current not in names:
                names.append(current)
            continue
        if p is None:
            p = next(_post(str(v.get("href"))) for v in smd.values() if isinstance(v, dict) and _post(str(v.get("href", ""))))
        links[p[0]] = (p[1], p[2])
        if current:
            membership.setdefault(p[0], [])
            if current not in membership[p[0]]:
                membership[p[0]].append(current)
    return names, membership, links


# ---------------------------------------------------------------- HTML
def _links_html(html: str, out: list[Item]) -> None:
    for m in re.finditer(r'href="([^"]+)"[^>]*>([^<]*)<', html):
        if p := _post(unescape(m.group(1))):
            out.append(Item(*p, username=_username(unescape(m.group(2)))))


def _collections_html(html: str) -> tuple[list[str], dict[str, list[str]], dict[str, tuple[str, str]]]:
    names: list[str] = []
    membership: dict[str, list[str]] = {}
    links: dict[str, tuple[str, str]] = {}
    current = ""
    for m in re.finditer(r'href="([^"]+)"|<(?:h2|div)[^>]*class="[^"]*_2pin[^"]*"[^>]*>([^<]{1,60})</', html):
        if m.group(1) and (p := _post(unescape(m.group(1)))):
            links[p[0]] = (p[1], p[2])
            if current and current not in membership.setdefault(p[0], []):
                membership[p[0]].append(current)
        elif m.group(2):
            text = unescape(m.group(2)).strip()
            if text and not text.lower().startswith(("name", "added", "creation", "update")):
                current = text[:40]
                if current not in names:
                    names.append(current)
    return names, membership, links


# ---------------------------------------------------------------- entry point
def parse_export(data: bytes, filename: str = "") -> Parsed:
    if len(data) > MAX_UPLOAD:
        raise ImportProblem("That file is too big. In Instagram's download screen, choose only “Saved” so the file stays small.")
    files: dict[str, bytes] = {}
    if data[:4] == b"PK\x03\x04":
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise ImportProblem("That ZIP file is damaged. Download it from Instagram again.")
        for info in z.infolist():
            base = info.filename.rsplit("/", 1)[-1].lower()
            if base.startswith(("saved_posts", "saved_collections")) and base.endswith((".json", ".html")):
                if info.file_size > MAX_MEMBER:
                    raise ImportProblem("A file inside that ZIP is unexpectedly large. Download the export again with only “Saved”.")
                files[info.filename] = z.read(info)
    else:
        files[filename or "upload.json"] = data

    items: list[Item] = []
    names: list[str] = []
    membership: dict[str, list[str]] = {}
    links: dict[str, tuple[str, str]] = {}
    for name, raw in files.items():
        lower = name.lower()
        text = raw.decode("utf-8", errors="replace")
        is_coll = "saved_collections" in lower
        if lower.endswith(".html") or text.lstrip()[:1] == "<":
            if is_coll:
                n, mem, lk = _collections_html(text)
            else:
                _links_html(text, items)
                continue
        else:
            try:
                parsed = json.loads(text)
            except ValueError:
                raise ImportProblem(f"{name.rsplit('/', 1)[-1]} isn't valid JSON. Download the export again in JSON format.")
            if not is_coll:
                _find_links(parsed, items)
                continue
            n, mem, lk = _collections_json(parsed)
        links.update(lk)
        names += [x for x in n if x not in names]
        for code, cols in mem.items():
            membership.setdefault(code, []).extend(c for c in cols if c not in membership.get(code, []))

    by_code: dict[str, Item] = {}
    for it in items:
        if it.code in by_code:
            prev = by_code[it.code]
            prev.username = prev.username or it.username
            prev.saved_at = prev.saved_at or it.saved_at
        else:
            by_code[it.code] = it
    # Posts that only appear in a collection still count as saved.
    for code, cols in membership.items():
        if code not in by_code:
            kind, url = links.get(code, ("post", f"https://www.instagram.com/p/{code}/"))
            by_code[code] = Item(code, kind, url)
        by_code[code].collections = cols

    if not files:
        raise ImportProblem("No saved posts found in that file. Make sure you picked “Saved” when requesting your Instagram download.")
    if not by_code:
        raise ImportProblem("That file doesn't list any saved posts. Choose “Saved” and the JSON format in Instagram's download screen.")
    if len(by_code) > MAX_ITEMS:
        raise ImportProblem(f"That export lists more than {MAX_ITEMS:,} saves, which is more than one import can take.")
    return Parsed(list(by_code.values()), names, sorted(files))


# ---------------------------------------------------------------- saving into a library
def apply_import(db: Database, user_id: int, parsed: Parsed, file_name: str) -> dict:
    """Add the export's saves to the member's library. Collections become piles. Returns a summary."""
    with db.tx() as c:
        cur = c.execute("INSERT INTO imports(user_id, file_name, created_at, found) VALUES (?,?,?,?)",
                        (user_id, file_name[:120], now(), len(parsed.items)))
        import_id = cur.lastrowid
        boards = {r["name"].lower(): r["id"] for r in c.execute("SELECT id, name FROM boards WHERE user_id = ?", (user_id,))}
        created: list[int] = []
        for name in parsed.collections:
            if name.lower() not in boards:
                bid = c.execute("INSERT INTO boards(user_id, name, created_at) VALUES (?,?,?)", (user_id, name, now())).lastrowid
                boards[name.lower()] = bid
                created.append(bid)
        existing = {r["item_key"]: (r["id"], r["board_id"]) for r in c.execute(
            "SELECT id, item_key, board_id FROM saves WHERE user_id = ?", (user_id,))}
        added = dupes = piled = 0
        shelves: dict[str, int] = {}
        for it in parsed.items:
            board_id = boards.get(it.collections[0].lower()) if it.collections else None
            if it.item_key in existing:
                dupes += 1
                sid, current_board = existing[it.item_key]
                if board_id and current_board is None:   # already saved, but now we know its pile
                    c.execute("UPDATE saves SET board_id = ? WHERE id = ?", (board_id, sid))
                    piled += 1
                continue
            shelf = guess(" ".join([*it.collections, it.username.lstrip("@").replace(".", " ").replace("_", " ")]))
            shelves[shelf] = shelves.get(shelf, 0) + 1
            when = (it.saved_at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
            c.execute(
                "INSERT INTO saves(user_id, mid, kind, item_key, url, caption, creator, category, tags, status, progress,"
                " board_id, created_at, processed_at, import_id) VALUES (?,?,?,?,?,'',?,?,'','done','try',?,?,?,?)",
                (user_id, f"import-{import_id}-{it.code}", it.kind, it.item_key, it.url, it.username, shelf,
                 board_id, when, now(), import_id),
            )
            existing[it.item_key] = (None, board_id)
            added += 1
        c.execute("UPDATE imports SET added = ?, duplicates = ?, boards_created = ? WHERE id = ?",
                  (added, dupes, json.dumps(created), import_id))
    return {
        "id": import_id, "found": len(parsed.items), "added": added, "duplicates": dupes, "put_on_piles": piled,
        "piles_created": [n for n in parsed.collections if boards.get(n.lower()) in created],
        "shelves": dict(sorted(shelves.items(), key=lambda kv: (kv[0] == UNSORTED, -kv[1]))),
    }


def list_imports(db: Database, user_id: int) -> list[dict]:
    with db.connect() as c:
        rows = c.execute("SELECT id, file_name, created_at, found, added, duplicates, undone_at FROM imports "
                         "WHERE user_id = ? ORDER BY id DESC LIMIT 20", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def undo_import(db: Database, user_id: int, import_id: int) -> dict:
    """Remove the saves this import added, and the piles it created if they are now empty."""
    with db.tx() as c:
        imp = c.execute("SELECT * FROM imports WHERE id = ? AND user_id = ?", (import_id, user_id)).fetchone()
        if not imp:
            raise ImportProblem("That import doesn't exist.")
        if imp["undone_at"]:
            raise ImportProblem("That import was already undone.")
        removed = c.execute("DELETE FROM saves WHERE user_id = ? AND import_id = ?", (user_id, import_id)).rowcount
        piles = 0
        for bid in json.loads(imp["boards_created"] or "[]"):
            if not c.execute("SELECT 1 FROM saves WHERE board_id = ? LIMIT 1", (bid,)).fetchone():
                piles += c.execute("DELETE FROM boards WHERE id = ? AND user_id = ?", (bid, user_id)).rowcount
        c.execute("UPDATE imports SET undone_at = ? WHERE id = ?", (now(), import_id))
    return {"removed": removed, "piles_removed": piles}
