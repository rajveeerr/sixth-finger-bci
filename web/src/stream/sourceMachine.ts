// Where predictions come from (01-ARCHITECTURE.md §5), as a pure reducer:
// connecting → server; a failed server → loading the in-browser model → browser;
// the browser model failing → replay of the stored predictions. "Try server again"
// starts over from connecting.

import type { SourceState } from "./types";

export type SourceEvent = "hello" | "server-failed" | "browser-ready" | "browser-failed" | "retry";

export function nextSource(state: SourceState, event: SourceEvent): SourceState {
  switch (state) {
    case "connecting":
      if (event === "hello") return "server";
      if (event === "server-failed") return "loading-browser";
      return state;
    case "server":
      return event === "server-failed" ? "loading-browser" : state;
    case "loading-browser":
      if (event === "browser-ready") return "browser";
      if (event === "browser-failed") return "replay";
      return state;
    case "browser":
      if (event === "retry") return "connecting";
      if (event === "browser-failed") return "replay";
      return state;
    case "replay":
      return event === "retry" ? "connecting" : state;
  }
}
