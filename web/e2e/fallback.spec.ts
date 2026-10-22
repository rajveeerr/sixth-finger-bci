import { expect, test, type Page } from "@playwright/test";

// A server that cannot answer (port 9 is closed), so the test does not depend on
// whether an inference server happens to be running.
const NO_SERVER = "server=http://127.0.0.1:9";

/** Waits for a Move reading and checks, in the same frame, that the sixth finger bent and a guess is shown. */
async function bendsOnMove(page: Page) {
  const seen = await page.waitForFunction(
    () => {
      const card = document.querySelector("[data-testid=prediction]");
      if (card?.getAttribute("data-label") !== "move") return null;
      return {
        command: document.querySelector("[data-testid=hand]")?.getAttribute("data-command"),
        guess: document.querySelector("[data-testid=guess]")?.textContent ?? "",
      };
    },
    null,
    { timeout: 30_000 },
  );
  const { command, guess } = (await seen.jsonValue())!;
  expect(command).toBe("SIXTH_FINGER_FLEX");
  expect(guess).toMatch(/A guess: the (hand|sixth finger)\. Right \d+% of the time for this patient/);
}

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

test("the sixth finger bends on Move, whichever movement was imagined", async ({ page }) => {
  await page.goto(`/?speed=8&${NO_SERVER}`);
  await expect(page.getByTestId("mode-badge")).toHaveAttribute("data-source", "browser", { timeout: 15_000 });
  await bendsOnMove(page);
  await expect(page.getByTestId("prediction")).toContainText("rest as Rest and hand or finger as Move");
  await expect(page.getByRole("radio", { name: "Three choices" })).toHaveCount(0);
});

test("the stored predictions drive the same switch when the in-browser model cannot load", async ({ page }) => {
  await page.route("**/demo/model.onnx", (route) => route.abort());
  await page.goto("/?speed=8&server=none");
  await expect(page.getByTestId("mode-badge")).toHaveAttribute("data-source", "replay", { timeout: 15_000 });
  await bendsOnMove(page);
  await expect(page.getByTestId("prediction")).toContainText("Worked out earlier by the same model and saved");
});

test("continuous mode moves the finger through the switch, without counting", async ({ page }) => {
  await page.goto(`/?speed=8&${NO_SERVER}`);
  await expect(page.getByTestId("mode-badge")).toHaveAttribute("data-source", "browser", { timeout: 15_000 });
  await page.getByRole("radio", { name: "Continuous (experimental)" }).click();
  await expect(page.getByTestId("prediction")).toContainText("A reading every half second", { timeout: 15_000 });
  await bendsOnMove(page);
});

test("the live page runs the same switch", async ({ page }) => {
  await page.goto(`/live?speed=8&${NO_SERVER}`);
  await expect(page.getByTestId("mode-badge")).toHaveAttribute("data-source", "browser", { timeout: 15_000 });
  await bendsOnMove(page);
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
