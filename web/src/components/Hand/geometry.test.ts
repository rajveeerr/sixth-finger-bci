import { describe, expect, it } from "vitest";
import { forearmGeometry, knuckleY, nailGeometry, palmGeometry, phalanxGeometry, PALM_LENGTH } from "./geometry";

function finite(g: { getAttribute: (n: string) => { array: ArrayLike<number> } }) {
  return Array.from(g.getAttribute("position").array).every(Number.isFinite);
}

describe("the hand's shapes", () => {
  it("builds every part with finite vertices and normals", () => {
    for (const g of [palmGeometry(), forearmGeometry(), phalanxGeometry(4, 1, 0.9), phalanxGeometry(2, 0.8, 0.7, true), nailGeometry(1, 1.2)]) {
      expect(finite(g)).toBe(true);
      expect(Array.from(g.getAttribute("normal").array).every(Number.isFinite)).toBe(true);
    }
  });

  it("puts the knuckle line highest at the middle finger", () => {
    expect(knuckleY(-0.9)).toBeGreaterThan(knuckleY(-2.8));
    expect(knuckleY(-0.9)).toBeGreaterThan(knuckleY(2.7));
    expect(knuckleY(-2.8)).toBeGreaterThan(knuckleY(2.7)); // the little finger sits lowest
    expect(knuckleY(0)).toBeLessThan(PALM_LENGTH);
  });

  it("makes a phalanx that turns about a sphere at its base", () => {
    const g = phalanxGeometry(4, 1, 0.9);
    g.computeBoundingBox();
    expect(g.boundingBox!.min.y).toBeCloseTo(-1, 1); // the joint sphere reaches below the pivot
    expect(g.boundingBox!.max.y).toBeCloseTo(4.9, 1);
  });
});
