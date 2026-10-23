import { data, pct } from "../explain/data";
import { SureTerm } from "../explain/refs";
import { IsoHand } from "../hands/IsoHand";
import { shownCommand, useDemo } from "../store";
import type { Prediction } from "../stream/types";

const SOURCE_TEXT: Record<Prediction["source"], string> = {
  server: "Decided on the server",
  browser: "Decided in this browser",
  replay: "Saved earlier by the same model",
};

const MOVEMENT: Record<string, string> = { affected_hand: "the hand", sixth_finger: "the sixth finger" };

const times = (n: number) => (n === 1 ? "once" : `${n} times`);

/** The running score: fixed windows read right per trial, switch-ons in continuous mode. */
function Tally() {
  const { mode, right, total, switches: sw } = useDemo();
  if (mode === "continuous") {
    return (
      <span data-testid="switch-score">
        Moved <b>{times(sw.moved)}</b>, <b>{sw.right}</b> right
        {sw.missed > 0 && <span className="tally-missed">, missed {sw.missed}</span>}
      </span>
    );
  }
  if (!total) return <span>No reading yet</span>;
  return (
    <span>
      <b>
        {right} of {total}
      </b>{" "}
      right so far
    </span>
  );
}

/** Step 3: move or rest from the last 4 s, whether it was right, the guess at which movement, and the hand. */
export function PredictionCard() {
  const { lastPrediction: p, lastReading: r, manualMode } = useDemo();
  const command = useDemo(shownCommand);
  const kind = r ? (r.move ? "move" : "rest") : "";
  const surePct = r ? Math.min(99, Math.round(r.sure * 100)) : 0;
  return (
    <section
      className="step step-read"
      aria-label="What the model reads"
      data-testid="prediction"
      data-label={kind}
    >
      <h3 className="step-title">
        <span className="step-num">3</span> The model reads
      </h3>
      <p className="read-now" data-kind={kind || "none"} aria-live="polite">
        {r ? (r.move ? "Move" : "Rest") : "Waiting for 4 s of signal"}
        {r && r.right !== null && (
          <span className="mark" data-right={String(r.right)}>
            {r.right ? "✓ right" : "✗ wrong"}
          </span>
        )}
      </p>
      <p className="step-note read-about">{r && <SureTerm>{surePct}% sure</SureTerm>}</p>
      <p className="step-note read-guess" data-testid="guess" data-guess={r?.move ? r.guess : ""}>
        {r?.move && (
          <>
            Hand or finger? A guess: <b>{MOVEMENT[r.guess] ?? r.guess}</b>, right {pct(data.demo.hand_finger.acc)} of
            the time; guessing gets 50%.
          </>
        )}
      </p>
      <div className="hand-stage" data-testid="hand" data-command={command}>
        <IsoHand command={command} />
      </div>
      {manualMode && <p className="step-note hand-note">Test pose, not a reading. Press Esc to go back.</p>}
      <p className="step-note tally">
        <Tally />
        {p && `. ${SOURCE_TEXT[p.source]}${p.source !== "replay" ? ` in ${p.latency_ms.toFixed(0)} ms` : ""}.`}
      </p>
    </section>
  );
}
