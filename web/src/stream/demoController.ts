// Runs the source state machine (sourceMachine.ts): connects to the server, falls back
// to the in-browser model on the same bundle, and to the stored predictions if that
// fails, keeping the current trial. Plain TypeScript, so it is tested without a browser.

import { loadBundle as defaultLoadBundle, type LoadedBundle } from "./bundle";
import { connectServer, type StreamConnection } from "./connection";
import { LocalStream, type Predictor, type Timer } from "./localStream";
import { nextSource, type SourceEvent } from "./sourceMachine";
import type { ControlMessage, Mode, ServerMessage, SourceState } from "./types";

export interface ControllerOptions {
  /** Empty for a site without a server: it starts on the in-browser model. */
  serverUrl: string;
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
  private readonly base: string;

  constructor(private readonly opts: ControllerOptions) {
    this.base = opts.base ?? "/demo";
    this.speed = opts.speed;
  }

  start() {
    if (!this.opts.serverUrl) this.source = "loading-browser";
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

  /** "Try server again". */
  retry() {
    if (this.opts.serverUrl) this.dispatch("retry");
  }

  control(message: ControlMessage) {
    if (message.type === "pause") this.paused = true;
    if (message.type === "resume" || message.type === "jump") this.paused = false;
    if (message.type === "speed") this.speed = message.value;
    if (this.source === "server") {
      this.connection?.send(message);
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
    if (state === "connecting") {
      this.local?.stop();
      this.local = null;
      const connect = this.opts.connect ?? connectServer;
      this.connection = connect(this.opts.serverUrl, this.opts.mode, {
        onMessage: (m) => {
          if (!current() && this.source !== "server") return;
          if (m.type === "hello" && this.source === "connecting") {
            this.dispatch("hello");
            if (this.trial > 0) this.connection?.send({ type: "jump", trial: this.trial });
          }
          this.forward(m);
        },
        onClose: () => {
          if (this.source === "connecting" || this.source === "server") this.dispatch("server-failed");
        },
      }, { speed: this.speed });
    } else if (state === "loading-browser") {
      this.connection?.close();
      this.connection = null;
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
    const stream = new LocalStream(bundle, predictor, {
      mode: this.opts.mode,
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
        if (predictor.source === "browser") this.dispatch("browser-failed");
        else this.opts.onError?.(`The replay stopped: ${String(err)}`);
      });
  }
}

async function defaultLoadDecoder(base: string, bundle: LoadedBundle): Promise<Predictor> {
  const { loadBrowserDecoder } = await import("./onnxFallback");
  return loadBrowserDecoder(base, bundle.manifest);
}

async function defaultLoadReplay(base: string, bundle: LoadedBundle): Promise<Predictor> {
  const { loadReplay } = await import("./replay");
  return loadReplay(base, bundle.manifest);
}
