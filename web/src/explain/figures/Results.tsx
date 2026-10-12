import { FINDINGS } from "../findings";
import { Gauge } from "./Gauge";

const pct = (v: number) => `${Math.round(v * 100)}%`;

/** The findings as dial gauges: the needle is our score, the hatched arc is guessing. */
export function ResultsGauges() {
  return (
    <div className="gauges">
      {FINDINGS.map((f) => (
        <figure key={f.key} className="finding">
          <figcaption className="finding-q">{f.question}</figcaption>
          <Gauge value={f.value} other={f.other?.value} guess={f.guess} label={`${f.question} ${pct(f.value)}`} />
          <p className="finding-value">
            <b>{pct(f.value)}</b> {f.valueLabel}
            {f.other && (
              <span className="finding-other">
                {" "}
                against {pct(f.other.value)} {f.other.label}
              </span>
            )}
          </p>
          <p className="finding-a">{f.answer}</p>
        </figure>
      ))}
      <p className="gauge-key">
        <span className="key-needle" /> our score <span className="key-ghost" /> the score it is compared with{" "}
        <span className="key-guess" /> what guessing gets
      </p>
    </div>
  );
}
