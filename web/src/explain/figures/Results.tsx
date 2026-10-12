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

/** The findings as plain bars, with a mark where guessing would land. */
export function ResultsBars() {
  return (
    <div className="result-bars">
      {FINDINGS.map((f) => (
        <figure key={f.key} className="finding-row">
          <figcaption className="finding-q">{f.question}</figcaption>
          <div className="rbar">
            <span className="rbar-track">
              <span className="rbar-fill" style={{ width: pct(f.value) }} />
              {f.guess !== undefined && f.guess > 0 && (
                <span className="rbar-guess" style={{ left: pct(f.guess) }}>
                  <i>guessing</i>
                </span>
              )}
            </span>
            <b>{pct(f.value)}</b>
          </div>
          {f.other && (
            <div className="rbar rbar-other">
              <span className="rbar-track">
                <span className="rbar-fill" style={{ width: pct(f.other.value) }} />
              </span>
              <span>
                {pct(f.other.value)} {f.other.label}
              </span>
            </div>
          )}
          <p className="finding-a">{f.answer}</p>
        </figure>
      ))}
    </div>
  );
}
