// The model on the site's own server (web/api/decode.py on Vercel): the page streams the
// bundle as in the browser and sends each window there. Used where a WebSocket server
// cannot run; if a request fails the controller moves on to the in-browser model.

import type { Manifest } from "./bundle";
import type { Predictor } from "./localStream";

/** A cold start of the function can take a few seconds; a window should not. */
const HELLO_MS = 12_000;
const WINDOW_MS = 6_000;

async function fetchWithin(url: string, init: RequestInit, ms: number): Promise<Response> {
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: abort.signal });
  } finally {
    clearTimeout(timer);
  }
}

/** Checks the server holds the bundle's model, then decodes every window there. */
export async function loadRemoteDecoder(url: string, m: Manifest): Promise<Predictor> {
  const hello = await fetchWithin(url, { method: "GET" }, HELLO_MS);
  if (!hello.ok) throw new Error(`model server answered ${hello.status}`);
  const info = (await hello.json()) as { sha256?: string };
  if (info.sha256 !== m.model.sha256) throw new Error("the server's model is not the bundle's");
  return {
    source: "server",
    sliding: true,
    async predict(x) {
      const body = new Uint8Array(x.buffer, x.byteOffset, x.byteLength).slice();
      const res = await fetchWithin(
        url,
        { method: "POST", headers: { "content-type": "application/octet-stream" }, body },
        WINDOW_MS,
      );
      if (!res.ok) throw new Error(`model server answered ${res.status}`);
      const out = (await res.json()) as { probs: number[]; latency_ms: number };
      return { probs: out.probs, latencyMs: out.latency_ms };
    },
  };
}
