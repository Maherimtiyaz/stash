import { expect, test } from "@playwright/test";
import { newMember, signIn } from "./helpers";

// Runs in the "phone" project (Pixel 7 size and touch).
test.beforeEach(async ({ page }) => {
  await signIn(page, newMember().links[0]);
});

const noSidewaysScroll = (page: import("@playwright/test").Page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test("home fits the screen and the dock is reachable", async ({ page }) => {
  expect(await noSidewaysScroll(page)).toBe(true);
  await expect(page.locator(".dock-btn", { hasText: "Plan" })).toBeVisible();
});

test("a save opens at the top with its close button visible", async ({ page }) => {
  await page.locator(".shelf .reel").nth(1).click();
  const close = page.locator(".viewer .close");
  await expect(close).toBeInViewport();
  const box = await close.boundingBox();
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.y).toBeLessThan(120);
});

test("Capsule buttons sit above the dock", async ({ page }) => {
  await page.locator(".dock-btn", { hasText: "Capsule" }).click();
  const buttons = await page.locator(".verdicts").boundingBox();
  const dock = await page.locator(".dock").boundingBox();
  expect(buttons!.y + buttons!.height).toBeLessThanOrEqual(dock!.y);
});

test("Reminders and Import panels fit the screen", async ({ page }) => {
  await page.getByRole("button", { name: "Reminders" }).click();
  await expect(page.locator(".channels")).toBeVisible();
  expect(await noSidewaysScroll(page)).toBe(true);
  await page.getByRole("button", { name: "Close" }).click();
  await page.fill("#q", "/import");
  await page.keyboard.press("Enter");
  await expect(page.locator(".dropzone")).toBeVisible();
  expect(await noSidewaysScroll(page)).toBe(true);
});
