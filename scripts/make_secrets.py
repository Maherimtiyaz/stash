"""Print strong random values for a live server's secrets. Paste them into your host's environment settings.

    python scripts/make_secrets.py
"""
import base64
import secrets

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


# Web Push (phone/browser notifications) needs a P-256 key pair, called VAPID keys.
vapid = ec.generate_private_key(ec.SECP256R1())
vapid_public = vapid.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

print("# Generated for Stash. Keep these private; never commit them.")
print(f"SECRET_KEY={secrets.token_urlsafe(48)}")
print(f"ADMIN_TOKEN={secrets.token_urlsafe(32)}")
print(f"IG_VERIFY_TOKEN={secrets.token_urlsafe(24)}")
print(f"VAPID_PRIVATE_KEY={b64(vapid.private_numbers().private_value.to_bytes(32, 'big'))}")
print(f"VAPID_PUBLIC_KEY={b64(vapid_public)}")
print("APP_ENV=production")
print("# Also set IG_APP_SECRET (from your Meta app), PUBLIC_BASE_URL=https://your-domain,")
print("# VAPID_SUBJECT=mailto:you@your-domain, and SMTP_* for email reminders (see README).")
