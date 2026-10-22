import { create } from "zustand";
import { countReading, MoveSwitch, readWindow, type Reading } from "./decision";
import { eegBuffer } from "./stream/eegBuffer";
import type { ClassInfo, Mode, Prediction, ServerMessage, SourceState } from "./stream/types";

export type Command = "IDLE" | "HAND_GRASP" | "SIXTH_FINGER_FLEX";
export type PhaseName = "rest" | "prepare" | "imagery";
export const RECENT = 16;

// Continuous mode's switch keeps its state between readings; a new stream or a jump starts it afresh.
const moveSwitch = new MoveSwitch();

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
  /** The last decisions on rest and imagery windows, oldest first. */
  recent: Prediction[];
  phase: PhaseName | null;
  phaseTruth: string | null;
  paused: boolean;
  speed: number;
  /** The pose set by the manual test keys; readings move the finger through lastReading. */
  command: Command;
  lastPrediction: Prediction | null;
  /** Move or rest, and the guess at which movement, for the last prediction. */
  lastReading: Reading | null;
  /** Fixed windows read right as move or rest, rest windows included. */
  right: number;
  total: number;
  manualMode: boolean;
  error: string | null;
  setSource: (source: DemoState["source"]) => void;
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
  recent: [],
  phase: null,
  phaseTruth: null,
  paused: false,
  speed: 1,
  command: "IDLE",
  lastPrediction: null,
  lastReading: null,
  right: 0,
  total: 0,
  manualMode: false,
  error: null,
  setSource: (source) => set({ source }),
  setError: (error) => set({ error }),
  applyMessage: (m) => {
    switch (m.type) {
      case "hello":
        if (eegBuffer.channels.join() !== m.display_channels.join() || !eegBuffer.capacity) {
          eegBuffer.reset(m.display_channels, m.display_sfreq);
        }
        moveSwitch.reset();
        set({
          synthetic: m.synthetic,
          classes: m.classes,
          mode: m.mode,
          nTrials: m.n_trials,
          speed: m.speed,
          window: m.window,
        });
        break;
      case "trial_start": {
        const { trial, nTrials } = useDemo.getState();
        if (m.trial !== trial && m.trial !== (trial + 1) % Math.max(nTrials, 1)) moveSwitch.reset();
        set({ trial: m.trial, trialUid: m.uid, trialDuration: m.duration_s, cueOnset: m.cue_onset_s });
        break;
      }
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
  applyPrediction: (p) => {
    // The half-second readings of continuous mode go through the switch's gate; the fixed
    // windows are read one at a time and counted, rest windows too (did it stay at rest?).
    const s = useDemo.getState();
    const reading = p.window === "sliding" ? moveSwitch.read(p, s.classes) : readWindow(p, s.classes);
    if (p.window !== "sliding" && p.trial === s.trial) {
      eegBuffer.mark({
        len: Math.round((s.window.end_s - s.window.start_s) * eegBuffer.sfreq),
        kind: reading.move ? "move" : "rest",
        right: reading.right,
      });
    }
    set({
      lastPrediction: p,
      lastReading: reading,
      recent: p.window === "sliding" ? s.recent : [...s.recent, p].slice(-RECENT),
      ...countReading({ right: s.right, total: s.total }, p, reading),
    });
  },
  setManualCommand: (command) => set({ command, manualMode: true }),
  endManual: () => set({ manualMode: false, command: "IDLE" }),
  reset: () => {
    moveSwitch.reset();
    set({ lastPrediction: null, lastReading: null, recent: [], command: "IDLE", right: 0, total: 0, manualMode: false });
  },
}));

/** The pose the hand shows: the manual test's, else the sixth finger bent on Move, whichever movement. */
export function shownCommand(s: Pick<DemoState, "manualMode" | "command" | "lastReading">): Command {
  if (s.manualMode) return s.command;
  return s.lastReading?.move ? "SIXTH_FINGER_FLEX" : "IDLE";
}
