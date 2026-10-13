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

export interface Scored {
  mean: number;
  ci: [number, number];
  n: number;
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
  switch: { detection: number; detection_ci: [number, number]; false_per_minute: number; latency_s: number; n: number };
  later: {
    same_session: number;
    post: { as_is: Scored; re_setup: Scored };
    follow: { as_is: Scored; re_setup: Scored };
  };
  elsewhere: {
    motor: { dataset: string; leaky: number; fair: number; points: number; n: number }[];
    depression: { dataset: string; pipeline: string; leaky: number; fair: number; points: number; n: number }[];
    depression_shuffled: { leaky: number; fair: number; shuffles: number };
  };
  runtime: { csp_lda_fit_s: number; pretrain_s_median: number; pretrain_n: number; pretrain_on_gpu: boolean };
  demo: {
    subject: string;
    held_out_bal_acc: number;
    chosen_by_bal_acc: number;
    group_median_bal_acc: number;
    trials: number;
    trials_total: number;
    training_trials: number;
    model_bytes: number;
    parameters: number;
  };
}

export const data = raw as unknown as ExplainData;

export const pct = (v: number) => `${Math.round(v * 100)}%`;
