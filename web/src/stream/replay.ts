// Last resort: the predictions the same model made offline (predictions.json of the
// bundle), streamed on the same timing and labelled "replay" on screen.

import type { Manifest } from "./bundle";
import type { Predictor } from "./localStream";

export interface ReplayFile {
  schema_version: number;
  model_sha256: string;
  items: { trial: number; window: "rest" | "imagery"; probs: number[]; label_id: number }[];
}

export function replayPredictor(file: ReplayFile, m: Manifest): Predictor {
  if (file.model_sha256 !== m.model.sha256) {
    throw new Error("predictions.json was made by another model than the manifest's");
  }
  const byKey = new Map(file.items.map((it) => [`${it.trial}:${it.window}`, it.probs]));
  return {
    source: "replay",
    sliding: false,
    async predict(_x, _nCh, _nT, ref) {
      const probs = byKey.get(`${ref.trial}:${ref.window}`);
      if (!probs) throw new Error(`no stored prediction for trial ${ref.trial}, ${ref.window}`);
      return { probs, latencyMs: 0 };
    },
  };
}

export async function loadReplay(base: string, m: Manifest): Promise<Predictor> {
  const res = await fetch(`${base}/${m.predictions_file}`);
  if (!res.ok) throw new Error(`${m.predictions_file}: HTTP ${res.status}`);
  return replayPredictor(await res.json(), m);
}
