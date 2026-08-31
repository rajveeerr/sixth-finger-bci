import type { ControlMessage, Mode, ServerMessage } from "./types";

export interface StreamHandlers {
  onMessage: (message: ServerMessage) => void;
  onClose: (reason: "closed" | "error" | "timeout") => void;
}

export interface StreamConnection {
  send: (control: ControlMessage) => void;
  close: () => void;
}

/** Open /ws/stream; reports "timeout" if no hello arrives within `helloTimeoutMs`. */
export function connectServer(
  _baseUrl: string,
  _mode: Mode,
  _handlers: StreamHandlers,
  _helloTimeoutMs = 2000,
): StreamConnection {
  throw new Error("connectServer is not implemented yet");
}
