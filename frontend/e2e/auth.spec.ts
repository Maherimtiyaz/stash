import { expect, test } from "@playwright/test";
import { api, newMember, signIn } from "./helpers";

test("a sign-in link works once, then the session carries on", async ({ page, browser }) => {
  const m = newMember();
  await signIn(page, m.links[0]);
  await expect(page).not.toHaveURL(/t=/);                                     // link removed from the address bar
  expect(await page.evaluate(() => localStorage.getItem("stash_token"))).toMatch(/^s_/);  // a session, not the link
  await page.reload();
  await expect(page.locator(".shelf .reel").first()).toBeVisible();            // still signed in

  const other = await (await browser.newContext()).newPage();
  await other.goto(m.links[0]);                                                // same link again
  await expect(other.locator(".notice")).toContainText("already used");
  await other.fill("#link", m.links[1]);                                       // paste a fresh one
  await other.getByRole("button", { name: "Open my stash" }).click();
  await expect(other.locator(".shelf .reel").first()).toBeVisible();
});

test("sign out ends the session on the server", async ({ page }) => {
  const m = newMember();
  await signIn(page, m.links[0]);
  const token = await page.evaluate(() => localStorage.getItem("stash_token"));
  await page.locator(".signout").click();
  await expect(page.locator(".signin-card")).toBeVisible();
  const status = await page.evaluate(async (t) => (await fetch("/api/v1/me", { headers: { Authorization: `Bearer ${t}` } })).status, token);
  expect(status).toBe(401);
});

test("visitors without a link see the sign-in page, forged links are refused", async ({ page }) => {
  await page.goto("/app/");
  await expect(page.locator(".signin-card")).toBeVisible();
  await page.goto("/app/?t=l_forged-link-value");
  await expect(page.locator(".notice")).toContainText("expired or was already used");
});

test("the app sends the device time zone", async ({ browser }) => {
  const m = newMember();
  const page = await (await browser.newContext({ timezoneId: "America/Los_Angeles" })).newPage();
  await signIn(page, m.links[0]);
  expect((await api<{ timezone: string }>(page, "/me")).timezone).toBe("America/Los_Angeles");
});
