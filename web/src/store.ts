import { create } from "zustand";
import { eegBuffer } from "./stream/eegBuffer";
import type { ClassInfo, Mode, Prediction, ServerMessage, SourceState } from "./stream/types";

export type Command = "IDLE" | "HAND_GRASP" | "SIXTH_FINGER_FLEX";
// "three": the decoder's three commands as trained. "switch": the one-switch use the
// results support (P09): any imagery against rest flexes the sixth finger.
export type View = "three" | "switch";
export type PhaseName = "rest" | "prepare" | "imagery";
export const RECENT = 16;

/** Rest against either imagery, from the smoothed probabilities when the gate ran. */
export function anyImagery(p: Prediction): boolean {
  const v = p.smoothed ?? p.probs;
  return v[1] + v[2] > v[0];
}

interface DemoState {
  source: SourceState;
  synthetic: boolean;
  classes: ClassInfo[];
  mode: Mode;
  nTrials: number;
  trial: number;
  trialUid: string;
  trialDuration: number; // seconds
  cueOnset: number; // seconds from the trial's start
  window: { start_s: number; end_s: number };
  /** This trial's decisions on its rest and imagery windows, for the trial strip. */
  trialDecisions: Prediction[];
  /** The last decisions on rest and imagery windows, oldest first. */
  recent: Prediction[];
  phase: PhaseName | null;
  phaseTruth: string | null;
  paused: boolean;
  speed: number;
  view: View;
  command: Command;
  lastPrediction: Prediction | null;
  correct: number;
  total: number;
  switchCorrect: number;
  switchTotal: number;
  manualMode: boolean;
  error: string | null;
  setSource: (source: DemoState["source"]) => void;
  setView: (view: View) => void;
  setError: (error: string | null) => void;
  applyMessage: (m: ServerMessage) => void;
  applyPrediction: (p: Prediction) => void;
  setManualCommand: (command: Command) => void;
  endManual: () => void;
  reset: () => void;
}

export const useDemo = create<DemoState>((set) => ({
  source: "connecting",
  synthetic: false,
  classes: [],
  mode: "trial",
  nTrials: 0,
  trial: 0,
  trialUid: "",
  trialDuration: 0,
  cueOnset: 0,
  window: { start_s: 1, end_s: 5 },
  trialDecisions: [],
  recent: [],
  phase: null,
  phaseTruth: null,
  paused: false,
  speed: 1,
  view: "three",
  command: "IDLE",
  lastPrediction: null,
  correct: 0,
  total: 0,
  switchCorrect: 0,
  switchTotal: 0,
  manualMode: false,
  error: null,
  setSource: (source) => set({ source }),
  setView: (view) => set({ view }),
  setError: (error) => set({ error }),
  applyMessage: (m) => {
    switch (m.type) {
      case "hello":
        if (eegBuffer.channels.join() !== m.display_channels.join() || !eegBuffer.capacity) {
          eegBuffer.reset(m.display_channels, m.display_sfreq);
        }
        set({
          synthetic: m.synthetic,
          classes: m.classes,
          mode: m.mode,
          nTrials: m.n_trials,
          speed: m.speed,
          window: m.window,
        });
        break;
      case "trial_start":
        set({
          trial: m.trial,
          trialUid: m.uid,
          trialDuration: m.duration_s,
          cueOnset: m.cue_onset_s,
          trialDecisions: [],
        });
        break;
      case "phase":
        eegBuffer.setPhase(m.phase, m.truth);
        set({ phase: m.phase, phaseTruth: m.truth });
        break;
      case "eeg":
        eegBuffer.push(m.data, m.t);
        break;
      case "prediction":
        useDemo.getState().applyPrediction(m);
        break;
      case "status":
        set({ paused: m.paused, speed: m.speed });
        break;
      case "error":
        console.warn("stream error:", m.message);
        break;
    }
  },
  applyPrediction: (p) =>
    set((s) => {
      // Running accuracy of the three commands counts imagery decisions only: rest
      // windows and the experimental sliding windows would inflate it. The one switch
      // is scored on every trial window, rest included (did it stay quiet at rest?).
      const scored = p.window === "imagery" && p.correct !== null;
      const switchScored = p.window !== "sliding" && p.truth !== null;
      const switchRight = switchScored && anyImagery(p) === (p.truth !== s.classes[0]?.name);
      return {
        lastPrediction: p,
        trialDecisions: p.window === "sliding" || p.trial !== s.trial ? s.trialDecisions : [...s.trialDecisions, p],
        recent: p.window === "sliding" ? s.recent : [...s.recent, p].slice(-RECENT),
        command: s.manualMode ? s.command : (p.command as Command),
        correct: s.correct + (scored && p.correct ? 1 : 0),
        total: s.total + (scored ? 1 : 0),
        switchCorrect: s.switchCorrect + (switchRight ? 1 : 0),
        switchTotal: s.switchTotal + (switchScored ? 1 : 0),
      };
    }),
  setManualCommand: (command) => set({ command, manualMode: true }),
  endManual: () =>
    set((s) => ({ manualMode: false, command: (s.lastPrediction?.command as Command) ?? "IDLE" })),
  reset: () =>
    set({
      lastPrediction: null,
      trialDecisions: [],
      recent: [],
      command: "IDLE",
      correct: 0,
      total: 0,
      switchCorrect: 0,
      switchTotal: 0,
      manualMode: false,
    }),
}));

/** The command the hand shows: manual test, else the decoder in the chosen view. */
export function shownCommand(s: Pick<DemoState, "manualMode" | "command" | "view" | "lastPrediction">): Command {
  if (s.manualMode || s.view === "three" || !s.lastPrediction) return s.command;
  return anyImagery(s.lastPrediction) ? "SIXTH_FINGER_FLEX" : "IDLE";
}
