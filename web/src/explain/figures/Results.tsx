import { useEffect, useRef, useState } from "react";
import { Bars, Curves, DotStrip, Slope } from "../charts";
import { data } from "../data";
import { FINDINGS, type Finding } from "../findings";
import { Gauge } from "./Gauge";
import { SetupFlow } from "./SetupFlow";

const pct = (v: number) => `${Math.round(v * 100)}%`;
const task = (key: string) => data.tasks.find((t) => t.key === key)!;
const minutes = (m: number) => (m < 1 ? `${Math.round(m * 60)} s` : `${m.toFixed(1)} min`);

/** The setup curves with a slider along the practice, reading both curves where it stands. */
function SetupEvidence() {
  const T = data.calibration.transfer;
  const S = data.calibration.scratch;
  const [i, setI] = useState(0);
  const toSeries = (pts: typeof T) => pts.map((p) => ({ x: p.minutes, y: p.mean, lo: p.ci[0], hi: p.ci[1] }));
  return (
    <>
      <Curves
        series={[
          { label: "Learning also from other patients", points: toSeries(T) },
          { label: "From the patient alone", points: toSeries(S), muted: true },
        ]}
        guess={1 / 3}
        at={T[i].minutes}
        label="Accuracy against minutes of practice, starting from other patients and from scratch"
      />
      <div className="scrub">
        <input
          type="range"
          min={0}
          max={T.length - 1}
          step={1}
          value={i}
          aria-label="Practice trials of each movement"
          onChange={(e) => setI(Number(e.target.value))}
        />
      </div>
      <p className="chart-say" aria-live="polite">
        After {T[i].k} practice trial{T[i].k > 1 ? "s" : ""} of each movement ({minutes(T[i].minutes)}): learning also
        from other patients <b>{pct(T[i].mean)}</b>, from the patient alone <b>{pct(S[i].mean)}</b>.
      </p>
      <SetupFlow />
    </>
  );
}

/** The weeks-later scores, with or without the short re-setup on the new day. */
function LaterEvidence() {
  const L = data.later;
  const [setup, setSetup] = useState(false);
  return (
    <>
      <div className="toggle" role="radiogroup" aria-label="On the new day">
        {[false, true].map((on) => (
          <button key={String(on)} type="button" role="radio" aria-checked={setup === on} onClick={() => setSetup(on)}>
            {on ? "Adjusted with 5 practice trials of each" : "Unchanged"}
          </button>
        ))}
      </div>
      <Bars
        rows={[
          { label: "On the day it was built", value: L.same_session },
          { label: "Two weeks later", value: setup ? L.post.re_setup.mean : L.post.as_is.mean, strong: true },
          { label: "A month later", value: setup ? L.follow.re_setup.mean : L.follow.as_is.mean, strong: true },
        ]}
        guess={1 / 3}
        label="Accuracy of the first session's model on the same day, two weeks later and a month later"
      />
    </>
  );
}

/** The evidence under each answer: every patient where there is one value each. */
function Evidence({ f }: { f: Finding }) {
  if (f.key === "sixth") {
    const rest = task("T3_sf_vs_rest");
    const which = task("T1_ah_vs_sf");
    return (
      <DotStrip
        rows={[
          { label: "Sixth finger or resting?", values: rest.values, mean: rest.mean },
          { label: "Hand or sixth finger?", values: which.values, mean: which.mean },
        ]}
        domain={[0.3, 1]}
        ticks={[0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]}
        marker={{ at: 0.5, text: "guessing" }}
        label="Accuracy of each patient's model on two two-way choices"
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
        names={L.subjects.map((s) => `Patient ${Number(s.replace("sub-", ""))}`)}
        labels={[
          <>
            <b>The published way</b> test trials also used to build the method
          </>,
          <>
            <b>Tested fairly</b> test trials kept apart
          </>,
        ]}
        label="Accuracy of each patient tested the old way and tested fairly"
      />
    );
  }
  if (f.key === "setup") return <SetupEvidence />;
  if (f.key === "later") return <LaterEvidence />;
  const s = data.switch;
  return (
    <dl className="figures-row">
      <div>
        <dt>{pct(s.detection)}</dt>
        <dd>of imagining periods switch it on</dd>
      </div>
      <div>
        <dt>{s.latency_s.toFixed(1)} s</dt>
        <dd>from the start of imagining</dd>
      </div>
      <div>
        <dt>{s.false_per_minute.toFixed(1)}</dt>
        <dd>mistaken switches per minute of rest</dd>
      </div>
    </dl>
  );
}

/** Which answer a #answer-N link asks for, if any. */
const fromHash = () => {
  const m = /^#answer-(\d)$/.exec(window.location.hash);
  const i = m ? FINDINGS.findIndex((f) => f.answers === Number(m[1])) : -1;
  return i >= 0 ? i : null;
};

/** The five answers, one at a time: the dials are the tabs, each showing its score. */
export function ResultsGauges() {
  const [open, setOpen] = useState(() => fromHash() ?? 0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  useEffect(() => {
    const onHash = () => {
      const i = fromHash();
      if (i !== null) setOpen(i);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const f = FINDINGS[open];
  // The address follows the open answer, so a link to it opens it again later.
  const show = (i: number) => {
    setOpen(i);
    window.history.replaceState(null, "", `#answer-${FINDINGS[i].answers}`);
  };
  const go = (i: number) => {
    const n = (i + FINDINGS.length) % FINDINGS.length;
    show(n);
    tabs.current[n]?.focus();
  };
  return (
    <div className="answers">
      <div className="answer-tabs" role="tablist" aria-label="The five answers">
        {FINDINGS.map((g, i) => (
          <button
            key={g.key}
            ref={(el) => {
              tabs.current[i] = el;
            }}
            id={`answer-${g.answers}`}
            type="button"
            role="tab"
            aria-selected={open === i}
            aria-controls="answer-panel"
            tabIndex={open === i ? 0 : -1}
            className="answer-tab"
            onClick={() => show(i)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight") go(i + 1);
              if (e.key === "ArrowLeft") go(i - 1);
            }}
          >
            <Gauge value={g.value} other={g.other?.value} guess={g.guess} />
            <span className="answer-tab-n">Question {g.answers}</span>
            <span className="answer-tab-name">{g.short}</span>
            <span className="answer-tab-value">
              <b>{pct(g.value)}</b> {g.scale}
            </span>
          </button>
        ))}
      </div>
      <section id="answer-panel" className="answer" role="tabpanel" aria-labelledby={`answer-${f.answers}`}>
        <p className="finding-kicker">
          <a href={`#question-${f.answers}`}>Question {f.answers}</a>
        </p>
        <h3 className="finding-q">{f.question}</h3>
        <p className="finding-lead">{f.lead}</p>
        <p className="finding-a">{f.answer}</p>
        <Evidence key={f.key} f={f} />
        <p className="finding-note">{f.note}</p>
        <div className="how">
          <h4>How we found this</h4>
          <p>{f.how}</p>
          <ul>
            {f.see.map((s) => (
              <li key={s.href}>
                <a href={s.href}>{s.text}</a>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}
