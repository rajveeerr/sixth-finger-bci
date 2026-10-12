import { beforeEach, describe, expect, it } from "vitest";
import { RECENT, shownCommand, useDemo } from "./store";
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

describe("the trial strip and the recent row", () => {
  beforeEach(() => useDemo.getState().reset());

  it("keeps this trial's window decisions and forgets them at the next trial", () => {
    const { applyPrediction, applyMessage } = useDemo.getState();
    applyMessage({ type: "trial_start", trial: 0, pass: 0, uid: "sub-08_x", n_samples: 3600, duration_s: 14.4, cue_onset_s: 8.6 });
    applyPrediction(prediction("rest", true));
    applyPrediction(prediction("sliding", null));
    applyPrediction(prediction("imagery", false));
    let s = useDemo.getState();
    expect(s.trialDecisions.map((p) => p.window)).toEqual(["rest", "imagery"]);
    expect([s.trialDuration, s.cueOnset]).toEqual([14.4, 8.6]);
    applyMessage({ type: "trial_start", trial: 1, pass: 0, uid: "sub-08_y", n_samples: 3600, duration_s: 14.4, cue_onset_s: 8.6 });
    s = useDemo.getState();
    expect(s.trialDecisions).toEqual([]);
    expect(s.recent).toHaveLength(2); // the recent row runs across trials
  });

  it("keeps only the last RECENT decisions", () => {
    const { applyPrediction } = useDemo.getState();
    for (let i = 0; i < RECENT + 5; i++) applyPrediction({ ...prediction("imagery", true), t: i });
    const s = useDemo.getState();
    expect(s.recent).toHaveLength(RECENT);
    expect(s.recent[0].t).toBe(5);
  });
});
