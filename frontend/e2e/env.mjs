// Shared by the test server and the test helpers.
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
export const PORT = 8765;
export const BASE = `http://127.0.0.1:${PORT}`;
export const DATA = join(ROOT, "frontend", "e2e", ".data");
export const PYTHON = process.env.PYTHON || (existsSync(join(ROOT, ".venv/bin/python")) ? join(ROOT, ".venv/bin/python") : "python");
export const ENV = {
  DB_PATH: join(DATA, "e2e.db"),
  SECRET_KEY: "e2e-only-secret-key-not-for-real-use-0123",
  IG_APP_SECRET: "e2e-app-secret",
  IG_VERIFY_TOKEN: "e2e-only-verify-token",
  ADMIN_TOKEN: "e2e-only-admin-token-0123456789",
  PUBLIC_BASE_URL: BASE,
  WORKER_ENABLED: "1",
  RATE_LIMITS: "0", // many sign-ins from one machine; limits have their own backend tests
  DEFAULT_TIMEZONE: "UTC",
};
