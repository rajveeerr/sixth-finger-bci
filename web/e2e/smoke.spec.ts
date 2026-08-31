import { expect, test } from "@playwright/test";

test("the demo page loads with its main panels", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sixth-Finger BCI" })).toBeVisible();
  await expect(page.getByTestId("hand")).toBeVisible();
  await expect(page.getByTestId("mode-badge")).toBeVisible();
});
