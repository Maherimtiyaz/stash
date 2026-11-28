import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { newMember, signIn } from "./helpers";

const HERE = dirname(fileURLToPath(import.meta.url));
const EXPORT = join(HERE, "fixtures", "instagram-export.zip");   // made by fixtures/make_export.py
const NOT_AN_EXPORT = join(HERE, "fixtures", "not-an-export.txt");

test("import an Instagram export, re-import nothing, undo it", async ({ page }) => {
  await signIn(page, newMember().links[0]);
  const total = page.locator(".count.c1 b");
  await expect(total).toHaveText("17");

  await page.getByRole("button", { name: /Import from Instagram/ }).click();
  await page.setInputFiles("#import-file", EXPORT);
  const result = page.locator(".import-result");
  await expect(result.locator("h3")).toHaveText("Added 300 saves");
  await expect(result).toContainText("New piles from your collections: Recipes, Gym, Tech stuff");   // "Goa trip" already existed
  await expect(result.locator(".shelf-dot", { hasText: "Unsorted" })).toBeVisible();
  await result.getByRole("button", { name: "See my stash" }).click();
  await expect(total).toHaveText("317");

  await page.getByRole("button", { name: /Import from Instagram/ }).click();
  await page.setInputFiles("#import-file", EXPORT);
  await expect(result.locator("h3")).toHaveText("Nothing new to add");

  const earlier = page.locator(".upcoming li").first();
  await earlier.getByRole("button", { name: "Undo" }).click();
  await earlier.locator(".danger-btn").click();
  await expect(page.locator(".toast")).toContainText("removed 300 saves");
  await page.getByRole("button", { name: "Close" }).click();
  await expect(total).toHaveText("17");
});

test("a wrong file is explained", async ({ page }) => {
  await signIn(page, newMember().links[0]);
  await page.fill("#q", "/import");
  await page.keyboard.press("Enter");
  await page.setInputFiles("#import-file", NOT_AN_EXPORT);
  await expect(page.locator(".notice")).toContainText("isn't valid JSON");
});
