import { create } from "zustand";
import {
  countReading,
  MoveSwitch,
  NO_SWITCHES,
  readWindow,
  SwitchCount,
  type Reading,
  type SwitchTally,
} from "./decision";
import { eegBuffer } from "./stream/eegBuffer";
import type { ClassInfo, Mode, Prediction, ServerMessage, SourceState } from "./stream/types";

export type Command = "IDLE" | "HAND_GRASP" | "SIXTH_FINGER_FLEX";
export type PhaseName = "rest" | "prepare" | "imagery";
export const RECENT = 16;

// Continuous mode's switch keeps its state between readings, and its score with it; a new
// stream or a jump starts both afresh. A trial that starts before the last one reached its
// end, or out of order, is a jump; null is a fresh stream.
const moveSwitch = new MoveSwitch();
const switchCount = new SwitchCount();
let playing: { trial: number; ended: boolean } | null = null;

function restartSwitch() {
  moveSwitch.reset();
  switchCount.reset();
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
  /** Continuous mode's score: switch-ons, those while imagining, imaginings missed. */
  switches: SwitchTally;
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
  switches: NO_SWITCHES,
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
        restartSwitch();
        playing = null;
        set({
          switches: switchCount.tally,
          synthetic: m.synthetic,
          classes: m.classes,
          mode: m.mode,
          nTrials: m.n_trials,
          speed: m.speed,
          window: m.window,
        });
        break;
      case "trial_start": {
        const n = Math.max(useDemo.getState().nTrials, 1);
        if (playing && !(playing.ended && m.trial === (playing.trial + 1) % n)) restartSwitch();
        playing = { trial: m.trial, ended: false };
        switchCount.start(m.trial, m.cue_onset_s);
        set({
          trial: m.trial,
          trialUid: m.uid,
          trialDuration: m.duration_s,
          cueOnset: m.cue_onset_s,
          switches: switchCount.tally,
        });
        break;
      }
      case "trial_end":
        if (playing?.trial === m.trial) playing.ended = true;
        switchCount.end(m.trial);
        set({ switches: switchCount.tally });
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
  applyPrediction: (p) => {
    // The half-second readings of continuous mode go through the switch's gate and are marked
    // by the switch-on behind them; the fixed windows are read one at a time and counted,
    // rest windows too (did it stay at rest?).
    const s = useDemo.getState();
    const sliding = p.window === "sliding";
    const reading = sliding ? moveSwitch.read(p, s.classes) : readWindow(p, s.classes);
    if (sliding) reading.right = switchCount.read(p.trial, p.t, reading.move);
    if (!sliding && p.trial === s.trial) {
      eegBuffer.mark({
        len: Math.round((s.window.end_s - s.window.start_s) * eegBuffer.sfreq),
        kind: reading.move ? "move" : "rest",
        right: reading.right,
      });
    }
    set({
      lastPrediction: p,
      lastReading: reading,
      recent: sliding ? s.recent : [...s.recent, p].slice(-RECENT),
      switches: switchCount.tally,
      ...countReading({ right: s.right, total: s.total }, p, reading),
    });
  },
  setManualCommand: (command) => set({ command, manualMode: true }),
  endManual: () => set({ manualMode: false, command: "IDLE" }),
  reset: () => {
    restartSwitch();
    playing = null;
    set({
      lastPrediction: null,
      lastReading: null,
      recent: [],
      command: "IDLE",
      right: 0,
      total: 0,
      switches: NO_SWITCHES,
      manualMode: false,
    });
  },
}));

/** The pose the hand shows: the manual test's, else the sixth finger bent on Move, whichever movement. */
export function shownCommand(s: Pick<DemoState, "manualMode" | "command" | "lastReading">): Command {
  if (s.manualMode) return s.command;
  return s.lastReading?.move ? "SIXTH_FINGER_FLEX" : "IDLE";
}
