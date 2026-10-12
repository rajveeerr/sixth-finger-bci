import { FINDINGS } from "../findings";
import { Gauge } from "./Gauge";

const pct = (v: number) => `${Math.round(v * 100)}%`;

/** The findings as rows: a dial gauge, the question, our score against guessing, the answer. */
export function ResultsGauges() {
  return (
    <ol className="findings">
      {FINDINGS.map((f) => (
        <li key={f.key} className="finding">
          <Gauge value={f.value} other={f.other?.value} guess={f.guess} label={`${f.question} ${pct(f.value)}`} />
          <div className="finding-text">
            <h3 className="finding-q">{f.question}</h3>
            <p className="finding-value">
              {pct(f.value)} {f.valueLabel}
              {f.other && `, against ${pct(f.other.value)} ${f.other.label}`}
              {f.guess !== undefined && `. Guessing gets ${pct(f.guess)}`}
            </p>
            <p className="finding-a">
              <em>{f.lead}</em> {f.answer}
            </p>
          </div>
        </li>
      ))}
      <li className="finding-key" aria-hidden="true">
        <span className="key-needle" /> our score <span className="key-ghost" /> the score it is compared with{" "}
        <span className="key-guess" /> what guessing gets
      </li>
    </ol>
  );
}
