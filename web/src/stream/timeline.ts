// Phase changes and decode points of one trial: a port of trial_timeline in
// server/app/stream.py, so the browser streams with exactly the server's timing.

import type { TrialInfo } from "./bundle";

export interface TimelineEvent {
  sample: number;
  kind: "phase" | "decode";
  phase?: "rest" | "prepare" | "imagery";
  window?: "rest" | "imagery";
  start: number;
  stop: number;
}

/** In samples from the rest onset; a window is decoded the moment its last sample arrives. */
export function trialTimeline(
  trial: TrialInfo,
  sfreq: number,
  window: { start_s: number; end_s: number },
): TimelineEvent[] {
  const cue = Math.round(trial.cue_onset_s * sfreq);
  const w0 = Math.round(window.start_s * sfreq);
  const w1 = Math.round(window.end_s * sfreq);
  if (cue + w1 > trial.n_samples) throw new Error(`trial ${trial.uid} ends before its imagery window`);
  const events: TimelineEvent[] = [
    { sample: 0, kind: "phase", phase: "rest", start: 0, stop: 0 },
    { sample: Math.max(cue - Math.round(sfreq), 0), kind: "phase", phase: "prepare", start: 0, stop: 0 },
    { sample: cue, kind: "phase", phase: "imagery", start: 0, stop: 0 },
    { sample: w1, kind: "decode", window: "rest", start: w0, stop: w1 },
    { sample: cue + w1, kind: "decode", window: "imagery", start: cue + w0, stop: cue + w1 },
  ];
  // Stable sort by sample, phases before decodes at the same sample (as in Python).
  return events
    .map((e, i) => ({ e, i }))
    .sort((a, b) => a.e.sample - b.e.sample || Number(a.e.kind !== "phase") - Number(b.e.kind !== "phase") || a.i - b.i)
    .map(({ e }) => e);
}
