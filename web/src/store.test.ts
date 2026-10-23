import { beforeEach, describe, expect, it } from "vitest";
import { RECENT, shownCommand, useDemo } from "./store";
import { eegBuffer } from "./stream/eegBuffer";
import type { Prediction } from "./stream/types";

const CLASSES = [
  { id: 0, name: "rest", label: "Rest", command: "IDLE" },
  { id: 1, name: "affected_hand", label: "Affected hand", command: "HAND_GRASP" },
  { id: 2, name: "sixth_finger", label: "Sixth finger", command: "SIXTH_FINGER_FLEX" },
];

function prediction(window: Prediction["window"], truth: string | null, probs = [0.2, 0.7, 0.1]): Prediction {
  return {
    type: "prediction", trial: 0, t: 5, window, window_s: [1, 5], probs,
    label_id: 1, label: "affected_hand", command: "HAND_GRASP", confidence: 0.7,
    truth, correct: truth === null ? null : truth === "affected_hand", latency_ms: 1, source: "server",
  };
}

beforeEach(() => {
  useDemo.getState().reset();
  useDemo.setState({ classes: CLASSES, trial: 0, nTrials: 36 });
});

describe("the move-or-rest tally", () => {
  it("counts every fixed window, hand and sixth-finger trials both as a movement", () => {
    const { applyPrediction } = useDemo.getState();
    applyPrediction(prediction("imagery", "affected_hand")); // read as a movement: right
    applyPrediction(prediction("imagery", "sixth_finger")); // a hand lean, but a movement: right
    applyPrediction(prediction("rest", "rest")); // a rest window read as a movement: wrong
    applyPrediction(prediction("rest", "rest", [0.8, 0.1, 0.1])); // rest read as rest: right
    applyPrediction(prediction("sliding", "sixth_finger")); // half-second readings are not counted
    const s = useDemo.getState();
    expect([s.right, s.total]).toEqual([3, 4]);
  });

  it("keeps the guess at which movement apart from the reading", () => {
    useDemo.getState().applyPrediction(prediction("imagery", "sixth_finger"));
    expect(useDemo.getState().lastReading).toMatchObject({ move: true, right: true, guess: "affected_hand" });
  });
});

describe("the hand", () => {
  it("bends the sixth finger on Move, whichever movement, and the manual test overrides", () => {
    const { applyPrediction } = useDemo.getState();
    applyPrediction(prediction("imagery", "affected_hand"));
    expect(shownCommand(useDemo.getState())).toBe("SIXTH_FINGER_FLEX");
    applyPrediction(prediction("rest", "rest", [0.8, 0.1, 0.1]));
    expect(shownCommand(useDemo.getState())).toBe("IDLE");
    useDemo.getState().setManualCommand("HAND_GRASP");
    expect(shownCommand(useDemo.getState())).toBe("HAND_GRASP");
    useDemo.getState().endManual();
    expect(shownCommand(useDemo.getState())).toBe("IDLE");
  });

  it("follows the continuous switch, which needs two sure readings in a row", () => {
    const { applyPrediction } = useDemo.getState();
    applyPrediction(prediction("sliding", "sixth_finger", [0, 0.5, 0.5]));
    expect(shownCommand(useDemo.getState())).toBe("IDLE");
    applyPrediction(prediction("sliding", "sixth_finger", [0, 0.5, 0.5]));
    expect(shownCommand(useDemo.getState())).toBe("SIXTH_FINGER_FLEX");
  });

  it("starts the continuous switch afresh after a jump, not on the next trial", () => {
    const { applyPrediction, applyMessage } = useDemo.getState();
    const start = (trial: number) =>
      applyMessage({ type: "trial_start", trial, pass: 0, uid: "x", n_samples: 3600, duration_s: 14.4, cue_onset_s: 8.6 });
    start(0);
    applyPrediction(prediction("sliding", "sixth_finger", [0, 0.5, 0.5]));
    applyMessage({ type: "trial_end", trial: 0 });
    start(1); // the next trial: the switch carries on
    applyPrediction({ ...prediction("sliding", "sixth_finger", [0, 0.5, 0.5]), trial: 1 });
    expect(useDemo.getState().lastReading?.move).toBe(true);
    start(9); // a jump: it starts again at rest
    applyPrediction({ ...prediction("sliding", "sixth_finger", [0, 0.5, 0.5]), trial: 9 });
    expect(useDemo.getState().lastReading?.move).toBe(false);
  });

  it("treats Next trial before the end of a trial as a jump", () => {
    const { applyPrediction, applyMessage } = useDemo.getState();
    const start = (trial: number) =>
      applyMessage({ type: "trial_start", trial, pass: 0, uid: "x", n_samples: 3600, duration_s: 14.4, cue_onset_s: 8.6 });
    start(0);
    applyPrediction(prediction("sliding", "sixth_finger", [0, 0.5, 0.5]));
    start(1); // trial 0 never ended
    applyPrediction({ ...prediction("sliding", "sixth_finger", [0, 0.5, 0.5]), trial: 1 });
    expect(useDemo.getState().lastReading?.move).toBe(false);
  });
});

