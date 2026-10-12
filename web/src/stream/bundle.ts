// The demo bundle (web/public/demo): manifest, held-out trials and the exported decoder.
// Mirrors server/app/bundle.py; both read exactly the same files.

import type { ClassInfo } from "./types";

export interface PreprocessOp {
  op: "scale" | "spatial_filter" | "channel_standardize";
  factor?: number | null;
  matrix?: number[][] | null;
  mean?: number[] | null;
  std?: number[] | null;
}

export interface TrialInfo {
  index: number;
  uid: string;
  label: number;
  cue_onset_s: number;
  n_samples: number;
  offset_bytes: number;
}

export interface Manifest {
  schema_version: number;
  created_at: string;
  synthetic: boolean;
  source: {
    dataset: string;
    doi: string;
    license: string;
    subject: string;
    session: string;
    runs: number[];
    attribution: string;
  };
  sfreq: number;
  channels: string[];
  display_channels: string[];
  display_decimation: number;
  units: "uV";
  classes: ClassInfo[];
  window: { start_s: number; end_s: number };
  model: {
    file: string;
    sha256: string;
    input_name: string;
    output_name: string;
    output: "probabilities" | "logits";
    n_channels: number;
    n_times: number;
    name: string;
    method: string;
    trained_on: string;
    notes: string;
  };
  preprocessing: PreprocessOp[];
  encoding: { dtype: "int16" | "float32"; scale_uv: number };
  trials_file: string;
  trials_sha256: string;
  predictions_file: string;
  trials: TrialInfo[];
}

export interface LoadedBundle {
  base: string;
  manifest: Manifest;
  /** A trial as one Float32Array per channel, in microvolts. */
  trial(index: number): Float32Array[];
}

/** Decode the trials file (little-endian, as the Python writer stores it). */
export function parseBundle(base: string, manifest: Manifest, buffer: ArrayBuffer): LoadedBundle {
  const nCh = manifest.channels.length;
  const { dtype, scale_uv: scale } = manifest.encoding;
  const itemsize = dtype === "int16" ? 2 : 4;
  const expected = manifest.trials.reduce((n, t) => n + t.n_samples * nCh * itemsize, 0);
  if (buffer.byteLength !== expected) {
    throw new Error(`trials file has ${buffer.byteLength} bytes, the manifest says ${expected}`);
  }
  const view = new DataView(buffer);
  return {
    base,
    manifest,
    trial(index) {
      const t = manifest.trials[index];
      return Array.from({ length: nCh }, (_, c) => {
        const row = new Float32Array(t.n_samples);
        const start = t.offset_bytes + c * t.n_samples * itemsize;
        for (let i = 0; i < t.n_samples; i++) {
          const at = start + i * itemsize;
          const v = dtype === "int16" ? view.getInt16(at, true) : view.getFloat32(at, true);
          row[i] = v * scale;
        }
        return row;
      });
    },
  };
}

export async function loadBundle(base = "/demo"): Promise<LoadedBundle> {
  const res = await fetch(`${base}/manifest.json`);
  if (!res.ok) throw new Error(`manifest.json: HTTP ${res.status}`);
  const manifest: Manifest = await res.json();
  const trials = await fetch(`${base}/${manifest.trials_file}`);
  if (!trials.ok) throw new Error(`${manifest.trials_file}: HTTP ${trials.status}`);
  return parseBundle(base, manifest, await trials.arrayBuffer());
}

/** Samples [start, stop) of every channel as one channel-major array (nCh × (stop - start)). */
export function windowOf(rows: Float32Array[], start: number, stop: number): Float32Array {
  const n = stop - start;
  const out = new Float32Array(rows.length * n);
  rows.forEach((row, c) => out.set(row.subarray(start, stop), c * n));
  return out;
}

/** The same operations, in the same order, as apply_preprocessing in server/app/bundle.py. */
export function applyPreprocessing(
  window: Float32Array,
  nCh: number,
  nT: number,
  ops: PreprocessOp[],
): Float32Array {
  let x = Float32Array.from(window);
  for (const op of ops) {
    if (op.op === "scale") {
      const f = Math.fround(op.factor ?? 1);
      for (let i = 0; i < x.length; i++) x[i] = Math.fround(x[i] * f);
    } else if (op.op === "spatial_filter") {
      const m = op.matrix ?? [];
      const out = new Float32Array(x.length);
      for (let r = 0; r < nCh; r++) {
        for (let t = 0; t < nT; t++) {
          let acc = 0;
          for (let c = 0; c < nCh; c++) acc += Math.fround(m[r][c]) * x[c * nT + t];
          out[r * nT + t] = acc;
        }
      }
      x = out;
    } else if (op.op === "channel_standardize") {
      const mean = op.mean ?? [];
      const std = op.std ?? [];
      for (let c = 0; c < nCh; c++) {
        for (let t = 0; t < nT; t++) {
          x[c * nT + t] = (x[c * nT + t] - mean[c]) / std[c];
        }
      }
    }
  }
  return x;
}

export function softmax(v: number[]): number[] {
  const m = Math.max(...v);
  const e = v.map((x) => Math.exp(x - m));
  const s = e.reduce((a, b) => a + b, 0);
  return e.map((x) => x / s);
}
