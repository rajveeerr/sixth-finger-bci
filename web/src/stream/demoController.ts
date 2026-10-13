// Runs the source state machine (sourceMachine.ts): connects to the server, falls back
// to the in-browser model on the same bundle, and to the stored predictions if that
// fails, keeping the current trial. Plain TypeScript, so it is tested without a browser.

import { loadBundle as defaultLoadBundle, type LoadedBundle } from "./bundle";
import { connectServer, type StreamConnection } from "./connection";
import { LocalStream, type Predictor, type Timer } from "./localStream";
import { nextSource, type SourceEvent } from "./sourceMachine";
import type { ControlMessage, Mode, ServerMessage, SourceState } from "./types";

export interface ControllerOptions {
  /** Empty for a site without a streaming server: it starts on the in-browser model. */
  serverUrl: string;
  /** A model server answering one window at a time over HTTP (used when there is no streaming server). */
  decodeUrl?: string;
  mode: Mode;
  speed: number;
  base?: string;
  onMessage: (message: ServerMessage) => void;
  onSource: (source: SourceState) => void;
  onError?: (error: string) => void;
  connect?: typeof connectServer;
  loadBundle?: (base: string) => Promise<LoadedBundle>;
  loadDecoder?: (base: string, bundle: LoadedBundle) => Promise<Predictor>;
  loadReplay?: (base: string, bundle: LoadedBundle) => Promise<Predictor>;
  loadRemote?: (url: string, bundle: LoadedBundle) => Promise<Predictor>;
  timer?: Timer;
}

export class DemoController {
  source: SourceState = "connecting";
  private generation = 0;
  private trial = 0;
  private speed: number;
  private paused = false;
  private connection: StreamConnection | null = null;
  private local: LocalStream | null = null;
  private bundle: LoadedBundle | null = null;
  private decoder: Predictor | null = null;
  private remote: Predictor | null = null;
  private running: Predictor | null = null;
  private mode: Mode;
  private readonly base: string;

  constructor(private readonly opts: ControllerOptions) {
    this.base = opts.base ?? "/demo";
    this.speed = opts.speed;
    this.mode = opts.mode;
  }

  private get hasServer() {
    return !!this.opts.serverUrl || !!this.opts.decodeUrl;
  }

  start() {
    if (!this.hasServer) this.source = "loading-browser";
    this.opts.onSource(this.source);
    this.enter(this.source);
  }

  stop() {
    this.generation += 1;
    this.connection?.close();
    this.local?.stop();
    this.connection = null;
    this.local = null;
  }

  /** Switch between per-trial and continuous decoding without leaving the current trial. */
  setMode(mode: Mode) {
    if (mode === this.mode) return;
    this.mode = mode;
    if (this.source === "server" && this.connection) {
      // The streaming server takes the mode when it connects, so connect again; the old
      // connection closes after the new attempt has begun, so its close is ignored.
      const old = this.connection;
      this.connection = null;
      this.source = "connecting";
      this.opts.onSource(this.source);
      this.enter("connecting");
      old.close();
    } else if (this.running) {
      this.runLocal(this.running);
    }
  }

  /** Decode in this browser even though a server is there. */
  useBrowser() {
    this.dispatch("use-browser");
  }

  /** "Try server again". */
  retry() {
    if (this.hasServer) this.dispatch("retry");
  }

  control(message: ControlMessage) {
    if (message.type === "pause") this.paused = true;
    if (message.type === "resume" || message.type === "jump") this.paused = false;
    if (message.type === "speed") this.speed = message.value;
    if (this.source === "server" && this.connection) {
      this.connection.send(message);
      return;
    }
    const local = this.local;
    if (!local) return;
    if (message.type === "pause") local.pause();
    else if (message.type === "resume") local.resume();
    else if (message.type === "speed") local.setSpeed(message.value);
    else if (message.type === "jump") local.jump(message.trial);
  }

  private dispatch(event: SourceEvent) {
    const next = nextSource(this.source, event);
    if (next === this.source) return;
    this.source = next;
    this.opts.onSource(next);
    this.enter(next);
  }

  private forward(message: ServerMessage) {
    if (message.type === "trial_start") this.trial = message.trial;
    this.opts.onMessage(message);
  }

