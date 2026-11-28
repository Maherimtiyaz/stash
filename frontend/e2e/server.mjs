// Starts the real FastAPI server on a fresh database for the browser tests (run by playwright.config.ts).
import { spawn } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { DATA, ENV, PORT, PYTHON, ROOT } from "./env.mjs";

rmSync(DATA, { recursive: true, force: true });
mkdirSync(DATA, { recursive: true });
const server = spawn(PYTHON, ["-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", String(PORT)], {
  cwd: ROOT,
  env: { ...process.env, ...ENV },
  stdio: "inherit",
});
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => server.kill(sig));
server.on("exit", (code) => process.exit(code ?? 0));
