import type { Prediction } from "./types";

/** Last resort: precomputed predictions from the bundle, labelled as a replay on screen. */
export async function loadReplay(_bundleUrl: string): Promise<Prediction[]> {
  throw new Error("loadReplay is not implemented yet");
}
