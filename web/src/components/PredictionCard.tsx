import { data, pct } from "../explain/data";
import { SureTerm } from "../explain/refs";
import { IsoHand } from "../hands/IsoHand";
import { shownCommand, useDemo } from "../store";
import type { Prediction } from "../stream/types";

const SOURCE_TEXT: Record<Prediction["source"], string> = {
  server: "Decided on the server",
  browser: "Decided in this browser",
  replay: "Worked out earlier by the same model and saved",
};

const MOVEMENT: Record<string, string> = { affected_hand: "the hand", sixth_finger: "the sixth finger" };

/** Step 3: move or rest from the last 4 s, whether it was right, the guess at which movement, and the hand. */
export function PredictionCard() {
  const { lastPrediction: p, lastReading: r, classes, mode, right, total, manualMode } = useDemo();
  const command = useDemo(shownCommand);
  const kind = r ? (r.move ? "move" : "rest") : "";
  const surePct = r ? Math.min(99, Math.round(r.sure * 100)) : 0;
  const asked = !p
    ? ""
    : p.truth === classes[0]?.name
      ? "resting"
      : `asked to imagine ${MOVEMENT[p.truth ?? ""] ?? "a movement"}`;
  const tally =
    mode === "continuous"
      ? "A reading every half second, not counted in the score"
      : total
        ? `${right} of ${total} read right so far, rest as Rest and hand or finger as Move`
        : "No reading yet";
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
      <p className="step-note read-about">
        {p ? (
          <>
            From the last 4 s, while the patient was <b>{asked}</b>. <SureTerm>{surePct}% sure</SureTerm>.
          </>
        ) : (
          "The first reading comes 5 s into the trial."
        )}
      </p>
      <p className="step-note read-guess" data-testid="guess" data-guess={r?.move ? r.guess : ""}>
        {r?.move ? (
          <>
            Which movement? A guess: <b>{MOVEMENT[r.guess] ?? r.guess}</b>. Right{" "}
            {pct(data.demo.hand_finger.acc)} of the time for this patient; guessing gets 50%.
          </>
        ) : (
          "Which movement? Guessed only on Move."
        )}
      </p>
      <div className="hand-stage" data-testid="hand" data-command={command}>
        <IsoHand command={command} />
      </div>
      <p className="step-note hand-note">
        {manualMode
          ? "Test pose, not a reading. Press Esc to go back."
          : "The robotic finger bends on Move, whichever movement was imagined."}
      </p>
      <p className="step-note tally">
        {tally}
        {p && `. ${SOURCE_TEXT[p.source]}${p.source !== "replay" ? ` in ${p.latency_ms.toFixed(0)} ms` : ""}.`}
      </p>
    </section>
  );
}
