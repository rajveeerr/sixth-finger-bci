import { useEffect } from "react";
import { useDemo } from "../store";
import type { DemoStreamControls } from "../stream/useDemoStream";

const SPEEDS = [1, 2, 4];

function setMode(mode: "trial" | "continuous") {
  const url = new URL(window.location.href);
  if (mode === "trial") url.searchParams.delete("mode");
  else url.searchParams.set("mode", mode);
  window.location.assign(url.toString());
}

const Key = ({ children }: { children: string }) => <kbd className="key">{children}</kbd>;

/** Playback, as quiet text buttons with their keys: Space pauses, the arrows change trial. */
export function Controls({ stream }: { stream: DemoStreamControls }) {
  const { paused, speed, trial, nTrials, source, mode } = useDemo();
  const local = source === "browser" || source === "replay";

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.target instanceof HTMLInputElement) return;
      const s = useDemo.getState();
      if (e.key === " " && !(e.target instanceof HTMLButtonElement)) {
        e.preventDefault();
        stream.control({ type: s.paused ? "resume" : "pause" });
      } else if (e.key === "ArrowLeft" && s.nTrials) {
        stream.control({ type: "jump", trial: s.trial - 1 });
      } else if (e.key === "ArrowRight" && s.nTrials) {
        stream.control({ type: "jump", trial: s.trial + 1 });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stream]);

  return (
    <nav className="controls" aria-label="Playback">
      <button className="ctl" onClick={() => stream.control({ type: paused ? "resume" : "pause" })}>
        <Key>Space</Key> {paused ? "Resume" : "Pause"}
      </button>
      <button className="ctl" disabled={!nTrials} onClick={() => stream.control({ type: "jump", trial: trial - 1 })}>
        <Key>←</Key> Previous trial
      </button>
      <button className="ctl" disabled={!nTrials} onClick={() => stream.control({ type: "jump", trial: trial + 1 })}>
        <Key>→</Key> Next trial
      </button>
      <span className="ctl-group" role="radiogroup" aria-label="Speed">
        {SPEEDS.map((s) => (
          <button key={s} role="radio" aria-checked={speed === s} className={speed === s ? "opt on" : "opt"}
            onClick={() => stream.control({ type: "speed", value: s })}>
            {s}×
          </button>
        ))}
      </span>
      <span className="ctl-group" role="radiogroup" aria-label="Decoding">
        <button role="radio" aria-checked={mode === "trial"} className={mode === "trial" ? "opt on" : "opt"}
          onClick={() => mode !== "trial" && setMode("trial")}>
          Per trial
        </button>
        <button role="radio" aria-checked={mode === "continuous"} className={mode === "continuous" ? "opt on" : "opt"}
          onClick={() => mode !== "continuous" && setMode("continuous")}>
          Continuous (experimental)
        </button>
      </span>
      <span className="ctl-hint">
        <Key>1</Key> <Key>2</Key> <Key>3</Key> test the hand
      </span>
      {local && (
        <button className="ctl ctl-quiet" onClick={stream.retry}>
          Try the server again
        </button>
      )}
    </nav>
  );
}
