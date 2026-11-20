"""Everything that knows Instagram's webhook and Send API formats lives here.

Payload shapes follow Meta's Instagram Messaging webhook docs. The exact fields on a
shared reel (`ig_reel`) are the first thing to confirm against a real webhook; the
parser is deliberately tolerant so a field rename degrades to "link only" instead of
crashing.
"""
import hashlib
import hmac
import logging
import re
from dataclasses import dataclass, field

import httpx

log = logging.getLogger("stash.instagram")

IG_URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?P<kind>reel|reels|p|tv)/(?P<code>[A-Za-z0-9_-]+)", re.I
)


@dataclass
class Share:
    kind: str          # reel | post | link
    item_key: str      # stable ID for dedupe
    url: str = ""
    caption: str = ""


@dataclass
class Incoming:
    mid: str
    sender: str
    recipient: str
    text: str = ""
    is_echo: bool = False
    shares: list[Share] = field(default_factory=list)


def verify_signature(raw_body: bytes, header: str | None, app_secret: str) -> bool:
    """Meta signs each POST with HMAC-SHA256 of the raw body using the app secret."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def _shares_from_text(text: str) -> list[Share]:
    out = []
    for m in IG_URL_RE.finditer(text or ""):
        kind = "post" if m["kind"].lower() == "p" else "reel"
        out.append(Share(kind=kind, item_key=f"ig:{m['code']}", url=m.group(0)))
    return out


def _share_from_attachment(att: dict) -> Share | None:
    a_type = (att.get("type") or "").lower()
    p = att.get("payload") or {}
    url = p.get("url") or ""
    caption = p.get("title") or ""
    if a_type == "ig_reel":
        rid = p.get("reel_video_id") or ""
        key = f"reel:{rid}" if rid else (f"url:{url.split('?')[0]}" if url else "")
        return Share("reel", key, url, caption) if key else None
    if a_type in ("share", "ig_post"):
        found = _shares_from_text(url)
        if found:
            found[0].caption = caption
            return found[0]
        return Share("post", f"url:{url.split('?')[0]}", url, caption) if url else None
    return None  # images, audio, story mentions, reactions: ignored for now


def parse_webhook(payload: dict) -> list[Incoming]:
    """Flatten Meta's entry[].messaging[] envelope into Incoming messages."""
    out: list[Incoming] = []
    if payload.get("object") != "instagram":
        return out
    for entry in payload.get("entry", []):
        for ev in entry.get("messaging", []):
            msg = ev.get("message")
            if not msg or msg.get("is_deleted"):
                continue
            text = msg.get("text") or ""
            shares = [s for s in (_share_from_attachment(a) for a in msg.get("attachments", [])) if s]
            shares += _shares_from_text(text)
            # Same item shared twice in one message → keep one.
            uniq = {s.item_key: s for s in shares}
            out.append(Incoming(
                mid=msg.get("mid", ""),
                sender=(ev.get("sender") or {}).get("id", ""),
                recipient=(ev.get("recipient") or {}).get("id", ""),
                text=text.strip(),
                is_echo=bool(msg.get("is_echo")),
                shares=list(uniq.values()),
            ))
    return out


class Messenger:
    def send_text(self, igsid: str, text: str) -> None:
        raise NotImplementedError


class DryRunMessenger(Messenger):
    """Records replies instead of sending them. Used locally and in tests."""

    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send_text(self, igsid: str, text: str) -> None:
        log.info("DRY-RUN reply to %s: %s", igsid, text)
        self.sent.append((igsid, text))


class GraphMessenger(Messenger):
    """Sends via the Instagram API with Instagram Login (graph.instagram.com)."""

    def __init__(self, access_token: str, version: str):
        self.url = f"https://graph.instagram.com/{version}/me/messages"
        self.client = httpx.Client(timeout=10, headers={"Authorization": f"Bearer {access_token}"})

    def send_text(self, igsid: str, text: str) -> None:
        r = self.client.post(self.url, json={"recipient": {"id": igsid}, "message": {"text": text[:1000]}})
        if r.status_code >= 400:
            raise RuntimeError(f"Send API {r.status_code}: {r.text[:300]}")
