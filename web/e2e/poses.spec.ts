import { expect, test } from "@playwright/test";

// The hand in each command's pose, for the report (scripts/make_hand_poses_figure.py puts
// the three side by side).
const POSES = [
  { key: "1", command: "IDLE" },
  { key: "2", command: "HAND_GRASP" },
  { key: "3", command: "SIXTH_FINGER_FLEX" },
];

for (const style of ["iso"] as const) {
  test(`the ${style} hand takes each command's pose`, async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto("/?server=http://127.0.0.1:9");
    await expect(page.getByTestId("mode-badge")).toHaveAttribute("data-source", "browser", { timeout: 15_000 });
    await expect(page.locator("[data-testid=hand] svg")).toBeVisible({ timeout: 10_000 });
    for (const { key, command } of POSES) {
      await page.keyboard.press(key);
      await expect(page.getByTestId("hand")).toHaveAttribute("data-command", command);
      await page.waitForTimeout(900); // the springs settle in about 0.5 s
      await page.getByTestId("hand").screenshot({ path: `test-results/hand-${style}-${command}.png` });
    }
  });
}
