// Streams the bundle in the browser with the same messages, order and timing as
// server/app/stream.py (StreamSession), decoding with a Predictor: the in-browser
// model or the offline replay of the same model.

import { CommandGate } from "../lib/gate";
import { windowOf, type LoadedBundle } from "./bundle";
import { trialTimeline, type TimelineEvent } from "./timeline";
import type { Mode, Prediction, ServerMessage, Source } from "./types";

export interface Decision {
  probs: number[];
  latencyMs: number;
}

export interface Predictor {
  source: Source;
  /** Whether any window can be decoded (continuous mode); replay knows only its stored ones. */
  sliding: boolean;
  /** Probabilities for a channel-major window in microvolts (nCh × nT). */
  predict(
    x: Float32Array,
    nCh: number,
    nT: number,
    ref: { trial: number; window: Prediction["window"] },
  ): Promise<Decision>;
}

export interface Timer {
  now(): number; // milliseconds
  sleep(ms: number): Promise<void>;
}

export const realTimer: Timer = {
  now: () => performance.now(),
  sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
};

export interface LocalStreamOptions {
  mode: Mode;
  speed: number;
  startTrial?: number;
  loop?: boolean;
  chunkSamples?: number;
  hopSeconds?: number;
  maxSpeed?: number;
  timer?: Timer;
}

type Send = (message: ServerMessage) => void;

const round = (v: number, d: number) => Math.round(v * 10 ** d) / 10 ** d;

export class LocalStream {
  readonly mode: Mode;
  speed: number;
  paused = false;
  private readonly timer: Timer;
  private readonly opts: Required<Omit<LocalStreamOptions, "timer" | "mode" | "speed">>;
  private anchorWall = 0;
  private anchorData = 0;
  private dataTime = 0;
  private jumpTo: number | null = null;
  private stopped = false;
  private wake: (() => void) | null = null;
  private history: Float32Array[] | null = null;
  private readonly gate = new CommandGate();
  private send: Send = () => {};

  constructor(
    private readonly bundle: LoadedBundle,
    private readonly predictor: Predictor,
    options: LocalStreamOptions,
  ) {
    // The replay holds only the trial windows, so continuous mode needs a live model.
    this.mode = options.mode === "continuous" && predictor.sliding ? "continuous" : "trial";
    this.timer = options.timer ?? realTimer;
    this.opts = {
      startTrial: options.startTrial ?? 0,
      loop: options.loop ?? true,
      chunkSamples: options.chunkSamples ?? 20,
      hopSeconds: options.hopSeconds ?? 0.5,
      maxSpeed: options.maxSpeed ?? 8,
    };
    this.speed = this.clamp(options.speed);
  }

  private clamp(speed: number): number {
    return Math.min(Math.max(speed, 0.25), this.opts.maxSpeed);
  }

  private status(): ServerMessage {
    return { type: "status", paused: this.paused, speed: this.speed };
  }

  private reanchor() {
    this.anchorWall = this.timer.now();
    this.anchorData = this.dataTime;
  }

  pause() {
    this.paused = true;
    this.send(this.status());
  }

  resume() {
    this.reanchor();
    this.paused = false;
    this.wake?.();
    this.send(this.status());
  }

  setSpeed(value: number) {
    this.reanchor();
    this.speed = this.clamp(value);
    this.send(this.status());
  }

  jump(trial: number) {
    this.jumpTo = ((trial % this.bundle.manifest.trials.length) + this.bundle.manifest.trials.length) %
      this.bundle.manifest.trials.length;
    if (this.paused) this.resume();
    else this.send(this.status());
  }

  stop() {
    this.stopped = true;
    this.wake?.();
  }

  private async waitUntil(dataTime: number) {
    while (this.paused && !this.stopped) {
      await new Promise<void>((resolve) => {
        this.wake = resolve;
      });
      this.wake = null;
    }
    const due = this.anchorWall + ((dataTime - this.anchorData) / this.speed) * 1000;
    const delay = due - this.timer.now();
    if (delay > 0) await this.timer.sleep(delay);
    this.dataTime = dataTime;
  }

  private hello(): ServerMessage {
    const m = this.bundle.manifest;
    return {
      type: "hello",
      protocol: 1,
      server_version: `browser-${this.predictor.source}`,
      mode: this.mode,
      speed: this.speed,
      n_trials: m.trials.length,
      sfreq: m.sfreq,
      display_sfreq: m.sfreq / m.display_decimation,
      display_channels: m.display_channels,
      classes: m.classes,
      window: m.window,
      synthetic: m.synthetic,
      model: { name: m.model.name, method: m.model.method, sha256: m.model.sha256 },
    };
  }

