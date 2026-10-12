import { useDemo } from "../store";
import type { DemoStreamControls } from "../stream/useDemoStream";

const SPEEDS = [1, 2, 4];

function setMode(mode: "trial" | "continuous") {
  const url = new URL(window.location.href);
  if (mode === "trial") url.searchParams.delete("mode");
  else url.searchParams.set("mode", mode);
  window.location.assign(url.toString());
}

export function Controls({ stream }: { stream: DemoStreamControls }) {
  const { paused, speed, trial, nTrials, source, mode } = useDemo();
  const local = source === "browser" || source === "replay";
  return (
    <nav className="controls" aria-label="Playback">
      <button className="primary" onClick={() => stream.control({ type: paused ? "resume" : "pause" })}>
        {paused ? "Resume" : "Pause"}
      </button>
      <div className="segmented" role="radiogroup" aria-label="Speed">
        {SPEEDS.map((s) => (
          <button key={s} role="radio" aria-checked={speed === s} className={speed === s ? "on" : ""}
            onClick={() => stream.control({ type: "speed", value: s })}>
            {s}×
          </button>
        ))}
      </div>
      <button disabled={!nTrials} onClick={() => stream.control({ type: "jump", trial: trial - 1 })}>
        Previous trial
      </button>
      <button disabled={!nTrials} onClick={() => stream.control({ type: "jump", trial: trial + 1 })}>
        Next trial
      </button>
      <div className="segmented" role="radiogroup" aria-label="Decoding">
        <button role="radio" aria-checked={mode === "trial"} className={mode === "trial" ? "on" : ""}
          onClick={() => mode !== "trial" && setMode("trial")}>
          Per trial
        </button>
        <button role="radio" aria-checked={mode === "continuous"} className={mode === "continuous" ? "on" : ""}
          onClick={() => mode !== "continuous" && setMode("continuous")}>
          Continuous (experimental)
        </button>
      </div>
      {local && (
        <button className="quiet" onClick={stream.retry}>
          Try the server again
        </button>
      )}
    </nav>
  );
}
