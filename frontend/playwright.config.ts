import { defineConfig, devices } from "@playwright/test";

const CI = !!process.env.CI;

// Browser tests against the real server (started by e2e/server.mjs on a fresh database).
// Build the web app first: npm run build. Each test creates its own demo member, so tests can run in parallel.
export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  workers: CI ? 2 : undefined,
  retries: CI ? 1 : 0,
  forbidOnly: CI,
  reporter: CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://127.0.0.1:8765",
    trace: CI ? "retain-on-failure" : "off",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } }, testIgnore: /phone\.spec/ },
    { name: "phone", use: { ...devices["Pixel 7"] }, testMatch: /phone\.spec/ },
  ],
  webServer: {
    command: "node e2e/server.mjs",
    url: "http://127.0.0.1:8765/healthz",
    reuseExistingServer: !CI,
    timeout: 60_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});
