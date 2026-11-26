import { execFileSync } from "node:child_process";
import { expect, type Page } from "@playwright/test";
import { BASE, ENV, PYTHON, ROOT } from "./env.mjs";

export interface Member { user_id: number; igsid: string; links: string[]; saves: number }

const run = (args: string[]) =>
  execFileSync(PYTHON, args, { cwd: ROOT, env: { ...process.env, ...ENV }, encoding: "utf8" });

/** A fresh demo member (17 sample saves, 5 piles) with single-use sign-in links. Every test gets its own. */
export function newMember(links = 3): Member {
  return JSON.parse(run(["scripts/seed_demo.py", "--json", "--links", String(links)]));
}

/** Open the app with a sign-in link and wait for Home. */
export async function signIn(page: Page, link: string) {
  await page.goto(link);
  await expect(page.locator(".shelf .reel").first()).toBeVisible();
}

/** Act as Instagram: send a signed webhook for a DM from this member. */
export function dm(member: Member, kind: "reel" | "text" | "link" | "code", value: string) {
  return run(["scripts/simulate.py", kind, value, "--sender", member.igsid, "--url", BASE]);
}

/** Messages the bot has queued or sent to this member, oldest first. */
export function replies(member: Member): string[] {
  const out = run(["-c", [
    "import json, os, sqlite3, sys",
    "c = sqlite3.connect(os.environ['DB_PATH'])",
    "print(json.dumps([r[0] for r in c.execute('SELECT text FROM outbox WHERE igsid = ? ORDER BY id', (sys.argv[1],))]))",
  ].join("\n"), member.igsid]);
  return JSON.parse(out);
}

/** Wait for the bot's next reply after `before` replies, and return it. */
export async function nextReply(member: Member, before: number): Promise<string> {
  await expect.poll(() => replies(member).length, { timeout: 10_000 }).toBeGreaterThan(before);
  return replies(member)[before];
}

/** Call the API as the signed-in page. */
export async function api<T = unknown>(page: Page, path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  return page.evaluate(async ([path, method, body]) => {
    const t = localStorage.getItem("stash_token");
    const r = await fetch(`/api/v1${path}`, {
      method: method || "GET",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${t}` },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return r.json();
  }, [path, init.method, init.body] as const) as Promise<T>;
}
