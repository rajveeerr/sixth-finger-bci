import "@fontsource-variable/source-serif-4/opsz.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Plate } from "../components/Plate";
import { ResultsBars, ResultsGauges } from "../explain/figures/Results";
import type { Command } from "../store";
import "../styles.css";
import { IsoHand } from "./IsoHand";
import { ToonHand } from "./ToonHand";

const POSE_NAMES: { command: Command; label: string }[] = [
  { command: "IDLE", label: "Rest" },
  { command: "HAND_GRASP", label: "Affected hand" },
  { command: "SIXTH_FINGER_FLEX", label: "Sixth finger" },
];

/** A page for choosing between design options, side by side. */
function Compare() {
  const [command, setCommand] = useState<Command>("IDLE");
  const [cycle, setCycle] = useState(true);
  useEffect(() => {
    if (!cycle) return;
    const id = setInterval(() => {
      setCommand((c) => POSE_NAMES[(POSE_NAMES.findIndex((p) => p.command === c) + 1) % POSE_NAMES.length].command);
    }, 2200);
    return () => clearInterval(id);
  }, [cycle]);
  return (
    <div className="app compare">
      <header className="masthead">
        <div className="masthead-text">
          <h1>Two ways to draw the hand</h1>
          <p className="lede">The same hand model, posed by the same command. Pick one for the demo.</p>
        </div>
      </header>
      <nav className="controls" aria-label="Pose">
        <div className="segmented" role="radiogroup" aria-label="Command">
          {POSE_NAMES.map((p) => (
            <button key={p.command} role="radio" aria-checked={command === p.command}
              className={command === p.command ? "on" : ""}
              onClick={() => { setCycle(false); setCommand(p.command); }}>
              {p.label}
            </button>
          ))}
        </div>
        <button onClick={() => setCycle((c) => !c)}>{cycle ? "Stop cycling" : "Cycle the poses"}</button>
      </nav>
      <main className="compare-grid">
        <Plate fig={1} title="A. Isometric drawing" hint="Drawn like the bench, fixed view" readout={command} className="plate-option">
          <div className="dotted option-body">
            <IsoHand command={command} />
          </div>
        </Plate>
        <Plate fig={2} title="B. 3D, drawn like the bench" hint="Drag to turn it" readout={command} className="plate-option">
          <div className="dotted option-body">
            <ToonHand command={command} />
          </div>
        </Plate>
      </main>
      <header className="masthead compare-section">
        <div className="masthead-text">
          <h1>Two ways to show the results</h1>
          <p className="lede">The same five findings, with the same plain sentences.</p>
        </div>
      </header>
      <main className="compare-grid">
        <Plate fig={3} title="A. Dial gauges" hint="Drawn like the bench" className="plate-results">
          <ResultsGauges />
        </Plate>
        <Plate fig={4} title="B. Simple bars" hint="Plain and quick to read" className="plate-results">
          <ResultsBars />
        </Plate>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Compare />
  </StrictMode>,
);
