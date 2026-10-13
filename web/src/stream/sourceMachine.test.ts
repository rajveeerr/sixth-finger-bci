import { describe, expect, it } from "vitest";
import { nextSource, type SourceEvent } from "./sourceMachine";
import type { SourceState } from "./types";

const ARROWS: [SourceState, SourceEvent, SourceState][] = [
  ["connecting", "hello", "server"],
  ["connecting", "server-failed", "loading-browser"],
  ["server", "server-failed", "loading-browser"],
  ["connecting", "use-browser", "loading-browser"],
  ["server", "use-browser", "loading-browser"],
  ["loading-browser", "browser-ready", "browser"],
  ["loading-browser", "browser-failed", "replay"],
  ["browser", "browser-failed", "replay"],
  ["browser", "retry", "connecting"],
  ["replay", "retry", "connecting"],
];

describe("nextSource", () => {
  it.each(ARROWS)("%s --%s--> %s", (from, event, to) => {
    expect(nextSource(from, event)).toBe(to);
  });

  it("reaches replay only after the browser model fails", () => {
    const states: SourceState[] = ["connecting", "server", "loading-browser", "browser", "replay"];
    const events: SourceEvent[] = ["hello", "server-failed", "browser-ready", "browser-failed", "retry"];
    for (const s of states) {
      for (const e of events) {
        if (nextSource(s, e) === "replay" && s !== "replay") expect(e).toBe("browser-failed");
      }
    }
  });

  it("ignores events that do not apply", () => {
    expect(nextSource("server", "hello")).toBe("server");
    expect(nextSource("connecting", "browser-ready")).toBe("connecting");
  });
});