  private async prediction(
    trial: number,
    t: number,
    window: Prediction["window"],
    x: Float32Array,
    truth: string | null,
    span: [number, number],
  ): Promise<Prediction> {
    const m = this.bundle.manifest;
    const nCh = m.channels.length;
    const { probs, latencyMs } = await this.predictor.predict(x, nCh, x.length / nCh, { trial, window });
    const labelId = probs.indexOf(Math.max(...probs));
    const label = m.classes[labelId].name;
    const message: Prediction = {
      type: "prediction",
      trial,
      t: round(t, 3),
      window,
      window_s: [round(span[0] / m.sfreq, 3), round(span[1] / m.sfreq, 3)],
      probs: probs.map((p) => round(p, 5)),
      label_id: labelId,
      label,
      command: m.classes[labelId].command,
      confidence: round(probs[labelId], 5),
      truth,
      correct: truth === null ? null : label === truth,
      latency_ms: round(latencyMs, 3),
      source: this.predictor.source,
    };
    if (this.mode === "continuous") {
      const active = this.gate.update(probs);
      message.smoothed = this.gate.smoothed.map((p) => round(p, 5));
      message.command = m.classes[active].command;
      message.experimental = true;
    }
    return message;
  }

  async run(send: Send): Promise<void> {
    this.send = send;
    this.reanchor();
    send(this.hello());
    const n = this.bundle.manifest.trials.length;
    let index = this.opts.startTrial % n;
    let passes = 0;
    while (!this.stopped) {
      await this.streamTrial(index, passes, send);
      if (this.stopped) return;
      if (this.jumpTo !== null) {
        index = this.jumpTo;
        this.jumpTo = null;
        continue;
      }
      index = (index + 1) % n;
      if (index === 0) {
        passes += 1;
        if (!this.opts.loop) {
          send({ type: "end", n_trials: n });
          return;
        }
      }
    }
  }

  private async emitEvent(event: TimelineEvent, index: number, rows: Float32Array[], truthName: string, send: Send) {
    const m = this.bundle.manifest;
    const t = event.sample / m.sfreq;
    if (event.kind === "phase") {
      const truth = event.phase === "rest" ? m.classes[0].name : event.phase === "prepare" ? null : truthName;
      send({ type: "phase", trial: index, t: round(t, 3), phase: event.phase!, truth });
    } else if (this.mode === "trial") {
      const truth = event.window === "rest" ? m.classes[0].name : truthName;
      const x = windowOf(rows, event.start, event.stop);
      send(await this.prediction(index, t, event.window!, x, truth, [event.start, event.stop]));
    }
  }

  private async streamTrial(index: number, passes: number, send: Send) {
    const m = this.bundle.manifest;
    const info = m.trials[index];
    const rows = this.bundle.trial(index);
    const truthName = m.classes[info.label].name;
    const cue = Math.round(info.cue_onset_s * m.sfreq);
    const events = trialTimeline(info, m.sfreq, m.window);
    const displayIdx = m.display_channels.map((name) => m.channels.indexOf(name));
    const nTimes = m.model.n_times;
    const hop = Math.round(this.opts.hopSeconds * m.sfreq);
    const prev = this.history?.[0].length ?? 0;
    const context = rows.map((row, c) => {
      const joined = new Float32Array(prev + row.length);
      if (this.history) joined.set(this.history[c]);
      joined.set(row, prev);
      return joined;
    });
    const baseTime = this.dataTime;
    send({
      type: "trial_start",
      trial: index,
      pass: passes,
      uid: info.uid,
      n_samples: info.n_samples,
      duration_s: round(info.n_samples / m.sfreq, 3),
      cue_onset_s: info.cue_onset_s,
    });
    let next = 0;
    let pos = 0;
    while (pos < info.n_samples) {
      while (next < events.length && events[next].sample <= pos) {
        await this.emitEvent(events[next], index, rows, truthName, send);
        next += 1;
      }
      const stop = Math.min(pos + this.opts.chunkSamples, info.n_samples);
      await this.waitUntil(baseTime + stop / m.sfreq);
      if (this.stopped || this.jumpTo !== null) return;
      const data = displayIdx.map((c) => {
        const out: number[] = [];
        for (let i = pos; i < stop; i += m.display_decimation) out.push(round(rows[c][i], 2));
        return out;
      });
      send({ type: "eeg", trial: index, t: round(pos / m.sfreq, 3), data });
      if (this.mode === "continuous") {
        for (let end = pos + 1; end <= stop; end++) {
          if (end % hop === 0 && prev + end >= nTimes) {
            const x = windowOf(context, prev + end - nTimes, prev + end);
            const centre = end - Math.floor(nTimes / 2);
            const truth = centre >= cue ? truthName : m.classes[0].name;
            send(await this.prediction(index, end / m.sfreq, "sliding", x, truth, [end - nTimes, end]));
          }
        }
      }
      pos = stop;
    }
    while (next < events.length) {
      await this.emitEvent(events[next], index, rows, truthName, send);
      next += 1;
    }
    send({ type: "trial_end", trial: index });
    this.history = rows.map((row) => row.slice(row.length - nTimes));
  }
}
