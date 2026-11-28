import { expect, test } from "@playwright/test";
import { api, dm, newMember, nextReply, replies, signIn } from "./helpers";

interface Save { board_name: string | null; note: string; remind_at: string | null; progress: string }

test("a reel plus DM commands is filed, confirmed and shown in the app", async ({ page }) => {
  const m = newMember();
  await signIn(page, m.links[0]);
  let n = replies(m).length;
  dm(m, "reel", "Sunset kayaking in Goa #travel");
  expect(await nextReply(m, n)).toMatch(/^Saved to Travel ✓/);

  n = replies(m).length;
  dm(m, "text", "#goa-trip remind sat 7pm note: book 2 days ahead");
  const reply = await nextReply(m, n);
  expect(reply).toContain("Got it for “Sunset kayaking in Goa”");
  expect(reply).toMatch(/pile “Goa trip” · reminder Sat \d+ \w+, 19:00 · note saved/);

  const [s] = (await api<{ results: Save[] }>(page, "/saves?q=kayaking")).results;
  expect(s.board_name).toBe("Goa trip");
  expect(s.note).toBe("book 2 days ahead");
  expect(s.remind_at).not.toBeNull();

  n = replies(m).length;
  dm(m, "text", "done");
  expect(await nextReply(m, n)).toContain("marked tried ✓");
});

test("find, help and an unreadable time", async () => {
  const m = newMember();
  let n = replies(m).length;
  dm(m, "text", "find pasta");
  expect(await nextReply(m, n)).toMatch(/^Found in your stash:\n1\. Lemon garlic pasta/);
  n = replies(m).length;
  dm(m, "text", "help");
  expect(await nextReply(m, n)).toContain("remind sat 7pm");
  n = replies(m).length;
  dm(m, "reel", "Lemon tart");
  await nextReply(m, n);
  n = replies(m).length;
  dm(m, "text", "remind someday");
  expect(await nextReply(m, n)).toContain("couldn't read that time");
});

test("a due reminder arrives by DM and its link opens the save on another device", async ({ page, browser }) => {
  const m = newMember(2);
  await signIn(page, m.links[0]);
  const [s] = (await api<{ results: { id: number }[] }>(page, "/saves?q=paneer")).results;
  const n = replies(m).length;
  await api(page, `/saves/${s.id}`, { method: "PATCH", body: { remind_at: new Date(Date.now() - 60_000).toISOString() } });
  const reply = await nextReply(m, n);
  expect(reply).toContain("Reminder: 15-min paneer bhurji wrap");
  const link = reply.match(/http\S+&open=\d+/)?.[0];
  expect(link).toBeTruthy();

  const phone = await (await browser.newContext()).newPage();
  await phone.goto(link!);
  await expect(phone.locator(".viewer .viewer-head h2")).toContainText("paneer");
  await expect(phone).not.toHaveURL(/open=|t=/);
});

test("Reminders panel: DM window, email, test message", async ({ page }) => {
  await signIn(page, newMember().links[0]);
  await page.getByRole("button", { name: "Reminders" }).click();
  await expect(page.locator(".channel").first()).toContainText("Open");
  await page.fill("#remind-email", "priya@example.com");
  await page.locator(".email-row").getByRole("button", { name: "Save" }).click();
  await expect(page.locator(".toast")).toContainText("Email saved");
  await page.getByRole("button", { name: "Send me a test" }).click();
  await expect(page.locator(".test-results")).toContainText("Instagram DM: sent");
  await expect(page.locator(".test-results")).toContainText("Email: sent");
});
