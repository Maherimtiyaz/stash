"""Send signed fake Instagram webhooks to a running Stash server.

Usage (server running with the same IG_APP_SECRET):
    python scripts/simulate.py code  STASH-ABC123          # DM a link code
    python scripts/simulate.py reel  "Paneer wrap #recipe"  # share a reel with this caption
    python scripts/simulate.py link  https://www.instagram.com/reel/Cxyz123/
    python scripts/simulate.py text  WAITLIST
Options: --sender 1789... (fake IGSID)  --url http://localhost:8000
"""
import argparse
import hashlib
import hmac
import json
import os
import time
import uuid

import httpx


def build(sender: str, kind: str, value: str) -> dict:
    msg: dict = {"mid": f"sim_{uuid.uuid4().hex}"}
    if kind == "reel":
        msg["attachments"] = [{"type": "ig_reel", "payload": {
            "reel_video_id": str(uuid.uuid4().int)[:17],
            "title": value,
            "url": "https://lookaside.fbsbx.com/ig_messaging_cdn/?asset_id=demo",
        }}]
    else:
        msg["text"] = value
    return {"object": "instagram", "entry": [{"id": "17841400000000000", "time": int(time.time() * 1000),
            "messaging": [{"sender": {"id": sender}, "recipient": {"id": "17841400000000000"},
                           "timestamp": int(time.time() * 1000), "message": msg}]}]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["code", "reel", "link", "text"])
    ap.add_argument("value")
    ap.add_argument("--sender", default="1790000000000001")
    ap.add_argument("--url", default="http://localhost:8000")
    a = ap.parse_args()
    body = json.dumps(build(a.sender, a.kind, a.value)).encode()
    secret = os.environ.get("IG_APP_SECRET", "")
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    r = httpx.post(f"{a.url}/webhooks/instagram", content=body,
                   headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig})
    print(r.status_code, r.text)


if __name__ == "__main__":
    main()
