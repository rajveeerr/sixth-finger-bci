import { expect, test } from "@playwright/test";

const SERVER = process.env.SERVER_URL ?? "http://localhost:8000";

test.beforeAll(async ({ request }) => {
  const ok = await request.get(`${SERVER}/health`).then((r) => r.ok()).catch(() => false);
  test.skip(!ok, `no inference server at ${SERVER} (start it with make server)`);
});

test("decodes on the server and keeps it through a pause", async ({ page }) => {
  await page.goto(`/?speed=8&server=${encodeURIComponent(SERVER)}`);
  await expect(page.getByTestId("mode-badge")).toHaveAttribute("data-source", "server", { timeout: 5_000 });
  await expect(page.getByTestId("prediction")).toContainText("Decided on the server", { timeout: 10_000 });
  await page.getByRole("button", { name: "Pause" }).click();
  await page.waitForTimeout(8_000); // the server keeps a paused stream alive with heartbeats
  await expect(page.getByTestId("mode-badge")).toHaveAttribute("data-source", "server");
  await page.getByRole("button", { name: "Resume" }).click();
});
