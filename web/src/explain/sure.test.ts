import { describe, expect, it } from "vitest";
import { coverageAt, nearestShare, plain, sayCoverage, type CoveragePoint } from "./sure";

const CURVE: CoveragePoint[] = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1].map((share, i) => ({
  share,
  acc: 0.95 - i * 0.012,
  ci: [0.9 - i * 0.01, 0.98],
}));

describe("the only-when-sure slider", () => {
  it("reads the curve where the slider stands, held to its ends", () => {
    expect(coverageAt(CURVE, 4).share).toBe(0.5);
    expect(coverageAt(CURVE, -3).share).toBe(0.1);
    expect(coverageAt(CURVE, 99).share).toBe(1);
  });

  it("says the share taken and how often those are right", () => {
    expect(plain(sayCoverage(coverageAt(CURVE, 4)))).toBe(
      "Taking only its surest 50% of decisions, it is right 90% of the time, and waits on the rest.",
    );
    expect(plain(sayCoverage(coverageAt(CURVE, 9)))).toBe("Taking every decision, it is right 84% of the time.");
  });

  it("puts the numbers in bold", () => {
    const bold = sayCoverage(coverageAt(CURVE, 0)).filter((s) => typeof s !== "string");
    expect(bold).toEqual([{ b: "10%" }, { b: "95%" }]);
  });

  it("picks the point nearest a pointer", () => {
    expect(nearestShare(CURVE, 0.47)).toBe(4);
    expect(nearestShare(CURVE, 0.01)).toBe(0);
    expect(nearestShare(CURVE, 1.2)).toBe(9);
  });
});
