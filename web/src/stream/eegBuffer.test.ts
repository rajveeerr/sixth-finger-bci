import { describe, expect, it } from "vitest";
import { EegRing } from "./eegBuffer";

describe("the EEG ring", () => {
  it("knows how far into the trial its newest sample is", () => {
    const ring = new EegRing();
    ring.reset(["C3", "C4"], 125);
    ring.push([[1, 2, 3, 4, 5], [5, 4, 3, 2, 1]], 2.0);
    expect(ring.trialT).toBeCloseTo(2.04);
    expect(ring.filled).toBe(5);
    ring.push([[6], [0]]); // a chunk without a time leaves the playhead where it was
    expect(ring.trialT).toBeCloseTo(2.04);
  });
});
