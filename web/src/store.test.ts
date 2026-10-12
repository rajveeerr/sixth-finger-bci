import { beforeEach, describe, expect, it } from "vitest";
import { shownCommand, useDemo } from "./store";
import type { Prediction } from "./stream/types";

function prediction(window: Prediction["window"], correct: boolean | null): Prediction {
  return {
    type: "prediction", trial: 0, t: 5, window, window_s: [1, 5], probs: [0.2, 0.7, 0.1],
    label_id: 1, label: "affected_hand", command: "HAND_GRASP", confidence: 0.7,
    truth: correct === null ? null : "affected_hand", correct, latency_ms: 1, source: "server",
  };
}

describe("running accuracy", () => {
  beforeEach(() => useDemo.getState().reset());

  it("counts imagery predictions only", () => {
    const { applyPrediction } = useDemo.getState();
    applyPrediction(prediction("rest", true));
    applyPrediction(prediction("sliding", false));
    applyPrediction(prediction("imagery", true));
    applyPrediction(prediction("imagery", false));
    const s = useDemo.getState();
    expect([s.correct, s.total]).toEqual([1, 2]);
    expect(s.command).toBe("HAND_GRASP");
  });
});


describe("one-switch view", () => {
  beforeEach(() => {
    useDemo.getState().reset();
    useDemo.setState({
      classes: [
        { id: 0, name: "rest", label: "Rest", command: "IDLE" },
        { id: 1, name: "affected_hand", label: "Affected hand", command: "HAND_GRASP" },
        { id: 2, name: "sixth_finger", label: "Sixth finger", command: "SIXTH_FINGER_FLEX" },
      ],
    });
  });

  it("scores rest and imagery windows as imagery against rest", () => {
    const { applyPrediction } = useDemo.getState();
    // Hand imagery read as hand: right for both views.
    applyPrediction(prediction("imagery", true));
    // Rest window read as hand (0.7 + 0.1 > 0.2): wrong for the switch.
    applyPrediction({ ...prediction("rest", false), truth: "rest" });
    const s = useDemo.getState();
    expect([s.switchCorrect, s.switchTotal]).toEqual([1, 2]);
    expect([s.correct, s.total]).toEqual([1, 1]);
  });

  it("flexes the sixth finger for any imagery in the switch view", () => {
    const p = prediction("imagery", true); // hand imagery decoded as hand
    expect(shownCommand({ manualMode: false, command: "HAND_GRASP", view: "three", lastPrediction: p })).toBe("HAND_GRASP");
    expect(shownCommand({ manualMode: false, command: "HAND_GRASP", view: "switch", lastPrediction: p })).toBe("SIXTH_FINGER_FLEX");
    const rest = { ...p, probs: [0.8, 0.1, 0.1] };
    expect(shownCommand({ manualMode: false, command: "IDLE", view: "switch", lastPrediction: rest })).toBe("IDLE");
    expect(shownCommand({ manualMode: true, command: "HAND_GRASP", view: "switch", lastPrediction: rest })).toBe("HAND_GRASP");
  });
});
