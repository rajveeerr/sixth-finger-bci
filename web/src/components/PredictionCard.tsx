import { decidedKind, isRight, labelOf } from "../decision";
import { RECENT, useDemo, type View } from "../store";
import type { Prediction } from "../stream/types";
import { Plate } from "./Plate";

const SOURCE_TEXT: Record<Prediction["source"], string> = {
  server: "Decided on the server",
  browser: "Decided in this browser",
  replay: "Stored by the same model",
};

const VIEW_NOTE: Record<View, string> = {
  three: "The three commands it was trained on.",
  switch: "Any imagined movement flexes the finger: the use our results support.",
};

/** Fig. 3: the decision of the last window, in the chosen view, against the cue the patient saw. */
export function PredictionCard() {
  const { lastPrediction: p, recent, classes, view, correct, total, switchCorrect, switchTotal, setView } = useDemo();
  const decided = p ? decidedKind(p, view, classes) : null;
  const right = p ? isRight(p, view, classes) : null;
  const probs = p ? (p.smoothed ?? p.probs) : [];
  const bars =
    view === "three"
      ? classes.map((c, i) => ({ key: c.name, label: c.label, value: probs[i] ?? 0 }))
      : [
          { key: classes[0]?.name ?? "rest", label: "Rest", value: probs[0] ?? 0 },
          { key: "imagery", label: "Any imagery", value: (probs[1] ?? 0) + (probs[2] ?? 0) },
        ];
  const tally =
    view === "three"
      ? total
        ? `${correct} of ${total} imagery cues right`
        : "No imagery cue yet"
      : switchTotal
        ? `${switchCorrect} of ${switchTotal} windows right, rest and imagery`
        : "No window yet";
  const provenance = p ? `${SOURCE_TEXT[p.source]}${p.experimental ? ", continuous" : ""}` : "";
  const latency = p && p.source !== "replay" ? `${p.latency_ms.toFixed(1)} ms` : "";
  return (
    <Plate
      fig={3}
      title="What the decoder read"
      hint={provenance}
      readout={latency}
      className="plate-decision"
      testId="prediction"
      data={{ "data-label": decided ?? "", "data-view": view }}
    >
      <section className="readout">
        <div className="readout-group">
          <div className="segmented" role="radiogroup" aria-label="How the decoder is used">
            {(["three", "switch"] as View[]).map((v) => (
              <button
                key={v}
                role="radio"
                aria-checked={view === v}
                className={view === v ? "on" : ""}
                onClick={() => setView(v)}
              >
                {v === "three" ? "Three commands" : "One switch"}
              </button>
            ))}
          </div>
          <p className="view-note">{VIEW_NOTE[view]}</p>
        </div>
        <div className="readout-group">
          <p className="decision" data-kind={decided ?? "none"} aria-live="polite">
            {p ? labelOf(classes, decided) : "Waiting for the first 4 s window"}
          </p>
          <dl className="bars">
            {bars.map((b) => (
              <div key={b.key} className="bar" data-kind={b.key} data-top={b.key === decided ? "" : undefined}>
                <dt>{b.label}</dt>
                <dd>
                  <span className="track">
                    <span className="fill" style={{ transform: `scaleX(${b.value})` }} />
                  </span>
                  <span className="pct">{Math.round(b.value * 100)}%</span>
                </dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="readout-group">
          {p && (
            <p className="cue" data-correct={right === null ? "" : String(right)}>
              <span className="cue-told">
                Asked to {p.truth === classes[0]?.name ? "rest" : `imagine ${labelOf(classes, p.truth).toLowerCase()}`}
              </span>
              {right !== null && <span className="mark">{right ? "✓ right" : "✗ wrong"}</span>}
            </p>
          )}
          <div className="recent">
            <ol aria-label="The last decisions, oldest first">
              {Array.from({ length: RECENT }, (_, i) => {
                const d = recent[recent.length - RECENT + i];
                if (!d) return <li key={i} className="empty" />;
                const r = isRight(d, view, classes);
                return (
                  <li key={i} data-kind={decidedKind(d, view, classes)} data-right={String(r)}
                    title={`${labelOf(classes, decidedKind(d, view, classes))}, ${r ? "right" : "wrong"}`} />
                );
              })}
            </ol>
            <span className="tally">{tally}</span>
          </div>
        </div>
      </section>
    </Plate>
  );
}
