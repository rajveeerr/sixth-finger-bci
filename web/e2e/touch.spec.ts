import { devices, expect, test } from "@playwright/test";

// Every hover on the page has a tap path: a reference's card opens on the first tap, and
// what a pointer shows stays shown after a tap.
test.use({ ...devices["iPhone 13"] });

test("a tap opens a reference's card before its link, and a tapped trial stays named", async ({ page }) => {
  await page.goto("/?server=none");
  const ref = page.locator("#recordings .ref").first();
  await ref.scrollIntoViewIfNeeded();
  await ref.locator("a").tap();
  await expect(ref.locator(".ref-card")).toBeVisible();
  expect(new URL(page.url()).host).toMatch(/localhost/);

  const square = page.locator(".session-run").nth(2).locator("i").nth(4);
  await square.scrollIntoViewIfNeeded();
  await square.tap();
  await expect(page.locator(".session-say")).toContainText("Trial 45 of 80");
});

test("a tapped step of the patient's path says what happens in it, and the switch changes the practice", async ({
  page,
}) => {
  await page.goto("/?server=none");
  const path = page.locator("#journey");
  const cap = path.locator(".journey-step").first();
  await cap.scrollIntoViewIfNeeded();
  await cap.tap();
  await expect(path.locator(".journey-say-narrow")).toContainText("headset streaming live");
  const dayOne = path.locator("[data-group=day-1]");
  await expect(dayOne).toContainText("about 5 min");
  await path.getByRole("radio", { name: "Already learned from other patients" }).tap();
  await expect(dayOne).toContainText("about 30 s");
});

test("Space scrolls the page away from the demo instead of pausing it", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto("/?server=none");
  await page.keyboard.press(" ");
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
});
