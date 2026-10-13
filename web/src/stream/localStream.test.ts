import { describe, expect, it } from "vitest";
import { readDemoBundle } from "./demoBundle.testutil";
import { LocalStream, type Predictor, type Timer } from "./localStream";
import type { Prediction, ServerMessage } from "./types";

/** Virtual time: sleeping advances the clock at once, so a 15 s trial runs instantly. */
function fakeTimer(): Timer & { log: number[] } {
  let now = 0;
  return {
    log: [],
    now: () => now,
    sleep: async (ms) => {
      now += ms;
    },
  };
}

const restPredictor: Predictor = {
  source: "browser",
  sliding: true,
  predict: async () => ({ probs: [0.7, 0.2, 0.1], latencyMs: 1 }),
};

async function firstTrial(speed: number, mode: "trial" | "continuous" = "trial") {
  const bundle = readDemoBundle();
  const timer = fakeTimer();
  const stream = new LocalStream(bundle, restPredictor, { mode, speed, loop: false, timer });
  const messages: { at: number; m: ServerMessage }[] = [];
  const run = stream.run((m) => {
    messages.push({ at: timer.now(), m });
    if (m.type === "trial_end") stream.stop();
  });
  await run;
  return { bundle, messages };
}

describe("LocalStream", () => {
  it("keeps the signal flowing while a slow model answers, and sends its decisions in order", async () => {
    const bundle = readDemoBundle();
    const timer = fakeTimer();
    const slow: Predictor = {
      source: "server",
      sliding: true,
      predict: () => new Promise((r) => setTimeout(() => r({ probs: [0.7, 0.2, 0.1], latencyMs: 300 }), 5)),
    };
    const stream = new LocalStream(bundle, slow, { mode: "trial", speed: 1, loop: false, timer });
    const messages: ServerMessage[] = [];
    await stream.run((m) => {
      messages.push(m);
      if (m.type === "trial_end") stream.stop();
    });
    const preds = messages.filter((m) => m.type === "prediction") as Prediction[];
    expect(preds.map((p) => p.window)).toEqual(["rest", "imagery"]);
    const first = messages.findIndex((m) => m.type === "prediction");
    const eegBefore = messages.slice(0, first).filter((m) => m.type === "eeg").length;
    expect(eegBefore).toBeGreaterThan((5 * bundle.manifest.sfreq) / 20); // more than the 5 s the window needed
    expect(messages[messages.length - 1].type).toBe("trial_end");
  });

  it("sends the server's messages in the server's order", async () => {
    const { messages } = await firstTrial(1);
    const kinds = messages.map(({ m }) => m.type).filter((t) => t !== "eeg");
    expect(kinds).toEqual([
      "hello", "trial_start", "phase", "prediction", "phase", "phase", "prediction", "trial_end",
    ]);
  });

  it("decodes the imagery window at cue + 5 s of data, on time at speed 1", async () => {
    const { bundle, messages } = await firstTrial(1);
    const cue = bundle.manifest.trials[0].cue_onset_s;
    const preds = messages.filter(({ m }) => m.type === "prediction") as { at: number; m: Prediction }[];
    expect(preds.map(({ m }) => m.window)).toEqual(["rest", "imagery"]);
    expect(preds[0].m.t).toBe(5);
    expect(preds[1].m.t).toBeCloseTo(cue + 5, 2);
    expect(preds[1].at / 1000).toBeCloseTo(cue + 5, 1); // wall time follows the data
    expect(preds[1].m.truth).toBe(bundle.manifest.classes[bundle.manifest.trials[0].label].name);
  });

  it("runs faster at a higher speed", async () => {
    const { bundle, messages } = await firstTrial(8);
    const end = messages[messages.length - 1].at / 1000;
    const duration = bundle.manifest.trials[0].n_samples / bundle.manifest.sfreq;
    expect(end).toBeCloseTo(duration / 8, 1);
  });

  it("streams decimated EEG of the display channels", async () => {
    const { bundle, messages } = await firstTrial(1);
    const eeg = messages.find(({ m }) => m.type === "eeg")!.m as Extract<ServerMessage, { type: "eeg" }>;
    expect(eeg.data.length).toBe(bundle.manifest.display_channels.length);
    expect(eeg.data[0].length).toBe(20 / bundle.manifest.display_decimation);
  });

  it("decodes every 0.5 s in continuous mode and marks it experimental", async () => {
    const { messages } = await firstTrial(1, "continuous");
    const preds = messages.filter(({ m }) => m.type === "prediction").map(({ m }) => m as Prediction);
    expect(preds.length).toBeGreaterThan(10);
    expect(preds.every((p) => p.window === "sliding" && p.experimental)).toBe(true);
    expect(preds[1].t - preds[0].t).toBeCloseTo(0.5, 6);
  });

  it("falls back to trial mode when the predictor cannot decode any window", async () => {
    const bundle = readDemoBundle();
    const replay: Predictor = { ...restPredictor, source: "replay", sliding: false };
    const stream = new LocalStream(bundle, replay, { mode: "continuous", speed: 1, timer: fakeTimer() });
    expect(stream.mode).toBe("trial");
  });
});
