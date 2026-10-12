import { describe, expect, it, vi } from "vitest";
import type { StreamHandlers } from "./connection";
import { DemoController } from "./demoController";
import { readDemoBundle } from "./demoBundle.testutil";
import type { Predictor, Timer } from "./localStream";
import type { ServerMessage, SourceState } from "./types";

const bundle = readDemoBundle();
const ok: Predictor = { source: "browser", sliding: true, predict: async () => ({ probs: [0.6, 0.3, 0.1], latencyMs: 1 }) };
const broken: Predictor = { source: "browser", sliding: true, predict: async () => { throw new Error("wasm"); } };
const replay: Predictor = { source: "replay", sliding: false, predict: async () => ({ probs: [0.2, 0.2, 0.6], latencyMs: 0 }) };

// Virtual time that also yields to the event loop, so the controller's promises settle.
const timer: Timer = { now: () => 0, sleep: () => new Promise((r) => setTimeout(r, 0)) };

function setup(opts: { server: "hello" | "fail"; decoder: Predictor | "missing" }) {
  const sources: SourceState[] = [];
  const messages: ServerMessage[] = [];
  let handlers!: StreamHandlers;
  const c = new DemoController({
    serverUrl: "http://localhost:8000",
    mode: "trial",
    speed: 1,
    onMessage: (m) => messages.push(m),
    onSource: (s) => sources.push(s),
    connect: (_u, _m, h) => {
      handlers = h;
      setTimeout(() => (opts.server === "hello" ? h.onMessage({ type: "hello" } as ServerMessage) : h.onClose("timeout")), 0);
      return { send: () => {}, close: () => {} };
    },
    loadBundle: async () => bundle,
    loadDecoder: async () => {
      if (opts.decoder === "missing") throw new Error("no wasm");
      return opts.decoder;
    },
    loadReplay: async () => replay,
    timer,
  });
  return { c, sources, messages, server: () => handlers };
}

const settle = (ms = 30) => new Promise((r) => setTimeout(r, ms));
// Wait for a condition rather than a fixed time: the suite may run on a busy machine.
const until = (check: () => void) => vi.waitFor(check, { timeout: 5000, interval: 10 });

describe("DemoController", () => {
  it("uses the server when it says hello", async () => {
    const { c, sources } = setup({ server: "hello", decoder: ok });
    c.start();
    await settle();
    expect(sources).toEqual(["connecting", "server"]);
    c.stop();
  });

  it("falls back to the in-browser model when the server fails", async () => {
    const { c, sources, messages } = setup({ server: "fail", decoder: ok });
    c.start();
    await until(() => expect(messages.some((m) => m.type === "prediction" && m.source === "browser")).toBe(true));
    expect(sources).toEqual(["connecting", "loading-browser", "browser"]);
    c.stop();
  });

  it("moves to the replay when the model cannot load", async () => {
    const { c, sources } = setup({ server: "fail", decoder: "missing" });
    c.start();
    await until(() => expect(sources).toEqual(["connecting", "loading-browser", "replay"]));
    c.stop();
  });

  it("moves to the replay when in-browser inference throws", async () => {
    const { c, sources, messages } = setup({ server: "fail", decoder: broken });
    c.start();
    await until(() => expect(messages.some((m) => m.type === "prediction" && m.source === "replay")).toBe(true));
    expect(sources).toEqual(["connecting", "loading-browser", "browser", "replay"]);
    c.stop();
  });

  it("drops to the browser when a working server disconnects", async () => {
    const { c, sources, server } = setup({ server: "hello", decoder: ok });
    c.start();
    await settle();
    server().onClose("closed");
    await until(() => expect(sources).toEqual(["connecting", "server", "loading-browser", "browser"]));
    c.stop();
  });
});
