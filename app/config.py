import os
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Settings:
    app_secret: str = ""
    verify_token: str = ""
    access_token: str = ""
    ig_username: str = "stash"
    graph_version: str = "v21.0"
    admin_token: str = ""
    secret_key: str = "dev-secret"
    public_base_url: str = "http://localhost:8000"
    db_path: str = "stash.db"
    worker_enabled: bool = True
    link_code_minutes: int = 30
    frontend_dist: str = ""     # folder with the built web app; empty disables /app
    app_env: str = "development"   # "production" turns on strict checks and HSTS
    rate_limits: bool = True
    trust_proxy: bool = False      # read the visitor's IP from X-Forwarded-For (only behind your own proxy)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def dry_run(self) -> bool:
        """No access token means replies are logged instead of sent to Instagram."""
        return not self.access_token

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ.get
        return cls(
            app_secret=e("IG_APP_SECRET", ""),
            verify_token=e("IG_VERIFY_TOKEN", ""),
            access_token=e("IG_ACCESS_TOKEN", ""),
            ig_username=e("IG_USERNAME", "stash"),
            graph_version=e("GRAPH_VERSION", "v21.0"),
            admin_token=e("ADMIN_TOKEN", ""),
            secret_key=e("SECRET_KEY", "dev-secret"),
            public_base_url=e("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/"),
            db_path=e("DB_PATH", "stash.db"),
            worker_enabled=e("WORKER_ENABLED", "1") == "1",
            frontend_dist=e("FRONTEND_DIST", str(Path(__file__).resolve().parents[1] / "frontend" / "dist")),
            app_env=e("APP_ENV", "development").strip().lower(),
            rate_limits=e("RATE_LIMITS", "1") == "1",
            trust_proxy=e("TRUST_PROXY", "0") == "1",
        )
