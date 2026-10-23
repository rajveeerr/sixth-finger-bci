import { useEffect } from "react";
import { useDemo } from "../store";
import type { Mode } from "../stream/types";
import type { DemoStreamControls } from "../stream/useDemoStream";
import { demoInView, keyForDemo } from "./demoKeys";

const SPEEDS = [1, 2, 4];

const MODES: { mode: Mode; name: string; line: string }[] = [
  { mode: "trial", name: "Per trial", line: "The model reads the 4 s after each instruction, as the study tests it." },
  {
    mode: "continuous",
    name: "Continuous",
    line: "It reads every half second without knowing when instructions come, as a real device would.",
  },
];

const Key = ({ children }: { children: string }) => <kbd className="key">{children}</kbd>;

/** Playback, as quiet text buttons with their keys (Space pauses, the arrows change trial), then the two ways of reading. */
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
    <div className="playbar">
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
      <div className="modes" role="radiogroup" aria-label="How the model reads">
        {MODES.map((m) => (
          <button key={m.mode} role="radio" aria-checked={mode === m.mode} className={mode === m.mode ? "mode on" : "mode"}
            onClick={() => mode !== m.mode && stream.setMode(m.mode)}>
            <b>{m.name}</b> {m.line}
          </button>
        ))}
      </div>
    </div>
  );
}
