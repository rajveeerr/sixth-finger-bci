import { create } from "zustand";
import type { ClassInfo, Prediction, SourceState } from "./stream/types";

export type Command = "IDLE" | "HAND_GRASP" | "SIXTH_FINGER_FLEX";

interface DemoState {
  source: SourceState;
  synthetic: boolean;
  classes: ClassInfo[];
  command: Command;
  lastPrediction: Prediction | null;
  correct: number;
  total: number;
  manualMode: boolean;
  setSource: (source: DemoState["source"]) => void;
  applyPrediction: (p: Prediction) => void;
  setManualCommand: (command: Command) => void;
  reset: () => void;
}

export const useDemo = create<DemoState>((set) => ({
  source: "connecting",
  synthetic: false,
  classes: [],
  command: "IDLE",
  lastPrediction: null,
  correct: 0,
  total: 0,
  manualMode: false,
  setSource: (source) => set({ source }),
  applyPrediction: (p) =>
    set((s) => {
      // Running accuracy counts imagery decisions only: rest windows and the
      // experimental sliding windows would inflate it.
      const scored = p.window === "imagery" && p.correct !== null;
      return {
        lastPrediction: p,
        command: p.command as Command,
        correct: s.correct + (scored && p.correct ? 1 : 0),
        total: s.total + (scored ? 1 : 0),
      };
    }),
  setManualCommand: (command) => set({ command, manualMode: true }),
  reset: () => set({ lastPrediction: null, command: "IDLE", correct: 0, total: 0, manualMode: false }),
}));
