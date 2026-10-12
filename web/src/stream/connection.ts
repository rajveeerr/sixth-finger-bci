// The WebSocket client of the inference server (/ws/stream), with the timeouts of
// 01-ARCHITECTURE.md §5: no hello within 2 s, or 5 s without any message while the
// stream runs, counts as a failed server. A paused server sends a status heartbeat
// every 2 s, and the watchdog also rests between `pause` and `resume`.

import type { ControlMessage, Mode, ServerMessage } from "./types";

export type CloseReason = "closed" | "error" | "timeout" | "rejected";

export interface StreamHandlers {
  onMessage: (message: ServerMessage) => void;
  /** Called once, when the connection fails or the server ends it (not after close()). */
  onClose: (reason: CloseReason, code?: number) => void;
}

export interface StreamConnection {
  send: (control: ControlMessage) => void;
  close: () => void;
}

export interface ConnectOptions {
  speed?: number;
  helloTimeoutMs?: number;
  watchdogMs?: number;
  socket?: (url: string) => WebSocket;
}

/** The socket URL from the server's own URL, so an https server gets wss. */
export function streamUrl(baseUrl: string, mode: Mode, speed = 1): string {
  const u = new URL("/ws/stream", baseUrl);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.searchParams.set("mode", mode);
  u.searchParams.set("speed", String(speed));
  return u.toString();
}

export function connectServer(
  baseUrl: string,
  mode: Mode,
  handlers: StreamHandlers,
  options: ConnectOptions = {},
): StreamConnection {
  const { speed = 1, helloTimeoutMs = 2000, watchdogMs = 5000 } = options;
  const open = options.socket ?? ((url: string) => new WebSocket(url));
  let ws: WebSocket;
  let finished = false;
  let paused = false;
  let watchdog: ReturnType<typeof setTimeout> | undefined;

  const clearTimers = () => {
    clearTimeout(helloTimer);
    clearTimeout(watchdog);
  };
  const fail = (reason: CloseReason, code?: number) => {
    if (finished) return;
    finished = true;
    clearTimers();
    try {
      ws.close();
    } catch {
      // already closed
    }
    handlers.onClose(reason, code);
  };
  const arm = () => {
    clearTimeout(watchdog);
    if (!paused) watchdog = setTimeout(() => fail("timeout"), watchdogMs);
  };

  try {
    ws = open(streamUrl(baseUrl, mode, speed));
  } catch {
    // An invalid URL or a blocked socket: report it after the caller has the handle.
    setTimeout(() => handlers.onClose("error"), 0);
    return { send: () => {}, close: () => {} };
  }
  const helloTimer = setTimeout(() => fail("timeout"), helloTimeoutMs);

  ws.onmessage = (event: MessageEvent) => {
    if (finished) return;
    let message: ServerMessage;
    try {
      message = JSON.parse(String(event.data));
    } catch {
      return;
    }
    if (message.type === "hello") clearTimeout(helloTimer);
    arm();
    handlers.onMessage(message);
  };
  ws.onerror = () => fail("error");
  ws.onclose = (event: CloseEvent) => {
    if (event.code === 1008 || event.code === 1013) {
      // 1008: this site's origin is not in the server's ALLOWED_ORIGINS; 1013: server full.
      console.warn(`inference server closed the stream with code ${event.code}`);
      fail("rejected", event.code);
    } else {
      fail("closed", event.code);
    }
  };

  return {
    send(control) {
      if (finished) return;
      if (control.type === "pause") {
        paused = true;
        clearTimeout(watchdog);
      } else if (control.type === "resume" || control.type === "jump") {
        paused = false;
        arm();
      }
      ws.send(JSON.stringify(control));
    },
    close() {
      finished = true;
      clearTimers();
      ws.close();
    },
  };
}
