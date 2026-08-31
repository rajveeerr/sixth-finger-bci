import { create } from "zustand";
import type { ClassInfo, Prediction, Source } from "./stream/types";

export type Command = "IDLE" | "HAND_GRASP" | "SIXTH_FINGER_FLEX";

interface DemoState {
  source: Source | "connecting" | "offline";
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
    set((s) => ({
      lastPrediction: p,
      command: p.command as Command,
      correct: s.correct + (p.correct ? 1 : 0),
      total: s.total + (p.correct === null ? 0 : 1),
    })),
  setManualCommand: (command) => set({ command, manualMode: true }),
  reset: () => set({ lastPrediction: null, command: "IDLE", correct: 0, total: 0, manualMode: false }),
}));
