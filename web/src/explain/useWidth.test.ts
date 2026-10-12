import { describe, expect, it } from "vitest";
import { scale, swarm } from "./useWidth";

describe("figure helpers", () => {
  it("maps a domain onto pixels, either way round", () => {
    const x = scale(0, 1, 10, 110);
    expect(x(0.5)).toBe(60);
    const y = scale(0, 1, 100, 0);
    expect(y(0.25)).toBe(75);
  });

  it("stacks dots that would overlap and leaves lone dots on the line", () => {
    const x = scale(0, 1, 0, 100);
    const dy = swarm([0.1, 0.1, 0.1, 0.9], x, 4);
    expect(dy[3]).toBe(0);
    expect(new Set(dy.slice(0, 3)).size).toBe(3); // three distinct rows
    for (let i = 0; i < 3; i++) for (let j = i + 1; j < 3; j++) expect(Math.abs(dy[i] - dy[j])).toBeGreaterThanOrEqual(7.6);
  });
});
