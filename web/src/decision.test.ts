import { describe, expect, it } from "vitest";
import { countReading, guessOf, MoveSwitch, readWindow, type Reading } from "./decision";
import type { ClassInfo, Prediction } from "./stream/types";

const CLASSES: ClassInfo[] = [
  { id: 0, name: "rest", label: "Rest", command: "IDLE" },
  { id: 1, name: "affected_hand", label: "Affected hand", command: "HAND_GRASP" },
  { id: 2, name: "sixth_finger", label: "Sixth finger", command: "SIXTH_FINGER_FLEX" },
];

function p(probs: number[], truth: string | null, window: Prediction["window"] = "imagery"): Prediction {
  const id = probs.indexOf(Math.max(...probs));
  return {
    type: "prediction", trial: 0, t: 5, window, window_s: [1, 5], probs, label_id: id, label: CLASSES[id].name,
    command: CLASSES[id].command, confidence: probs[id], truth, correct: truth === null ? null : CLASSES[id].name === truth,
    latency_ms: 1, source: "browser",
  };
}

describe("move or rest on a fixed window", () => {
  it("adds the two movements against rest, even when rest is the likeliest single choice", () => {
    const r = readWindow(p([0.45, 0.3, 0.25], "sixth_finger"), CLASSES);
    expect(r.move).toBe(true);
    expect(r.sure).toBeCloseTo(0.55);
    expect(r.right).toBe(true);
  });

  it("counts a hand trial read as a movement as right, the guess aside", () => {
    const r = readWindow(p([0.1, 0.2, 0.7], "affected_hand"), CLASSES);
    expect([r.move, r.right, r.guess]).toEqual([true, true, "sixth_finger"]);
  });

  it("is wrong when a rest window is read as a movement, and has no right or wrong without a cue", () => {
    expect(readWindow(p([0.3, 0.5, 0.2], "rest", "rest"), CLASSES).right).toBe(false);
    expect(readWindow(p([0.8, 0.1, 0.1], "rest", "rest"), CLASSES)).toMatchObject({ move: false, right: true });
    expect(readWindow(p([0.2, 0.5, 0.3], null), CLASSES).right).toBeNull();
  });

  it("guesses the likelier of the two movements", () => {
    expect(guessOf([0.9, 0.06, 0.04], CLASSES)).toBe("affected_hand");
    expect(guessOf([0.1, 0.3, 0.6], CLASSES)).toBe("sixth_finger");
  });
});

describe("the tally", () => {
  const read = (probs: number[], truth: string, window: Prediction["window"] = "imagery") => {
    const pred = p(probs, truth, window);
    return [pred, readWindow(pred, CLASSES)] as [Prediction, Reading];
  };

  it("counts hand and sixth-finger trials alike as a movement, and rest windows too", () => {
    let t = { right: 0, total: 0 };
    for (const [pred, r] of [
      read([0.2, 0.7, 0.1], "affected_hand"), // hand read as a movement: right
      read([0.2, 0.1, 0.7], "affected_hand"), // hand read as the sixth finger: still a movement, right
      read([0.3, 0.1, 0.6], "sixth_finger"), // sixth finger read as a movement: right
      read([0.6, 0.2, 0.2], "sixth_finger"), // sixth finger read as rest: wrong
      read([0.7, 0.2, 0.1], "rest", "rest"), // rest read as rest: right
      read([0.4, 0.5, 0.1], "rest", "rest"), // rest read as a movement: wrong
    ])
      t = countReading(t, pred, r);
    expect(t).toEqual({ right: 4, total: 6 });
  });

  it("leaves out the half-second readings and windows without a cue", () => {
    const t = { right: 0, total: 0 };
    const sliding = p([0.2, 0.7, 0.1], "affected_hand", "sliding");
    expect(countReading(t, sliding, readWindow(sliding, CLASSES))).toBe(t);
    const uncued = p([0.2, 0.7, 0.1], null);
    expect(countReading(t, uncued, readWindow(uncued, CLASSES))).toBe(t);
  });
});

describe("the continuous switch", () => {
  it("turns on above 60% twice in a row and off below 45%, as question 4 measured it", () => {
    const sw = new MoveSwitch();
    const on = (probs: number[]) => sw.read(p(probs, "sixth_finger", "sliding"), CLASSES).move;
    // A sure movement: the steadied chance is 65% after one reading and 76% after two; on at the second.
    expect([on([0, 0.5, 0.5]), on([0, 0.5, 0.5]), on([0, 0.5, 0.5])]).toEqual([false, true, true]);
    // Then rest: 58% keeps it on, 41% turns it off.
    expect([on([1, 0, 0]), on([1, 0, 0]), on([1, 0, 0])]).toEqual([true, false, false]);
  });

  it("starts again at rest after a reset", () => {
    const sw = new MoveSwitch();
    for (let i = 0; i < 4; i++) sw.read(p([0, 0.5, 0.5], "affected_hand", "sliding"), CLASSES);
    sw.reset();
    expect(sw.read(p([0.5, 0.25, 0.25], "rest", "sliding"), CLASSES)).toMatchObject({ move: false, sure: 0.5 });
  });
});
