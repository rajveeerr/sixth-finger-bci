import { expect, test } from "@playwright/test";

// A server that cannot answer (port 9 is closed), so the test does not depend on
// whether an inference server happens to be running.
const NO_SERVER = "server=http://127.0.0.1:9";

test("without a server the demo decodes in the browser and moves the hand", async ({ page }) => {
  await page.goto(`/?speed=8&${NO_SERVER}`);
  await expect(page.getByTestId("mode-badge")).toHaveAttribute("data-source", "browser", { timeout: 15_000 });
  // The first decision comes after 5 s of data (rest window), so at speed 8 within ~1 s.
  await expect(page.getByTestId("prediction")).not.toHaveAttribute("data-label", "", { timeout: 10_000 });
  await expect(page.getByTestId("prediction")).toContainText("Decided in this browser");
  await expect(page.getByTestId("hand")).not.toHaveAttribute("data-command", "IDLE", { timeout: 15_000 });
});

test("a site built without a server goes straight to the in-browser model", async ({ page }) => {
  await page.goto("/?speed=8&server=none");
  await expect(page.getByTestId("mode-badge")).toHaveAttribute("data-source", "browser", { timeout: 15_000 });
  await expect(page.getByTestId("prediction")).not.toHaveAttribute("data-label", "", { timeout: 10_000 });
  await expect(page.getByRole("button", { name: "Try the server again" })).toHaveCount(0);
});

test("the one-switch view flexes the sixth finger for any imagery", async ({ page }) => {
  await page.goto(`/?speed=8&${NO_SERVER}`);
  await page.getByRole("radio", { name: "On/off switch" }).click();
  await expect(page.getByTestId("prediction")).toHaveAttribute("data-view", "switch");
  await expect(page.getByTestId("hand")).toHaveAttribute("data-command", "SIXTH_FINGER_FLEX", { timeout: 20_000 });
  await expect(page.getByTestId("prediction")).toContainText("windows right, rest and imagery");
});

test("keys 1-3 pose the hand under a manual-test banner, Esc returns", async ({ page }) => {
  await page.goto(`/?${NO_SERVER}`);
  await expect(page.getByTestId("mode-badge")).toHaveAttribute("data-source", "browser", { timeout: 15_000 });
  await page.keyboard.press("2");
  await expect(page.getByTestId("manual-banner")).toBeVisible();
  await expect(page.getByTestId("hand")).toHaveAttribute("data-command", "HAND_GRASP");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("manual-banner")).toBeHidden();
});
