import { expect, test } from "@playwright/test";

for (const { width, height, name } of [
  { width: 1366, height: 768, name: "projector" },
  { width: 1024, height: 768, name: "old projector" },
  { width: 1920, height: 1080, name: "full HD screen" },
  { width: 375, height: 812, name: "phone" },
  { width: 320, height: 640, name: "small phone" },
]) {
  test(`no horizontal scroll on the ${name} (${width}×${height})`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto("/?speed=4&server=http://127.0.0.1:9");
    await expect(page.getByTestId("prediction")).not.toHaveAttribute("data-label", "", { timeout: 10_000 });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
    await page.screenshot({ path: `test-results/layout-${name.replace(/ /g, "-")}.png` });
    await page.screenshot({ path: `test-results/layout-${name.replace(/ /g, "-")}-full.png`, fullPage: true });
    // The demo itself, for the report (docs/figures/demo_projector.png and demo_phone.png).
    await page.locator("#demo").scrollIntoViewIfNeeded();
    await page.evaluate(() => document.querySelector("#demo")!.scrollIntoView({ block: "start" }));
    await page.waitForTimeout(600);
    if (width >= 1024) await page.screenshot({ path: `test-results/demo-${name.replace(/ /g, "-")}.png` });
    else await page.locator(".demo").screenshot({ path: `test-results/demo-${name.replace(/ /g, "-")}.png` });
  });
}
