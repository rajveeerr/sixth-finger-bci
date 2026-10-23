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

/** A score over the patients, and how many reached 80% and 90%. */
export interface PerPatient {
  mean: number;
  ci: [number, number];
  values: number[];
  n: number;
  n_ge_80: number;
  n_ge_90: number;
}

/** A demo reading scored on the demo patient's stored held-out predictions. */
export interface Counted {
  acc: number;
  right: number;
  n: number;
}

/** A task's row of the benchmark: each method's mean over the patients, and the task's best. */
export interface BenchRow {
  key: "T3_sf_vs_rest" | "T1_ah_vs_sf" | "T2_rest_ah_sf";
  chance: number;
  csp_lda: number;
  ts_lr: number;
  eegnet_scratch: number;
  best: {
    method: "ts_lr_c14" | "eegnet_ea_ft" | "eegnet_scratch";
    mean: number;
    /** The switch acting only when sure: right on this share of the windows it acts on... */
    sure?: number;
    /** ...and acting on this share of them. */
    sure_share?: number;
    /** The method that scored higher on runs 3 and 4, but lower on runs 1 and 2 where the choice was made. */
    not_chosen?: number;
  };
}

/** A score after some practice, and how long that practice took. */
export interface Practised {
  mean: number;
  minutes: number;
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
  /** The demo's network played as if live (answer 4). */
  switch: {
    detection: number;
    detection_ci: [number, number];
    false_per_minute: number;
    latency_s: number;
    n: number;
    /** Question 3's simpler model played the same way, learned as rest or any movement. */
    central: { detection: number; false_per_minute: number; latency_s: number; n: number };
  };
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
    /** Rest against the two movements added, on every rest and imagery window. */
    move_rest: Counted;
    /** The likelier of hand and sixth finger, on the imagery windows. */
    hand_finger: Counted;
  };
  /** The sixth finger as its own command (question 3); runs 1 and 2 learned, 3 and 4 tested. */
  sixth: {
    /** Sixth finger or rest, the simple method on the 14 sensors over the movement strip. */
    rest: PerPatient & { all_sensors: number };
    /** Hand or sixth finger, the best method: EEGNet learned from other patients, then adjusted. */
    which: PerPatient;
    /** The switch acting only when sure, how sure set for each patient on runs 1 and 2 alone. */
    sure: { acc: number; ci: [number, number]; share: number; n: number; n_ge_90: number; no_decision: number };
    /** Accuracy on each patient's surest decisions, by the share of decisions taken. */
    coverage: { share: number; acc: number; ci: [number, number] }[];
    /** How often the switch turns on, on every decision and only when sure. */
    fires: Record<"rest" | "hand" | "finger", { all: number; sure: number }>;
    /** Hand or sixth finger with the best method, acting only when sure. */
    which_sure: { acc: number; share: number; n: number; no_decision: number };
    /** Healthy people, two or three grasps of one hand, learned one day and tested a week later. */
    healthy: { people: number; pairs: [number, number]; three: [number, number] };
  };
  /** Every headline score in one place, with six digits so one decimal rounds as the paper's. */
  benchmark: {
    n: number;
    tasks: BenchRow[];
    /** Rest, hand or sixth finger for a new patient, after one practice trial of each, and after twenty. */
    setup: Record<"from_others" | "from_nothing" | "from_nothing_end", Practised>;
    /** Two weeks later, the first session's model unchanged, and after k practice trials of each movement. */
    later: { as_is: number; re_setup: number; k: number };
    /** Played as if live: share of imagined movements caught, and mistakes a minute of rest. */
    live: Record<"demo" | "switch", { detection: number; false_per_minute: number }>;
    /** Hand or sixth finger with the paper's method, tested the paper's way and fairly. */
    leak: { paper_way: number; fair: number };
    model: { parameters: number; bytes: number };
  };
}

export const data = raw as unknown as ExplainData;

/** The benchmark's row for a task. */
export function benchRow(key: BenchRow["key"]): BenchRow {
  const row = data.benchmark.tasks.find((t) => t.key === key);
  if (!row) throw new Error(`No benchmark row ${key}`);
  return row;
}

export const pct = (v: number) => `${Math.round(v * 100)}%`;

/** A share with one decimal, as the paper and the benchmark print it. */
export const pct1 = (v: number) => `${(v * 100).toFixed(1)}%`;

/** A range of shares in words, one number when both ends round to it. */
export function pctRange([lo, hi]: [number, number]): string {
  const [a, b] = [Math.round(lo * 100), Math.round(hi * 100)];
  return a === b ? `${a}%` : `${a} to ${b}%`;
}
