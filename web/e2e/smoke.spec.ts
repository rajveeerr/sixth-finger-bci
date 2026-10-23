import { expect, test } from "@playwright/test";

test("the demo page loads with its main panels", async ({ page }) => {
  await page.goto("/?server=http://127.0.0.1:9");
  await expect(page.getByRole("heading", { name: /Sixth-Finger BCI/ })).toBeVisible();
  await expect(page.getByTestId("hand")).toBeVisible();
  await expect(page.getByTestId("mode-badge")).toBeVisible();
});

test("one chapter for the patient's path and what is built, each part drawn once", async ({ page }) => {
  await page.goto("/?server=http://127.0.0.1:9");
  await expect(page.locator(".index li")).toHaveCount(9);
  const use = page.locator("#use");
  await expect(use.locator(".q-num")).toHaveText("7");
  await expect(use.locator("h2")).toHaveText("How would a patient use it, and which parts are built?");
  await expect(page.locator("#numbers .q-num")).toHaveText("8");
  await expect(page.locator("#added .q-num")).toHaveText("9");
  await expect(page.locator("#added h2")).toHaveText("What did you add?");
  await expect(page.getByText("How you can check it")).toHaveCount(0);
  await expect(page.locator("#built")).toHaveCount(0);

  const path = page.locator("#journey");
  await expect(path.locator(".jy-step")).toHaveCount(4);
  await expect(path.locator("[data-cap]")).toHaveCount(1);
  await expect(path.locator(".screen-glass")).toHaveCount(1);
  await expect(path.locator(".finger")).toHaveCount(1);
  const parts = path.locator(".jy-parts li");
  await expect(parts.filter({ hasText: "Bridge" })).toHaveText("Bridge: needed");
  await expect(parts.filter({ hasText: "Bridge" })).not.toHaveAttribute("data-built");
  await expect(parts.filter({ hasText: "Server and model" })).toHaveAttribute("data-built", "");
  await expect(path.locator(".jy-link")).toHaveText([
    "brain signal, every 80 ms",
    "a command every half second, from the last 4 s",
  ]);
});

test("the page opens with the problem: a hand a stroke left weak, and what the sixth finger does", async ({ page }) => {
  await page.goto("/?server=http://127.0.0.1:9");
  const first = page.locator(".index li").first();
  await expect(first.locator(".index-ask")).toHaveText("What problem does it solve?");
  await expect(first.locator("a")).toHaveAttribute("href", "#problem");
  const problem = page.locator("#problem");
  await expect(problem.locator(".q-num")).toHaveText("1");
  await expect(problem.locator(".problem h3")).toHaveText([
    "After a stroke",
    "A sixth finger",
    "Moved by imagining",
    "Our question",
  ]);
});

test("the chapter on the published 85% says what it means and why it is too high before its fold", async ({ page }) => {
  await page.goto("/?server=http://127.0.0.1:9");
  const published = page.locator("#published");
  await expect(published.locator(".q-points dt")).toHaveText([
    "What 85% means",
    "Why it is too high",
    "The fair score",
    "Why it matters",
  ]);
  await expect(published.locator(".q-points")).toBeVisible();
  await expect(published.locator("details.more")).not.toHaveAttribute("open");
});

test("the benchmark puts every headline score in one table, the best of each row marked", async ({ page }) => {
  await page.goto("/?server=http://127.0.0.1:9");
  const bench = page.locator("#numbers");
  await expect(bench.locator("h2")).toHaveText("How good is it, in numbers?");
  await expect(bench.locator(".bench-table thead th")).toHaveText([
    "Task",
    "CSP+LDA",
    "Tangent space + logistic regression",
    "EEGNet per patient",
    "Best",
  ]);
  const rows = bench.locator(".bench-table tbody tr");
  await expect(rows.locator(".bench-task")).toHaveText([
    "Sixth finger or rest",
    "Hand or sixth finger",
    "Rest, hand or sixth finger",
  ]);
  await expect(rows.locator(".bench-guess")).toHaveText(["guessing gets 50%", "guessing gets 50%", "guessing gets 33%"]);
  await expect(rows.locator("td.bench-best b")).toHaveText([/^\d+\.\d%$/, /^\d+\.\d%$/, /^\d+\.\d%$/]);
  await expect(bench.locator(".bench-lines dt")).toHaveText(["Setting up", "Another day", "Live", "The leak", "Model size"]);
});
