import { decidedKind, isRight } from "../decision";
import { RECENT, useDemo, type View } from "../store";
import type { Prediction } from "../stream/types";
import { Lamp } from "./Lamp";
import { Panel } from "./Panel";

const SOURCE_TEXT: Record<Prediction["source"], string> = {
  server: "Decided on the server",
  browser: "Decided in this browser",
  replay: "Stored by the same model",
};

/** What each class is called on screen, in plain words. */
const SAY: Record<string, string> = {
  rest: "Rest",
  affected_hand: "Hand",
  sixth_finger: "Sixth finger",
  imagery: "Move",
};
const TOLD: Record<string, string> = {
  rest: "Rest",
  affected_hand: "Imagine moving the hand",
  sixth_finger: "Imagine moving the sixth finger",
};

/** Step 3: the model's decision on the last 4 s, against what the patient was told. */
export function PredictionCard() {
  const { lastPrediction: p, recent, classes, view, correct, total, switchCorrect, switchTotal, setView } = useDemo();
  const decided = p ? decidedKind(p, view, classes) : null;
  const right = p ? isRight(p, view, classes) : null;
  const probs = p ? (p.smoothed ?? p.probs) : [];
  const lamps =
    view === "three"
      ? classes.map((c, i) => ({ key: c.name, value: probs[i] ?? 0 }))
      : [
          { key: classes[0]?.name ?? "rest", value: probs[0] ?? 0 },
          { key: "imagery", value: (probs[1] ?? 0) + (probs[2] ?? 0) },
        ];
  const tally =
    view === "three"
      ? total
        ? `${correct} of ${total} imagined movements read right`
        : "No imagined movement yet"
      : switchTotal
        ? `${switchCorrect} of ${switchTotal} windows right, rest and imagery`
        : "No decision yet";
  return (
    <Panel
      step={3}
      title="What the model decided"
      note="every 4 s"
      className="panel-decision"
      testId="prediction"
      data={{ "data-label": decided ?? "", "data-view": view }}
      foot={
        <>
          <span>
            {p ? SOURCE_TEXT[p.source] : ""}
            {p && p.source !== "replay" ? `, ${p.latency_ms.toFixed(0)} ms` : ""}
          </span>
          <span className="segmented" role="radiogroup" aria-label="How the decision is used">
            {(["three", "switch"] as View[]).map((v) => (
              <button key={v} role="radio" aria-checked={view === v} className={view === v ? "on" : ""}
                onClick={() => setView(v)}>
                {v === "three" ? "Three choices" : "On/off switch"}
              </button>
            ))}
          </span>
        </>
      }
    >
      <dl className="verdict">
        <div className="verdict-row">
          <dt>The patient was told</dt>
          <dd className="told" data-kind={p?.truth ?? ""}>
            {p ? (TOLD[p.truth ?? ""] ?? "") : "…"}
          </dd>
        </div>
        <div className="verdict-row">
          <dt>The model read</dt>
          <dd className="decision" data-kind={decided ?? "none"} aria-live="polite">
            {p ? (SAY[decided ?? ""] ?? decided) : "Waiting for the first 4 s"}
            {right !== null && (
              <span className="mark" data-right={String(right)}>
                {right ? "✓ right" : "✗ wrong"}
              </span>
            )}
          </dd>
        </div>
      </dl>
      <ol className="lamps" aria-label="How sure the model is of each choice">
        {lamps.map((l) => (
          <li key={l.key} data-kind={l.key} data-on={l.key === decided ? "" : undefined}>
            <Lamp kind={l.key} on={l.key === decided} />
            <span className="lamp-name">{SAY[l.key] ?? l.key}</span>
            <span className="lamp-pct">{Math.round(l.value * 100)}%</span>
          </li>
        ))}
      </ol>
      <div className="recent">
        <ol aria-label="The last decisions, oldest first">
          {Array.from({ length: RECENT }, (_, i) => {
            const d = recent[recent.length - RECENT + i];
            if (!d) return <li key={i} className="empty" />;
            const r = isRight(d, view, classes);
            const k = decidedKind(d, view, classes);
            return <li key={i} data-kind={k} data-right={String(r)} title={`${SAY[k] ?? k}, ${r ? "right" : "wrong"}`} />;
          })}
        </ol>
        <span className="tally">{tally}</span>
      </div>
    </Panel>
  );
}