  private enter(state: SourceState) {
    const generation = ++this.generation;
    const current = () => generation === this.generation;
    if (state === "connecting" && !this.opts.serverUrl && this.opts.decodeUrl) {
      const url = this.opts.decodeUrl;
      this.local?.stop();
      this.local = null;
      void (async () => {
        try {
          const bundle = await this.getBundle();
          const remote = await (this.opts.loadRemote ?? defaultLoadRemote)(url, bundle);
          if (!current()) return;
          this.remote = remote;
          this.dispatch("hello");
        } catch (err) {
          console.warn("model server unavailable:", err);
          if (current()) this.dispatch("server-failed");
        }
      })();
    } else if (state === "server" && this.remote && !this.connection) {
      this.runLocal(this.remote);
    } else if (state === "connecting") {
      this.local?.stop();
      this.local = null;
      const connect = this.opts.connect ?? connectServer;
      let conn: StreamConnection | null = null;
      conn = connect(this.opts.serverUrl, this.mode, {
        onMessage: (m) => {
          if (!current() && this.source !== "server") return;
          if (m.type === "hello" && this.source === "connecting") {
            this.dispatch("hello");
            if (this.trial > 0) this.connection?.send({ type: "jump", trial: this.trial });
          }
          this.forward(m);
        },
        onClose: () => {
          // A connection we have already replaced (a new mode) closing is not a failure.
          if (conn && this.connection !== conn) return;
          if (this.source === "connecting" || this.source === "server") this.dispatch("server-failed");
        },
      }, { speed: this.speed });
      this.connection = conn;
    } else if (state === "loading-browser") {
      this.connection?.close();
      this.connection = null;
      this.local?.stop();
      this.local = null;
      void (async () => {
        try {
          const bundle = await this.getBundle();
          const decoder = await (this.opts.loadDecoder ?? defaultLoadDecoder)(this.base, bundle);
          if (!current()) return;
          this.decoder = decoder;
          this.dispatch("browser-ready");
        } catch (err) {
          console.warn("in-browser model unavailable:", err);
          if (current()) this.dispatch("browser-failed");
        }
      })();
    } else if (state === "browser") {
      this.runLocal(this.decoder!);
    } else if (state === "replay") {
      this.local?.stop();
      void (async () => {
        try {
          const bundle = await this.getBundle();
          const replay = await (this.opts.loadReplay ?? defaultLoadReplay)(this.base, bundle);
          if (current()) this.runLocal(replay);
        } catch (err) {
          this.opts.onError?.(`The demo data could not be loaded: ${String(err)}`);
        }
      })();
    }
  }

  private async getBundle(): Promise<LoadedBundle> {
    this.bundle ??= await (this.opts.loadBundle ?? defaultLoadBundle)(this.base);
    return this.bundle;
  }

  private runLocal(predictor: Predictor) {
    const bundle = this.bundle!;
    this.local?.stop();
    this.running = predictor;
    const stream = new LocalStream(bundle, predictor, {
      mode: this.mode,
      speed: this.speed,
      startTrial: this.trial,
      timer: this.opts.timer,
    });
    this.local = stream;
    if (this.paused) stream.paused = true;
    stream
      .run((m) => {
        if (this.local === stream) this.forward(m);
      })
      .catch((err) => {
        if (this.local !== stream) return;
        console.warn("in-browser inference failed:", err);
        if (predictor.source === "server") this.dispatch("server-failed");
        else if (predictor.source === "browser") this.dispatch("browser-failed");
        else this.opts.onError?.(`The replay stopped: ${String(err)}`);
      });
  }
}

async function defaultLoadDecoder(base: string, bundle: LoadedBundle): Promise<Predictor> {
  const { loadBrowserDecoder } = await import("./onnxFallback");
  return loadBrowserDecoder(base, bundle.manifest);
}

async function defaultLoadRemote(url: string, bundle: LoadedBundle): Promise<Predictor> {
  const { loadRemoteDecoder } = await import("./remoteDecoder");
  return loadRemoteDecoder(url, bundle.manifest);
}

async function defaultLoadReplay(base: string, bundle: LoadedBundle): Promise<Predictor> {
  const { loadReplay } = await import("./replay");
  return loadReplay(base, bundle.manifest);
}
