import { expect, test } from "@playwright/test";
import { newMember, signIn } from "./helpers";

test.beforeEach(async ({ page }) => {
  await signIn(page, newMember().links[0]);
});

test("Capsule: keep, let go with the keyboard, later", async ({ page }) => {
  await page.locator(".dock-btn", { hasText: "Capsule" }).click();
  const progress = page.locator(".capsule-progress b");
  await expect(progress).toHaveText(/^1 \/ \d+$/);
  await page.locator(".verdicts").getByRole("button", { name: "Keep" }).click();
  await expect(progress).toHaveText(/^2 \/ /);
  await page.keyboard.press("ArrowLeft");
  await expect(progress).toHaveText(/^3 \/ /);
  await page.locator(".verdicts").getByRole("button", { name: "Later" }).click();
  await expect(page.locator(".toast")).toContainText("Back on Saturday");
});

test("Plan: drag onto a day, tap then tap, drag back to Someday", async ({ page }) => {
  await page.locator(".dock-btn", { hasText: "Plan" }).click();
  const pile = page.locator(".someday-row .reel");
  await expect(pile.first()).toBeVisible();       // count() doesn't wait: let the week load first
  const start = await pile.count();
  await pile.first().dragTo(page.locator(".day").nth(1));
  await expect(pile).toHaveCount(start - 1);
  await pile.first().click();
  await page.locator(".day").nth(2).click();
  await expect(pile).toHaveCount(start - 2);
  await page.locator(".slip").first().dragTo(page.locator(".someday"));
  await expect(pile).toHaveCount(start - 1);
});

test("Piles: stacks, a moodboard inside, create and rename", async ({ page }) => {
  await page.locator(".dock-btn", { hasText: "Piles" }).click();
  await expect(page.locator(".pile", { hasText: "Goa trip" })).toBeVisible();
  await page.locator(".pile", { hasText: "Goa trip" }).click();
  await expect(page.locator(".moodboard .tile")).toHaveCount(3);
  await page.getByRole("button", { name: "Rename" }).click();
  await page.fill("#pilename", "Goa 2027");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.locator(".pile-head h1")).toHaveText("Goa 2027");
  await page.locator(".moodboard .tile").first().click();
  await expect(page.locator(".viewer .viewer-head")).toBeVisible();
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "All piles" }).click();
  await page.locator(".pile.new").click();
  await page.fill("#pilename", "Weekend ideas");
  await page.getByRole("button", { name: "Make pile" }).click();
  await expect(page.locator(".pile-head h1")).toHaveText("Weekend ideas");
});
