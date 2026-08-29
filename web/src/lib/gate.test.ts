import { describe, expect, it } from "vitest";
import { CommandGate } from "./gate";

// Same vectors as server/tests/test_inference.py::test_gate_needs_dwell_and_releases.
const PROBS = [
  [0.8, 0.1, 0.1], [0.1, 0.1, 0.8], [0.05, 0.05, 0.9], [0.05, 0.05, 0.9],
  [0.1, 0.1, 0.8], [0.9, 0.05, 0.05], [0.9, 0.05, 0.05], [0.9, 0.05, 0.05],
  [0.1, 0.85, 0.05], [0.05, 0.9, 0.05], [0.05, 0.9, 0.05], [0.05, 0.9, 0.05],
];
const ACTIVE = [0, 0, 0, 0, 2, 2, 0, 0, 0, 0, 0, 1];

describe("CommandGate", () => {
  it("matches the server implementation", () => {
    const gate = new CommandGate();
    expect(PROBS.map((p) => gate.update(p))).toEqual(ACTIVE);
  });

  it("starts at rest with uniform smoothing", () => {
    const gate = new CommandGate();
    expect(gate.active).toBe(0);
    expect(gate.smoothed.every((s) => Math.abs(s - 1 / 3) < 1e-12)).toBe(true);
  });
});
