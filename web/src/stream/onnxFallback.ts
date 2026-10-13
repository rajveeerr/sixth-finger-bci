// Runs the bundle's ONNX decoder in the browser (onnxruntime-web) when the server is
// unreachable. The model file is checked against the manifest's sha256 first, so a stale
// or partial download moves the demo on to the replay instead of decoding with it.

// The wasm-only build: about half the download of the default one, which also carries
// the WebGPU and WebNN back ends this small model never uses.
import * as ort from "onnxruntime-web/wasm";
import { applyPreprocessing, softmax, type Manifest } from "./bundle";
import type { Predictor } from "./localStream";

// One window every few seconds is cheap; one thread needs no cross-origin isolation.
ort.env.wasm.numThreads = 1;

export async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** A Predictor over an already fetched model (also used by the Node parity test). */
export async function decoderFromBytes(bytes: ArrayBuffer, m: Manifest): Promise<Predictor> {
  if ((await sha256Hex(bytes)) !== m.model.sha256) {
    throw new Error("model.onnx does not match the manifest checksum");
  }
  const session = await ort.InferenceSession.create(new Uint8Array(bytes), {
    executionProviders: ["wasm"],
  });
  return {
    source: "browser",
    sliding: true,
    async predict(x, nCh, nT) {
      const started = performance.now();
      const input = applyPreprocessing(x, nCh, nT, m.preprocessing);
      const out = await session.run({
        [m.model.input_name]: new ort.Tensor("float32", input, [1, nCh, nT]),
      });
      const v = Array.from(out[m.model.output_name].data as Float32Array);
      const probs = m.model.output === "logits" ? softmax(v) : v;
      return { probs, latencyMs: performance.now() - started };
    },
  };
}

export async function loadBrowserDecoder(base: string, m: Manifest): Promise<Predictor> {
  const res = await fetch(`${base}/${m.model.file}`);
  if (!res.ok) throw new Error(`${m.model.file}: HTTP ${res.status}`);
  return decoderFromBytes(await res.arrayBuffer(), m);
}
