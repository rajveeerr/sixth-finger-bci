import type { Prediction } from "./types";

/** Runs the bundled ONNX model in the browser when the server is unreachable. */
export interface BrowserDecoder {
  predict: (window: Float32Array, nChannels: number, nTimes: number) => Promise<number[]>;
}

export async function loadBrowserDecoder(_bundleUrl: string): Promise<BrowserDecoder> {
  throw new Error("loadBrowserDecoder is not implemented yet");
}

export type BrowserPrediction = Omit<Prediction, "source"> & { source: "browser" };
