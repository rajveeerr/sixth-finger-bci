// Messages sent by the server on /ws/stream. Mirrors server/app/stream.py.

export type Mode = "trial" | "continuous";
// Where predictions come from (the `source` field of a prediction).
export type Source = "server" | "browser" | "replay";
// The states of the source state machine (01-ARCHITECTURE.md §5); the badge shows these.
export type SourceState = "connecting" | "server" | "loading-browser" | "browser" | "replay";

export interface ClassInfo {
  id: number;
  name: string;
  label: string;
  command: string;
}

export interface Hello {
  type: "hello";
  protocol: number;
  server_version: string;
  mode: Mode;
  speed: number;
  n_trials: number;
  sfreq: number;
  display_sfreq: number;
  display_channels: string[];
  classes: ClassInfo[];
  window: { start_s: number; end_s: number };
  synthetic: boolean;
  model: { name: string; method: string; sha256: string };
}

export interface TrialStart {
  type: "trial_start";
  trial: number;
  pass: number;
  uid: string;
  n_samples: number;
  duration_s: number;
  cue_onset_s: number;
}

export interface Phase {
  type: "phase";
  trial: number;
  t: number;
  phase: "rest" | "prepare" | "imagery";
  truth: string | null;
}

export interface EegChunk {
  type: "eeg";
  trial: number;
  t: number;
  data: number[][]; // display channels x samples, microvolts
}

export interface Prediction {
  type: "prediction";
  trial: number;
  t: number;
  window: "rest" | "imagery" | "sliding";
  window_s: [number, number];
  probs: number[];
  label_id: number;
  label: string;
  command: string;
  confidence: number;
  truth: string | null;
  correct: boolean | null;
  latency_ms: number;
  source: Source;
  smoothed?: number[];
  experimental?: boolean;
}

export interface TrialEnd {
  type: "trial_end";
  trial: number;
}

export interface Status {
  type: "status";
  paused: boolean;
  speed: number;
}

export interface StreamEnd {
  type: "end";
  n_trials: number;
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

export type ServerMessage =
  | Hello
  | TrialStart
  | Phase
  | EegChunk
  | Prediction
  | TrialEnd
  | Status
  | StreamEnd
  | ErrorMessage;

export type ControlMessage =
  | { type: "pause" }
  | { type: "resume" }
  | { type: "speed"; value: number }
  | { type: "jump"; trial: number };
