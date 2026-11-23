"""Request limits and security headers."""
import re
import threading
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings

# (method or "*", path pattern, requests allowed per minute per visitor)
# First match wins. Tight limits where guessing is possible; generous ones elsewhere.
RULES: list[tuple[str, re.Pattern, int]] = [
    ("POST", re.compile(r"^/api/v1/session$"), 10),     # swapping sign-in links
    ("POST", re.compile(r"^/i/[^/]+$"), 10),            # accepting invites
    ("*", re.compile(r"^/api/admin/"), 60),             # admin API (also slows token guessing)
    ("*", re.compile(r"^/(i/[^/]+|welcome|library|api/me)$"), 60),
    ("*", re.compile(r"^/api/v1/"), 300),               # the web app
    ("POST", re.compile(r"^/webhooks/instagram$"), 1200),  # Meta; only a safety net
]
WINDOW = 60.0


class RateLimiter:
    """Sliding-window counter kept in memory. One process only; use Redis when running several."""

    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str, limit: int) -> float:
        """Records a hit. Returns 0 when allowed, otherwise seconds until the next request is allowed."""
        t = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= t - WINDOW:
                q.popleft()
            if len(q) >= limit:
                return max(0.0, q[0] + WINDOW - t)
            q.append(t)
            if len(self.hits) > 50_000:  # drop idle keys so memory stays bounded
                for k in [k for k, v in self.hits.items() if not v or v[-1] <= t - WINDOW][:10_000]:
                    del self.hits[k]
            return 0.0


def client_ip(request: Request, trust_proxy: bool) -> str:
    if trust_proxy:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


APP_CSP = (
    "default-src 'self'; script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


def install(app: FastAPI, s: Settings) -> None:
    limiter = RateLimiter()
    app.state.limiter = limiter

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path, method = request.url.path, request.method
        if s.rate_limits:
            for m, pattern, limit in RULES:
                if (m == "*" or m == method) and pattern.match(path):
                    key = f"{pattern.pattern}|{client_ip(request, s.trust_proxy)}"
                    wait = limiter.check(key, limit)
                    if wait:
                        return JSONResponse({"detail": "Too many requests. Wait a minute and try again."},
                                            status_code=429, headers={"Retry-After": str(int(wait) + 1)})
                    break
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "no-referrer")          # sign-in links never leak to other sites
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if path == "/app" or path.startswith("/app/"):
            h.setdefault("Content-Security-Policy", APP_CSP)
        if path.startswith("/api/") or path in ("/welcome", "/library"):
            h.setdefault("Cache-Control", "no-store")             # personal data stays out of caches
        if s.is_production:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

