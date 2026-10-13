import { expect, test } from "@playwright/test";

// The presenting laptop may have no network: the built site must need nothing but itself.
test("the built site decodes with every other host unreachable", async ({ page }) => {
  const outside: string[] = [];
  await page.route("**/*", (route) => {
    const host = new URL(route.request().url()).hostname;
    if (host === "localhost" || host === "127.0.0.1") return route.continue();
    outside.push(route.request().url());
    return route.abort();
  });
  await page.goto("/?server=http://127.0.0.1:9");
  await expect(page.getByTestId("mode-badge")).toHaveAttribute("data-source", "browser", { timeout: 20_000 });
  await expect(page.getByTestId("prediction")).not.toHaveAttribute("data-label", "", { timeout: 30_000 });
  expect(outside).toEqual([]);
});
