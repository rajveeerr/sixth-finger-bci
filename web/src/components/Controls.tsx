import { useEffect } from "react";
import { useDemo } from "../store";
import type { DemoStreamControls } from "../stream/useDemoStream";
import { demoInView, keyForDemo } from "./demoKeys";

const SPEEDS = [1, 2, 4];

const Key = ({ children }: { children: string }) => <kbd className="key">{children}</kbd>;

/** Playback, as quiet text buttons with their keys: Space pauses, the arrows change trial. */
export function Controls({ stream }: { stream: DemoStreamControls }) {
  const { paused, speed, trial, nTrials, source, mode } = useDemo();
  const local = source === "loading-browser" || source === "browser" || source === "replay";

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!keyForDemo(e) || !demoInView()) return;
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
          onClick={() => mode !== "trial" && stream.setMode("trial")}>
          Per trial
        </button>
        <button role="radio" aria-checked={mode === "continuous"} className={mode === "continuous" ? "opt on" : "opt"}
          onClick={() => mode !== "continuous" && stream.setMode("continuous")}>
          Continuous (experimental)
        </button>
      </span>
      {stream.hasServer && (
        <span className="ctl-group" role="radiogroup" aria-label="Where the model runs">
          <button role="radio" aria-checked={!local} className={!local ? "opt on" : "opt"}
            onClick={() => local && stream.retry()}>
            On the server
          </button>
          <button role="radio" aria-checked={local} className={local ? "opt on" : "opt"}
            onClick={() => !local && stream.useBrowser()}>
            In this browser
          </button>
        </span>
      )}
    </nav>
  );
}
