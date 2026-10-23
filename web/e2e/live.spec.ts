import { expect, test } from "@playwright/test";

test("the demo alone links the paper, the slides and the report, and the site serves them", async ({ page, request }) => {
  await page.goto("/live?server=http://127.0.0.1:9");
  const docs = page.locator(".live-foot .doc-links");
  await expect(docs.getByRole("link")).toHaveText([
    /^Paper, PDF, \d+\.\d MB$/,
    /^Slides, PowerPoint, \d+\.\d MB$/,
    /^Report, PDF, \d+\.\d MB$/,
  ]);
  await expect(docs.getByRole("link", { name: /^Slides/ })).toHaveAttribute("download", "sixth-finger-bci-slides.pptx");
  await expect(page.locator("a[href*='github.com']")).toHaveCount(0);
  const hrefs = await docs.getByRole("link").evaluateAll((links) => links.map((a) => a.getAttribute("href")));
  expect(hrefs).toEqual([
    "/docs/sixth-finger-bci-paper.pdf",
    "/docs/sixth-finger-bci-slides.pptx",
    "/docs/sixth-finger-bci-report.pdf",
  ]);
  for (const href of hrefs) {
    const res = await request.get(href!);
    expect(res.ok()).toBe(true);
    expect(res.headers()["content-type"]).not.toContain("text/html");
  }
});
