import { afterEach, describe, expect, it, vi } from "vitest";
import type { Manifest } from "./bundle";
import { loadRemoteDecoder } from "./remoteDecoder";

const manifest = { model: { sha256: "abc" } } as unknown as Manifest;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

describe("loadRemoteDecoder", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("refuses a server whose model is not the bundle's", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ ok: true, sha256: "other" })),
    );
    await expect(loadRemoteDecoder("/api/decode", manifest)).rejects.toThrow(/not the bundle/);
  });

  it("posts the window as float32 bytes and returns the server's probabilities", async () => {
    const fetch = vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === "POST" ? json({ probs: [0.7, 0.2, 0.1], latency_ms: 3 }) : json({ ok: true, sha256: "abc" }),
    );
    vi.stubGlobal("fetch", fetch);
    const p = await loadRemoteDecoder("/api/decode", manifest);
    const x = new Float32Array([1, 2, 3, 4]);
    const out = await p.predict(x, 2, 2, { trial: 0, window: "rest" });
    expect(out).toEqual({ probs: [0.7, 0.2, 0.1], latencyMs: 3 });
    const body = fetch.mock.calls[1][1]!.body as Uint8Array;
    expect(Array.from(new Float32Array(body.buffer))).toEqual([1, 2, 3, 4]);
    expect(p.source).toBe("server");
  });

  it("fails a window the server refuses, so the page can fall back", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) =>
        init?.method === "POST" ? json({ error: "bad" }, 400) : json({ ok: true, sha256: "abc" }),
      ),
    );
    const p = await loadRemoteDecoder("/api/decode", manifest);
    await expect(p.predict(new Float32Array(4), 2, 2, { trial: 0, window: "rest" })).rejects.toThrow(/400/);
  });
});
