import { describe, expect, it } from "vitest";
import { decidedKind, isRight, labelOf } from "./decision";
import type { ClassInfo, Prediction } from "./stream/types";

const CLASSES: ClassInfo[] = [
  { id: 0, name: "rest", label: "Rest", command: "IDLE" },
  { id: 1, name: "affected_hand", label: "Affected hand", command: "HAND_GRASP" },
  { id: 2, name: "sixth_finger", label: "Sixth finger", command: "SIXTH_FINGER_FLEX" },
];

function p(probs: number[], label: string, truth: string | null): Prediction {
  return {
    type: "prediction", trial: 0, t: 5, window: "imagery", window_s: [1, 5], probs, label_id: 0, label,
    command: "IDLE", confidence: Math.max(...probs), truth, correct: truth === null ? null : label === truth,
    latency_ms: 1, source: "browser",
  };
}

describe("a decision in each view", () => {
  it("is the trained class in the three-command view", () => {
    const hand = p([0.2, 0.5, 0.3], "affected_hand", "sixth_finger");
    expect(decidedKind(hand, "three", CLASSES)).toBe("affected_hand");
    expect(isRight(hand, "three", CLASSES)).toBe(false);
  });

  it("is rest against any imagery in the one-switch view", () => {
    const hand = p([0.2, 0.5, 0.3], "affected_hand", "sixth_finger");
    expect(decidedKind(hand, "switch", CLASSES)).toBe("imagery");
    expect(isRight(hand, "switch", CLASSES)).toBe(true); // imagery read as imagery
    const restish = p([0.6, 0.25, 0.15], "rest", "rest");
    expect(decidedKind(restish, "switch", CLASSES)).toBe("rest");
    expect(isRight(restish, "switch", CLASSES)).toBe(true);
  });

  it("has no right or wrong without a cue, and names the switch's decision", () => {
    expect(isRight(p([0.2, 0.5, 0.3], "affected_hand", null), "three", CLASSES)).toBeNull();
    expect(labelOf(CLASSES, "imagery")).toBe("Movement imagined");
    expect(labelOf(CLASSES, "sixth_finger")).toBe("Sixth finger");
  });
});
