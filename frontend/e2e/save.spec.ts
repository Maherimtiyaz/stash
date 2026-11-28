import { expect, test } from "@playwright/test";
import { api, newMember, signIn } from "./helpers";

interface Save { id: number; progress: string; plan_day: string | null; board_name: string | null; note: string; category: string }

test("the save view updates status, plan, pile, shelf and note", async ({ page }) => {
  await signIn(page, newMember().links[0]);
  await page.fill("#q", "scuba");
  await page.keyboard.press("Enter");
  const viewer = page.locator(".viewer");
  await expect(viewer.locator(".viewer-head h2")).toContainText("Scuba");

  await viewer.getByRole("button", { name: "I tried it" }).click();
  await expect(page.locator(".toast")).toContainText("Marked as tried");
  await viewer.locator(".ticket").nth(2).click();                         // plan two days from now
  await viewer.getByRole("button", { name: "New pile" }).click();
  await viewer.getByLabel("New pile name").fill("Weekend plans");
  await viewer.getByRole("button", { name: "Make it" }).click();
  await expect(viewer.locator(".stk.on")).toHaveText("Weekend plans");
  await viewer.locator(".shelf-dot", { hasText: "Gym & Fitness" }).click();
  await viewer.locator("#note").fill("Book 2 days ahead");
  await viewer.locator(".viewer-head").click();                           // blur saves the note
  await expect(page.locator(".toast")).toContainText("Note saved");

  const [s] = (await api<{ results: Save[] }>(page, "/saves?q=scuba")).results;
  expect(s.progress).toBe("done");
  expect(s.plan_day).not.toBeNull();
  expect(s.board_name).toBe("Weekend plans");
  expect(s.category).toBe("Fitness");
  expect(s.note).toBe("Book 2 days ahead");

  await viewer.getByRole("button", { name: "Close" }).click();
  await expect(viewer).toHaveCount(0);
});

test("deleting a save asks first", async ({ page }) => {
  await signIn(page, newMember().links[0]);
  await page.fill("#q", "sneakers");
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Delete from stash" }).click();
  await page.getByRole("button", { name: "Keep it" }).click();
  await page.getByRole("button", { name: "Delete from stash" }).click();
  await page.locator(".danger").getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page.locator(".toast")).toContainText("Deleted");
  expect((await api<{ results: Save[] }>(page, "/saves?q=sneakers")).results).toHaveLength(0);
});
