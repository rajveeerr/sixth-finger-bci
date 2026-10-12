import { describe, expect, it } from "vitest";
import { scale, swarm } from "./charts";

describe("chart helpers", () => {
  it("maps a domain onto pixels, either way round", () => {
    expect(scale(0, 1, 10, 110)(0.5)).toBe(60);
    expect(scale(0, 1, 100, 0)(0.25)).toBe(75);
  });

  it("stacks dots that would overlap and leaves lone dots on the line", () => {
    const x = scale(0, 1, 0, 100);
    const dy = swarm([0.1, 0.1, 0.1, 0.9], x, 4);
    expect(dy[3]).toBe(0);
    expect(new Set(dy.slice(0, 3)).size).toBe(3);
    for (let i = 0; i < 3; i++) for (let j = i + 1; j < 3; j++) expect(Math.abs(dy[i] - dy[j])).toBeGreaterThanOrEqual(7.8);
  });
});
