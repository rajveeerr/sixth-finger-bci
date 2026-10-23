import { describe, expect, it } from "vitest";
import { data } from "./data";

describe("the benchmark", () => {
  it("marks as best a score no method in its row beats", () => {
    for (const row of data.benchmark.tasks) {
      expect(row.best.mean).toBeGreaterThanOrEqual(Math.max(row.csp_lda, row.ts_lr, row.eegnet_scratch));
    }
  });
});
