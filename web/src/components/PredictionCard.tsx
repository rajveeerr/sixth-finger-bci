import { decidedKind, isRight } from "../decision";
import { IsoHand } from "../hands/IsoHand";
import { shownCommand, useDemo } from "../store";
import type { Prediction } from "../stream/types";

const SOURCE_TEXT: Record<Prediction["source"], string> = {
  server: "Decided on the server",
  browser: "Decided in this browser",
  replay: "Stored by the same model",
};

/** What each reading is called on screen, in plain words. */
const SAY: Record<string, string> = {
  rest: "Rest",
  affected_hand: "Hand",
  sixth_finger: "Sixth finger",
  imagery: "Move",
};

/** Step 3: the model's reading of the last 4 s, whether it was right, and the hand moving. */
export function PredictionCard() {
  const { lastPrediction: p, classes, view, correct, total, switchCorrect, switchTotal, manualMode } = useDemo();
  const command = useDemo(shownCommand);
  const decided = p ? decidedKind(p, view, classes) : null;
  const right = p ? isRight(p, view, classes) : null;
  const probs = p ? (p.smoothed ?? p.probs) : [];
  const sure = !p ? 0 : view === "three" ? Math.max(...probs) : Math.max(probs[0] ?? 0, (probs[1] ?? 0) + (probs[2] ?? 0));
  const surePct = Math.min(99, Math.round(sure * 100));
  const asked = !p ? "" : p.truth === classes[0]?.name ? "resting" : `asked to imagine ${p.truth === "sixth_finger" ? "the sixth finger" : "the hand"}`;
  const tally =
    view === "three"
      ? total
        ? `${correct} of ${total} imagined movements read right so far`
        : "No imagined movement read yet"
      : switchTotal
        ? `${switchCorrect} of ${switchTotal} windows right, rest and imagery`
        : "No reading yet";
  return (
    <section className="step step-read" aria-label="What the model reads" data-testid="prediction" data-label={decided ?? ""} data-view={view}>
      <h2 className="step-title">
        <span className="step-num">3</span> The model reads
      </h2>
      <p className="read-now" data-kind={decided ?? "none"} aria-live="polite">
        {p ? (SAY[decided ?? ""] ?? decided) : "Waiting for 4 s of signal"}
        {right !== null && (
          <span className="mark" data-right={String(right)}>
            {right ? "✓ right" : "✗ wrong"}
          </span>
        )}
      </p>
      <p className="step-note read-about">
        {p ? (
          <>
            From the last 4 s, while the patient was <b>{asked}</b>. {surePct}% sure.
          </>
        ) : (
          "The first reading comes 5 s into the trial."
        )}
      </p>
      <div className="hand-stage" data-testid="hand" data-command={command}>
        <IsoHand command={command} />
      </div>
      <p className="step-note hand-note">
        {manualMode
          ? "Test pose, not a reading. Press Esc to go back."
          : view === "three"
            ? "The robotic finger bends when the model reads sixth finger."
            : "The robotic finger bends for any imagined movement."}
      </p>
      <p className="step-note tally">
        {tally}
        {p && `. ${SOURCE_TEXT[p.source]}${p.source !== "replay" ? ` in ${p.latency_ms.toFixed(0)} ms` : ""}.`}
      </p>
    </section>
  );
}
