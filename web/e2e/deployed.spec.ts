import { expect, test } from "@playwright/test";

// Runs only against a deployed copy: DEPLOYED_URL=https://... npx playwright test e2e/deployed.spec.ts
const url = process.env.DEPLOYED_URL;
test.skip(!url, "DEPLOYED_URL not set");

test("the deployed demo decodes and says where", async ({ page }) => {
  await page.goto(url!);
  await expect(page.getByRole("heading", { name: /Sixth-Finger BCI/ })).toBeVisible();
  const badge = page.getByTestId("mode-badge");
  await expect(badge).toHaveAttribute("data-source", /^(server|browser)$/, { timeout: 30_000 });
  await expect(page.getByTestId("prediction")).not.toHaveAttribute("data-label", "", { timeout: 40_000 });
});

test("the deployed site serves the demo bundle and the model", async ({ request }) => {
  const manifest = await request.get(new URL("/demo/manifest.json", url!).href);
  expect(manifest.ok()).toBe(true);
  const m = await manifest.json();
  const model = await request.get(new URL(`/demo/${m.model.file}`, url!).href);
  expect(model.ok()).toBe(true);
});
