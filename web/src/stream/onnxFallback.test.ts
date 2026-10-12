/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";
import * as ort from "onnxruntime-web";
import { describe, expect, it } from "vitest";
import { windowOf } from "./bundle";
import { DEMO_DIR, readDemoBundle } from "./demoBundle.testutil";
import { decoderFromBytes } from "./onnxFallback";
import { replayPredictor, type ReplayFile } from "./replay";

// In Node, onnxruntime-web loads its wasm from the package itself.
ort.env.wasm.wasmPaths = join(__dirname, "..", "..", "node_modules", "onnxruntime-web", "dist") + "/";

const bundle = readDemoBundle();
const m = bundle.manifest;
const stored: ReplayFile = JSON.parse(readFileSync(join(DEMO_DIR, m.predictions_file), "utf8"));
const bytes = (() => {
  const raw = readFileSync(join(DEMO_DIR, m.model.file));
  return raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
})();

function windowFor(trial: number, which: "rest" | "imagery") {
  const rows = bundle.trial(trial);
  const w0 = Math.round(m.window.start_s * m.sfreq);
  const w1 = Math.round(m.window.end_s * m.sfreq);
  const at = which === "rest" ? 0 : Math.round(m.trials[trial].cue_onset_s * m.sfreq);
  return windowOf(rows, at + w0, at + w1);
}

describe("browser decoder", () => {
  it("matches the bundle's offline predictions (|Δp| < 1e-4)", async () => {
    const decoder = await decoderFromBytes(bytes, m);
    let worst = 0;
    for (const item of stored.items) {
      const { probs } = await decoder.predict(windowFor(item.trial, item.window), 40, 1000, item);
      probs.forEach((p, i) => (worst = Math.max(worst, Math.abs(p - item.probs[i]))));
    }
    expect(stored.items.length).toBe(2 * m.trials.length);
    expect(worst).toBeLessThan(1e-4);
  }, 60_000);

  it("refuses a model that does not match the manifest", async () => {
    await expect(decoderFromBytes(new ArrayBuffer(8), m)).rejects.toThrow(/checksum/);
  });
});

describe("replay", () => {
  it("answers with the stored prediction of each window", async () => {
    const replay = replayPredictor(stored, m);
    const item = stored.items[3];
    const { probs } = await replay.predict(new Float32Array(0), 40, 1000, item);
    expect(probs).toEqual(item.probs);
    expect(replay.sliding).toBe(false);
  });

  it("refuses predictions made by another model", () => {
    expect(() => replayPredictor({ ...stored, model_sha256: "x" }, m)).toThrow(/another model/);
  });
});
