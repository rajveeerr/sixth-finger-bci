import { describe, expect, it } from "vitest";
import { countReading, guessOf, IMAGERY_S, MoveSwitch, readWindow, SwitchCount, type Reading } from "./decision";
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

describe("the continuous switch's score", () => {
  // A trial as the demo plays it: rest from 0 s, the cue at 8.6 s, imagining until 14.6 s.
  const CUE = 8.6;
  /** Plays one trial's readings, the switch's state at each half second from 4 s to 14.5 s. */
  function play(count: SwitchCount, trial: number, onAt: (t: number) => boolean, end = true) {
    count.start(trial, CUE);
    for (let t = 4; t <= 14.5; t += 0.5) count.read(trial, t, onAt(t));
    if (end) count.end(trial);
  }

  it("scores the same stretch as answer 4: the 6 s after the cue", () => {
    expect(IMAGERY_S).toBe(6);
  });

  it("counts each switch-on, right only when it falls in the imagining", () => {
    const count = new SwitchCount();
    // On during rest (wrong), off, then on again 2 s into the imagining (right).
    play(count, 0, (t) => (t >= 5 && t < 6) || t >= CUE + 2);
    expect(count.tally).toEqual({ moved: 2, right: 1, missed: 0 });
  });

  it("counts an imagining with no switch-on inside as missed once the trial ends", () => {
    const count = new SwitchCount();
    play(count, 0, () => false, false);
    expect(count.tally.missed).toBe(0); // not over yet
    count.end(0);
    expect(count.tally).toEqual({ moved: 0, right: 0, missed: 1 });
  });

  it("misses an imagining when the switch was already on before the cue, as answer 4 does", () => {
    const count = new SwitchCount();
    play(count, 0, (t) => t >= 7.5); // turned on in the wait before the cue and stayed on
    expect(count.tally).toEqual({ moved: 1, right: 0, missed: 1 });
  });

  it("does not count a switch-on just after the 6 s as right", () => {
    const count = new SwitchCount();
    count.start(0, CUE);
    count.read(0, CUE + IMAGERY_S - 0.1, false);
    count.read(0, CUE + IMAGERY_S, true);
    expect(count.tally).toEqual({ moved: 1, right: 0, missed: 1 });
  });

  it("marks a Move by the switch-on behind it, and a Rest not at all", () => {
    const count = new SwitchCount();
    count.start(0, CUE);
    expect(count.read(0, 6, true)).toBe(false); // on during rest
    expect(count.read(0, 9, true)).toBe(false); // still the same switch-on
    expect(count.read(0, 10, false)).toBeNull();
    expect(count.read(0, 11, true)).toBe(true);
  });

  it("stops marking a Move that runs on past the end of its trial", () => {
    const count = new SwitchCount();
    count.start(0, CUE);
    expect(count.read(0, 13, true)).toBe(true);
    count.end(0);
    count.start(1, CUE);
    expect(count.read(1, 0.5, true)).toBeNull(); // still on in the next trial's rest
    expect(count.tally).toEqual({ moved: 1, right: 1, missed: 0 });
  });

  it("runs on across trials and starts from nothing after a reset", () => {
    const count = new SwitchCount();
    play(count, 0, (t) => t >= CUE + 1 && t < CUE + 3);
    play(count, 1, () => false);
    expect(count.tally).toEqual({ moved: 1, right: 1, missed: 1 });
    count.reset();
    expect(count.tally).toEqual({ moved: 0, right: 0, missed: 0 });
    // The trial cut short by the reset is not scored when it ends.
    count.end(1);
    expect(count.tally.missed).toBe(0);
  });

  it("scores only trials seen from their start", () => {
    const count = new SwitchCount();
    count.read(3, 10, true); // a reading of a trial whose start it never saw
    count.end(3);
    expect(count.tally).toEqual({ moved: 1, right: 0, missed: 0 });
  });
});
