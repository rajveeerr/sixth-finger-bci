import { describe, expect, it } from "vitest";
import { damp, dampAll } from "./spring";

describe("spring", () => {
  it("settles within half a second at 60 fps, whatever the frame rate", () => {
    let a = 0;
    for (let i = 0; i < 30; i++) a = damp(a, 1.4, 10, 1 / 60);
    let b = 0;
    for (let i = 0; i < 15; i++) b = damp(b, 1.4, 10, 1 / 30);
    expect(a).toBeGreaterThan(1.4 * 0.99);
    expect(Math.abs(a - b)).toBeLessThan(1e-9);
  });

  it("reports when every joint has arrived", () => {
    const joints = [0, 0, 0];
    expect(dampAll(joints, [1, 1, 1], 10, 1 / 60)).toBe(false);
    let done = false;
    for (let i = 0; i < 120 && !done; i++) done = dampAll(joints, [1, 1, 1], 10, 1 / 60);
    expect(done).toBe(true);
  });
});