describe("the continuous score", () => {
  const start = (trial: number) =>
    useDemo
      .getState()
      .applyMessage({ type: "trial_start", trial, pass: 0, uid: "x", n_samples: 3650, duration_s: 14.6, cue_onset_s: 8.6 });
  const end = (trial: number) => useDemo.getState().applyMessage({ type: "trial_end", trial });
  /** A half-second reading of `trial` ending `t` s into it; a sure movement or a sure rest. */
  const read = (trial: number, t: number, move: boolean) =>
    useDemo
      .getState()
      .applyPrediction({ ...prediction("sliding", "sixth_finger", move ? [0, 0.5, 0.5] : [1, 0, 0]), trial, t });
  const hello = () =>
    useDemo.getState().applyMessage({
      type: "hello", protocol: 1, server_version: "test", mode: "continuous", speed: 1, n_trials: 36, sfreq: 250,
      display_sfreq: 125, display_channels: ["C3"], classes: CLASSES, window: { start_s: 1, end_s: 5 },
      synthetic: false, model: { name: "m", method: "eegnet_scratch", sha256: "x" },
    });

  /** Trial 0: on during rest (wrong), off, on in the imagining (right). Trial 1: never on (missed). */
  function twoTrials() {
    start(0);
    for (const t of [5, 5.5, 6, 6.5, 7, 7.5]) read(0, t, t < 6.5);
    for (const t of [10, 10.5, 11]) read(0, t, true);
    end(0);
    start(1);
    for (const t of [5, 10, 14]) read(1, t, false);
    end(1);
  }

  it("counts switch-ons, those while imagining, and imaginings missed", () => {
    twoTrials();
    expect(useDemo.getState().switches).toEqual({ moved: 2, right: 1, missed: 1 });
  });

  it("marks each Move by its switch-on, as the score counts it", () => {
    start(0);
    read(0, 5, true);
    read(0, 5.5, true);
    expect(useDemo.getState().lastReading).toMatchObject({ move: true, right: false });
    read(0, 6, false);
    read(0, 6.5, false);
    read(0, 7, false);
    expect(useDemo.getState().lastReading).toMatchObject({ move: false, right: null });
  });

  it("starts again from nothing after a jump", () => {
    twoTrials();
    start(2);
    read(2, 9, true);
    read(2, 9.5, true);
    start(20); // a jump in the middle of trial 2
    expect(useDemo.getState().switches).toEqual({ moved: 0, right: 0, missed: 0 });
    read(20, 9, true);
    read(20, 9.5, true);
    end(20);
    expect(useDemo.getState().switches).toEqual({ moved: 1, right: 1, missed: 0 });
  });

  it("starts again from nothing when the replay restarts or is reset", () => {
    twoTrials();
    hello(); // a new stream: another mode, or the browser taking over from the server
    expect(useDemo.getState().switches).toEqual({ moved: 0, right: 0, missed: 0 });
    twoTrials();
    useDemo.getState().reset();
    expect(useDemo.getState().switches).toEqual({ moved: 0, right: 0, missed: 0 });
  });

  it("leaves the per-trial tally alone", () => {
    twoTrials();
    expect([useDemo.getState().right, useDemo.getState().total]).toEqual([0, 0]);
  });
});

describe("the trial strip and the recent row", () => {
  it("keeps the trial's timing and marks each read window on the chart as move or rest", () => {
    const { applyPrediction, applyMessage } = useDemo.getState();
    applyMessage({ type: "trial_start", trial: 0, pass: 0, uid: "sub-08_x", n_samples: 3600, duration_s: 14.4, cue_onset_s: 8.6 });
    eegBuffer.reset(["C3"], 125);
    eegBuffer.push([[0, 0, 0]]);
    const before = eegBuffer.marks.length;
    applyPrediction(prediction("rest", "rest", [0.8, 0.1, 0.1]));
    applyPrediction(prediction("sliding", null));
    applyPrediction(prediction("imagery", "affected_hand", [0.6, 0.3, 0.1]));
    const s = useDemo.getState();
    expect([s.trialDuration, s.cueOnset]).toEqual([14.4, 8.6]);
    expect(eegBuffer.marks.length - before).toBe(2); // sliding windows are not marked
    expect(eegBuffer.marks.at(-1)).toMatchObject({ end: 3, len: 500, kind: "rest", right: false });
    applyMessage({ type: "trial_start", trial: 1, pass: 0, uid: "sub-08_y", n_samples: 3600, duration_s: 14.4, cue_onset_s: 8.6 });
    expect(useDemo.getState().recent).toHaveLength(2); // the recent row runs across trials
  });

  it("keeps only the last RECENT decisions", () => {
    const { applyPrediction } = useDemo.getState();
    for (let i = 0; i < RECENT + 5; i++) applyPrediction({ ...prediction("imagery", "affected_hand"), t: i });
    const s = useDemo.getState();
    expect(s.recent).toHaveLength(RECENT);
    expect(s.recent[0].t).toBe(5);
  });
});
