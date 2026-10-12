import { anyImagery, useDemo, type View } from "../store";
import type { ClassInfo, Prediction } from "../stream/types";

const SOURCE_TEXT: Record<Prediction["source"], string> = {
  server: "on the server",
  browser: "in this browser",
  replay: "stored offline by the same model",
};

function labelOf(classes: ClassInfo[], name: string | null) {
  return classes.find((c) => c.name === name)?.label ?? name ?? "";
}

/** The decision of the last window, in the chosen view, against the cue the patient saw. */
export function PredictionCard() {
  const { lastPrediction: p, classes, view, correct, total, switchCorrect, switchTotal, setView } = useDemo();
  const rest = classes[0]?.name;
  const imagined = p ? anyImagery(p) : false;
  const decided = !p ? null : view === "three" ? p.label : imagined ? "imagery" : rest;
  const headline = !p
    ? "Waiting for the first decision"
    : view === "three"
      ? labelOf(classes, p.label)
      : imagined
        ? "Movement imagined"
        : "Rest";
  const right = !p || p.truth === null ? null : view === "three" ? p.correct : imagined === (p.truth !== rest);
  const probs = p ? (p.smoothed ?? p.probs) : [];
  const bars =
    view === "three"
      ? classes.map((c, i) => ({ key: c.name, label: c.label, value: probs[i] ?? 0 }))
      : [
          { key: "rest", label: "Rest", value: probs[0] ?? 0 },
          { key: "imagery", label: "Any imagery", value: (probs[1] ?? 0) + (probs[2] ?? 0) },
        ];
  return (
    <section className="readout" data-testid="prediction" data-label={decided ?? ""} data-view={view}>
      <div className="view-switch" role="radiogroup" aria-label="How the decoder is used">
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
      <p className="view-note">
        {view === "three"
          ? "Rest, affected hand or sixth finger: the commands the decoder was trained on."
          : "Any imagined movement flexes the sixth finger: the use this study's results support."}
      </p>
      <p className="decision" data-kind={decided ?? "none"} aria-live="polite">
        {headline}
      </p>
      <dl className="bars">
        {bars.map((b) => (
          <div key={b.key} className="bar" data-kind={b.key}>
            <dt>{b.label}</dt>
            <dd>
              <span className="track">
                <span className="fill" style={{ width: `${Math.round(b.value * 100)}%` }} />
              </span>
              <span className="pct">{Math.round(b.value * 100)}%</span>
            </dd>
          </div>
        ))}
      </dl>
      {p && (
        <p className="cue" data-correct={right === null ? "" : String(right)}>
          Cue: {labelOf(classes, p.truth)}
          {right !== null && <span className="mark">{right ? " ✓ right" : " ✗ wrong"}</span>}
          <span className="window">
            {p.window === "rest" ? "rest window" : p.window === "imagery" ? "imagery window" : "sliding window"}
          </span>
        </p>
      )}
      <p className="tally">
        {view === "three"
          ? total
            ? `${correct} of ${total} imagery cues decoded right`
            : "No imagery cue decoded yet"
          : switchTotal
            ? `${switchCorrect} of ${switchTotal} windows right, rest and imagery`
            : "No window decoded yet"}
      </p>
      {p && (
        <p className="provenance">
          Decided {SOURCE_TEXT[p.source]}
          {p.source !== "replay" && ` in ${p.latency_ms.toFixed(1)} ms`}
          {p.experimental && ", continuous mode (experimental)"}
        </p>
      )}
    </section>
  );
}
