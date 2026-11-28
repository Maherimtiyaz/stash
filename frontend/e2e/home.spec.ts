import { expect, test } from "@playwright/test";
import { newMember, signIn } from "./helpers";

test.beforeEach(async ({ page }) => {
  await signIn(page, newMember().links[0]);
});

test("saves are sorted onto shelves, in order, with chips to filter", async ({ page }) => {
  const shelves = page.locator(".shelf .shelf-name");
  await expect(shelves).toHaveText(["Tech", "Travel", "Recipes", "Gym & Fitness", "Fashion", "Health", "Home"]);
  await expect(page.locator(".shelf-chip")).toHaveCount(7);
  await expect(page.locator(".shelf", { has: page.locator(".shelf-name", { hasText: /^Travel$/ }) }).locator(".reel")).toHaveCount(4);

  await page.locator(".shelf-chip", { hasText: "Gym" }).click();
  await expect(page.locator("#q")).toHaveValue("in:Fitness");
  await expect(page.locator(".shelf .reel")).toHaveCount(2);
});

test("search finds captions, tags and notes, grouped by shelf", async ({ page }) => {
  await page.fill("#q", "goa");
  await expect(page.locator(".hits")).toContainText("3 saves found");
  await expect(page.locator(".shelf .shelf-name")).toHaveText(["Travel"]);
  await expect(page.locator(".rest .pill")).toHaveText(/Show the other \d+ saves/);

  await page.fill("#q", "sunset");                       // only in a note
  await expect(page.locator(".hits")).toContainText("1 save found");

  await page.fill("#q", "sushi");
  await expect(page.locator(".hits")).toContainText("Nothing matches");
});

test("Newest switch shows one wall of every save", async ({ page }) => {
  await page.getByRole("button", { name: "Newest" }).click();
  await expect(page.locator(".wall .reel")).toHaveCount(17);
  await page.getByRole("button", { name: "By shelf" }).click();
  await expect(page.locator(".shelf").first()).toBeVisible();
});

test("the / command menu filters and navigates", async ({ page }) => {
  await page.fill("#q", "/");
  await expect(page.locator(".cmd").first()).toBeVisible();
  await page.fill("#q", "/tech");
  await page.keyboard.press("Enter");
  await expect(page.locator("#q")).toHaveValue("in:Tech");

  await page.fill("#q", "/plan");
  await page.keyboard.press("Enter");
  await expect(page.locator(".week")).toBeVisible();
});
