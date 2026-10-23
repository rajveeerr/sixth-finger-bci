import { expect, test, type APIRequestContext, type Locator } from "@playwright/test";

// The chapter-by-chapter page at /classic: the same demo, data and figures as the main page,
// laid out as numbered chapters.

const NO_SERVER = "server=http://127.0.0.1:9";

/** Every link under `where` to a file the site serves is there, and is the file rather than the page. */
async function servesEach(where: Locator, request: APIRequestContext) {
  const hrefs = await where.locator("a[href^='/docs/']").evaluateAll((links) => links.map((a) => a.getAttribute("href")));
  expect(hrefs).toEqual([
    "/docs/sixth-finger-bci-paper.pdf",
    "/docs/sixth-finger-bci-slides.pptx",
    "/docs/sixth-finger-bci-report.pdf",
  ]);
  for (const href of hrefs) {
    const res = await request.get(href!);
    expect(res.ok()).toBe(true);
    expect(res.headers()["content-type"]).not.toContain("text/html");
    expect((await res.body()).length).toBeLessThan(5_000_000);
  }
}

test("the chapter-by-chapter page loads with its own title and every chapter in order", async ({ page }) => {
  await page.goto(`/classic?${NO_SERVER}`);
  await expect(page).toHaveTitle("Sixth-Finger BCI, chapter by chapter");
  await expect(page.locator('meta[name="description"]')).toHaveAttribute("content", /chapter by chapter$/);
  await expect(page.locator('link[rel="canonical"], meta[name="robots"]')).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1, name: "Sixth-Finger BCI" })).toBeVisible();
  await expect(page.locator(".chapter h2")).toHaveText([
    "The idea",
    "The recordings",
    "What changes in the brain",
    "What we set out to find",
    "First, we checked the data",
    "The model",
    "Watch it work",
    "What we found",
    "How good it is, in numbers",
    "What this project adds",
    "What a BCI is, and how a patient would use it",
    "Read the paper, the slides and the report",
    "Read more",
  ]);
  await expect(page.locator(".chapter-num").first()).toHaveText("01");
  await expect(page.locator(".questions li")).toHaveCount(5);
  await expect(page.getByText("How you can check it")).toHaveCount(0);
});

test("chapter 1 opens with the stroke problem in four steps", async ({ page }) => {
  await page.goto(`/classic?${NO_SERVER}`);
  const idea = page.locator("#idea");
  await expect(idea.locator(".chapter-lede").first()).toContainText("affected hand");
  await expect(idea.locator(".problem h3")).toHaveText([
    "After a stroke",
    "A sixth finger",
    "Moved by imagining",
    "Our question",
  ]);
});

test("the demo runs on the page, in both ways of reading, with the live score", async ({ page }) => {
  await page.goto(`/classic?speed=8&${NO_SERVER}`);
  await expect(page.getByTestId("mode-badge")).toHaveAttribute("data-source", "browser", { timeout: 15_000 });
  await expect(page.getByTestId("prediction")).not.toHaveAttribute("data-label", "", { timeout: 10_000 });
  await expect(page.getByTestId("hand")).not.toHaveAttribute("data-command", "IDLE", { timeout: 15_000 });
  await expect(page.locator("#demo .mode")).toHaveCount(2);
  await page.getByRole("radio", { name: /Continuous/ }).click();
  await expect(page.getByTestId("switch-score")).toContainText(/Moved (once|\d+ times), \d+ right/, { timeout: 15_000 });
});

test("the five answers are dials used as tabs, and the first says what the published score means", async ({ page }) => {
  await page.goto(`/classic?${NO_SERVER}`);
  const tabs = page.locator("#found [role=tab]");
  await expect(tabs).toHaveCount(5);
  await expect(tabs.first()).toHaveAttribute("aria-selected", "true");
  const panel = page.locator("#answer-panel");
  await expect(panel.locator(".finding-lines dt")).toHaveText([
    /^What \d+% means$/,
    "Why it is too high",
    "The fair score",
    "Why it matters",
  ]);
  await expect(panel.locator(".leak")).toHaveCount(1);

  await tabs.nth(2).click();
  await expect(tabs.nth(2)).toHaveAttribute("aria-selected", "true");
  await expect(panel.locator(".finding-q")).toHaveText("Is the sixth finger a command of its own?");
  await expect(page).toHaveURL(/#answer-3$/);
  await page.keyboard.press("ArrowRight");
  await expect(tabs.nth(3)).toBeFocused();
  await expect(panel.locator(".finding-q")).toHaveText("Would it work live, as a simple on/off switch?");

  await page.goto(`/classic?${NO_SERVER}#answer-5`);
  await expect(page.locator("#found [role=tab]").nth(4)).toHaveAttribute("aria-selected", "true");
});

test("the benchmark is its own chapter, straight after the answers", async ({ page }) => {
  await page.goto(`/classic?${NO_SERVER}`);
  await expect(page.locator(".chapter")).toHaveCount(13);
  const ids = await page.locator(".chapter").evaluateAll((all) => all.map((c) => c.id));
  expect(ids.indexOf("numbers")).toBe(ids.indexOf("found") + 1);
  const bench = page.locator("#numbers");
  await expect(bench.locator(".bench-table tbody tr")).toHaveCount(3);
  await expect(bench.locator("td.bench-best b")).toHaveText([/^\d+\.\d%$/, /^\d+\.\d%$/, /^\d+\.\d%$/]);
  await expect(bench.locator(".bench-lines dt")).toHaveText(["Setting up", "Another day", "Live", "The leak", "Model size"]);
});

test("one figure shows how a patient would use it and which parts are built, without a switch", async ({ page }) => {
  await page.goto(`/classic?${NO_SERVER}`);
  const use = page.locator("#use");
  await expect(use.locator(".built-key li")).toHaveText(["Built in this project", "Needed in a real system"]);
  const path = use.locator("#journey");
  await expect(path.locator(".jy-step")).toHaveCount(4);
  await expect(path.locator(".jy-parts li").filter({ hasText: "Bridge" })).toHaveText("Bridge: needed");
  await expect(use.getByRole("radio")).toHaveCount(0);
  await expect(page.locator(".loop, .pipe")).toHaveCount(0);
});

test("the paper, the slides and the report are linked from the opening and served, and nothing links to GitHub", async ({
  page,
  request,
}) => {
  await page.goto(`/classic?${NO_SERVER}`);
  await expect(page.locator(".hero-read a")).toHaveAttribute("href", "#read");
  const read = page.locator("#read");
  await expect(read.getByRole("link", { name: /^Paper, PDF, \d+\.\d MB$/ })).toBeVisible();
  await servesEach(read, request);
  await expect(page.locator("a[href*='github.com']")).toHaveCount(0);
  const more = await page.locator("#more a").evaluateAll((links) => links.map((a) => a.getAttribute("href")));
  expect(more.length).toBeGreaterThan(0);
  for (const href of more) expect(href).toMatch(/^https:\/\/doi\.org\//);
});

for (const { width, height, name } of [
  { width: 320, height: 640, name: "small phone" },
  { width: 390, height: 844, name: "large phone" },
  { width: 1024, height: 768, name: "old projector" },
  { width: 1366, height: 768, name: "projector" },
  { width: 1920, height: 1080, name: "full HD screen" },
]) {
  test(`no horizontal scroll on the chapter-by-chapter page, ${name} (${width}×${height})`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto(`/classic?speed=4&${NO_SERVER}`);
    await expect(page.getByTestId("prediction")).not.toHaveAttribute("data-label", "", { timeout: 10_000 });
    for (const tab of await page.locator("#found [role=tab]").all()) await tab.click();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}
