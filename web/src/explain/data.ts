// The numbers behind the explanatory figures, written by scripts/make_web_explain_data.py
// from the results summaries. Never edit data.json by hand: run the script again.
import raw from "./data.json";

export interface Electrode {
  name: string;
  x: number; // 1 = the head's rim; x to the right ear, y to the nose
  y: number;
  shown: boolean;
  motor: boolean;
}

export interface Task {
  key: string;
  label: string;
  chance: number;
  mean: number;
  ci: [number, number];
  values: number[];
}

export interface CurvePoint {
  k: number;
  minutes: number;
  mean: number;
  ci: [number, number];
}

export interface ExplainData {
  electrodes: Electrode[];
  erd: Record<"affected_hand" | "sixth_finger", { values: number[]; mean: number }>;
  tasks: Task[];
  leak: {
    subjects: string[];
    replica: number[];
    leakfree: number[];
    mean_replica: number;
    mean_leakfree: number;
    mean_diff_points: number;
    n_positive: number;
    published: [number, number];
  };
  calibration: { scratch: CurvePoint[]; transfer: CurvePoint[] };
  switch: { detection: number; detection_ci: [number, number]; false_per_minute: number; latency_s: number };
  demo: { subject: string; held_out_bal_acc: number; trials: number; training_trials: number; model_bytes: number };
}

export const data = raw as unknown as ExplainData;

export const pct = (v: number) => `${Math.round(v * 100)}%`;
