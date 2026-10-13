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

function setup(opts: { server: "hello" | "fail" | "none"; decoder: Predictor | "missing" }) {
  const sources: SourceState[] = [];
  const messages: ServerMessage[] = [];
  let handlers!: StreamHandlers;
  const c = new DemoController({
    serverUrl: opts.server === "none" ? "" : "http://localhost:8000",
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
    ping: async () => {
      throw new Error("asleep");
    },
    timer,
  });
  return { c, sources, messages, server: () => handlers };
}

const settle = (ms = 30) => new Promise((r) => setTimeout(r, ms));
// Wait for a condition rather than a fixed time: the suite may run on a busy machine.
const until = (check: () => void) => vi.waitFor(check, { timeout: 5000, interval: 10 });

function setupHttp(remote: Predictor | "down" | (() => Promise<Predictor>), ping: () => Promise<void> = async () => {
  throw new Error("asleep");
}) {
  const sources: SourceState[] = [];
  const messages: ServerMessage[] = [];
  const c = new DemoController({
    serverUrl: "",
    decodeUrl: "/api/decode",
    mode: "trial",
    speed: 1,
    onMessage: (m) => messages.push(m),
    onSource: (s) => sources.push(s),
    loadBundle: async () => bundle,
    loadDecoder: async () => ok,
    loadRemote: async () => {
      if (remote === "down") throw new Error("no function");
      return typeof remote === "function" ? remote() : remote;
    },
    loadReplay: async () => replay,
    ping,
    upgradeEveryMs: 20,
    timer,
  });
  return { c, sources, messages };
}

const onServer: Predictor = { ...ok, source: "server" };
const failing: Predictor = { source: "server", sliding: true, predict: async () => { throw new Error("502"); } };

describe("DemoController with a model server over HTTP", () => {
  it("starts in the browser while the server sleeps, and moves to it once it wakes", async () => {
    // The first connection fails (the server is still waking), so the browser stands in.
    let awake = false;
    const { c, sources } = setupHttp(
      async () => {
        if (!awake) throw new Error("waking");
        return onServer;
      },
      async () => {
        if (!awake) throw new Error("asleep");
      },
    );
    c.start();
    await until(() => expect(sources.at(-1)).toBe("browser"));
    awake = true;
    await until(() => expect(sources.at(-1)).toBe("server"));
    c.stop();
  });

  it("stays in the browser the reader chose, even when the server wakes", async () => {
    const { c, sources } = setupHttp(onServer, async () => {});
    c.start();
    await until(() => expect(sources.at(-1)).toBe("server"));
    c.useBrowser();
    await until(() => expect(sources.at(-1)).toBe("browser"));
    await settle(120);
    expect(sources.at(-1)).toBe("browser");
    c.stop();
  });

  it("goes to the in-browser model when asked, and back to the server on retry", async () => {
    const { c, sources, messages } = setupHttp(onServer);
    c.start();
    await until(() => expect(sources.at(-1)).toBe("server"));
    c.useBrowser();
    await until(() => expect(messages.some((m) => m.type === "prediction" && m.source === "browser")).toBe(true));
    c.retry();
    await until(() => expect(sources.at(-1)).toBe("server"));
    expect(sources).toEqual(["connecting", "server", "loading-browser", "browser", "connecting", "server"]);
    c.stop();
  });

  it("switches to continuous mode on the same source without starting over", async () => {
    const { c, sources, messages } = setupHttp(onServer);
    c.start();
    await until(() => expect(sources.at(-1)).toBe("server"));
    c.setMode("continuous");
    await until(() => expect(messages.some((m) => m.type === "hello" && m.mode === "continuous")).toBe(true));
    expect(sources.at(-1)).toBe("server");
    c.stop();
  });

  it("decodes every window on the server when it answers", async () => {
    const { c, sources, messages } = setupHttp(onServer);
    c.start();
    await until(() => expect(messages.some((m) => m.type === "prediction" && m.source === "server")).toBe(true));
    expect(sources).toEqual(["connecting", "server"]);
    c.stop();
  });

  it("moves to the in-browser model when the server is down or a window fails", async () => {
    for (const remote of ["down", failing] as const) {
      const { c, sources, messages } = setupHttp(remote);
      c.start();
      await until(() => expect(messages.some((m) => m.type === "prediction" && m.source === "browser")).toBe(true));
      expect(sources.at(-1)).toBe("browser");
      expect(sources).toContain("loading-browser");
      c.stop();
    }
  });
});

describe("DemoController", () => {
  it("uses the server when it says hello", async () => {
    const { c, sources } = setup({ server: "hello", decoder: ok });
    c.start();
    await settle();
    expect(sources).toEqual(["connecting", "server"]);
    c.stop();
  });

  it("starts on the in-browser model when the site has no server", async () => {
    const { c, sources, messages } = setup({ server: "none", decoder: ok });
    c.start();
    await until(() => expect(messages.some((m) => m.type === "prediction" && m.source === "browser")).toBe(true));
    expect(sources).toEqual(["loading-browser", "browser"]);
    c.retry();
    await settle();
    expect(sources.at(-1)).toBe("browser");
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

  it("connects again in the new mode when the mode changes on the streaming server", async () => {
    const { c, sources } = setup({ server: "hello", decoder: ok });
    c.start();
    await settle();
    c.setMode("continuous");
    await settle();
    expect(sources).toEqual(["connecting", "server", "connecting", "server"]);
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
