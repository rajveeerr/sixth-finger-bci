import { beforeEach, describe, expect, it } from "vitest";
import { useDemo } from "./store";
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
