"""Print strong random values for a live server's secrets. Paste them into your host's environment settings.

    python scripts/make_secrets.py
"""
import secrets

print("# Generated for Stash. Keep these private; never commit them.")
print(f"SECRET_KEY={secrets.token_urlsafe(48)}")
print(f"ADMIN_TOKEN={secrets.token_urlsafe(32)}")
print(f"IG_VERIFY_TOKEN={secrets.token_urlsafe(24)}")
print("APP_ENV=production")
print("# Also set IG_APP_SECRET (from your Meta app) and PUBLIC_BASE_URL=https://your-domain")
