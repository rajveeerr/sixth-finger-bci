import { Bars, Curves, DotStrip, Slope } from "../charts";
import { data } from "../data";
import { FINDINGS, type Finding } from "../findings";
import { Gauge } from "./Gauge";

const pct = (v: number) => `${Math.round(v * 100)}%`;
const task = (key: string) => data.tasks.find((t) => t.key === key)!;

/** The evidence under each answer: every patient where there is one value each. */
function Evidence({ f }: { f: Finding }) {
  if (f.key === "moving" || f.key === "which") {
    const t = task(f.key === "moving" ? "T3_sf_vs_rest" : "T1_ah_vs_sf");
    return (
      <DotStrip
        rows={[{ values: t.values, mean: t.mean }]}
        domain={[0.3, 1]}
        ticks={[0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]}
        marker={{ at: t.chance, text: "guessing" }}
        label={`${f.question} One dot per patient.`}
      />
    );
  }
  if (f.key === "leak") {
    const L = data.leak;
    return (
      <Slope
        a={L.replica}
        b={L.leakfree}
        guess={0.5}
        band={{ from: L.published[0], to: L.published[1], text: "published" }}
        labels={[
          <>
            <b>The published way</b> test trials used in building it
          </>,
          <>
            <b>Tested fairly</b> test trials kept apart
          </>,
        ]}
        label="Accuracy of each patient tested the old way and tested fairly"
      />
    );
  }
  if (f.key === "setup") {
    const toSeries = (pts: typeof data.calibration.transfer) => pts.map((p) => ({ x: p.minutes, y: p.mean, lo: p.ci[0], hi: p.ci[1] }));
    return (
      <Curves
        series={[
          { label: "Starting from other patients", points: toSeries(data.calibration.transfer) },
          { label: "From scratch", points: toSeries(data.calibration.scratch), muted: true },
        ]}
        guess={1 / 3}
        reach={{ minutes: data.calibration.scratch.find((p) => p.mean >= data.calibration.transfer[0].mean - 0.005)?.minutes ?? 4.7, text: "from scratch reaches it here" }}
        label="Accuracy against minutes of practice, starting from other patients and from scratch"
      />
    );
  }
  if (f.key === "later") {
    const L = data.later;
    return (
      <Bars
        rows={[
          { label: "Same day as it was built", value: L.same_session },
          { label: "Two weeks later, as it was", value: L.post.as_is.mean, strong: true },
          { label: "Two weeks later, after 5 practice trials of each movement", value: L.post.re_setup.mean },
        ]}
        guess={1 / 3}
        label="Accuracy of the first session's model on the same day, two weeks later, and after a re-setup"
      />
    );
  }
  const s = data.switch;
  return (
    <dl className="figures-row">
      <div>
        <dt>{pct(s.detection)}</dt>
        <dd>of tries switch it on</dd>
      </div>
      <div>
        <dt>{s.latency_s.toFixed(1)} s</dt>
        <dd>from the start of imagining</dd>
      </div>
      <div>
        <dt>{s.false_per_minute.toFixed(1)}</dt>
        <dd>false switches a minute</dd>
      </div>
    </dl>
  );
}

/** The findings as rows: a dial, the question, the answer, and the evidence under it. */
export function ResultsGauges() {
  return (
    <ol className="findings">
      {FINDINGS.map((f) => (
        <li key={f.key} className="finding">
          <Gauge value={f.value} other={f.other?.value} guess={f.guess} label={`${f.question} ${pct(f.value)}`} />
          <div className="finding-text">
            <p className="finding-kicker">Question {f.answers}</p>
            <h3 className="finding-q">{f.question}</h3>
            <p className="finding-a">
              <em>{f.lead}</em> {f.answer}
            </p>
            <Evidence f={f} />
            <p className="finding-note">{f.note}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
