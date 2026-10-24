import { useState } from "react";
import { Bars, Coverage, COVERAGE_INSET, Curves, DotStrip, Slope } from "../charts";
import { data, pct } from "../data";
import { pctFine } from "../findings";
import { StripTerm } from "../refs";
import { coverageAt, plain, sayCoverage, type Said } from "../sure";

// The charts behind the answers, each placed in the chapter whose question it answers.

const minutes = (m: number) => (m < 1 ? `${Math.round(m * 60)} s` : `${m.toFixed(1)} min`);

const Say = ({ said }: { said: Said }) => <>{said.map((s, i) => (typeof s === "string" ? s : <b key={i}>{s.b}</b>))}</>;

/**
 * Each patient scored the published way and leakage-free with a standard CSP+LDA, one line
 * between the two. The published score is not drawn beside it: it came from another recipe.
 */
export function LeakSlope() {
  const L = data.leak;
  return (
    <Slope
      a={L.replica}
      b={L.leakfree}
      guess={0.5}
      names={L.subjects.map((s) => `Patient ${Number(s.replace("sub-", ""))}`)}
      labels={[
        <>
          <b>The published way</b> test trials also used to build the method
        </>,
        <>
          <b>Leakage-free</b> test trials kept apart
        </>,
      ]}
      label="Accuracy of each patient tested the paper's way and leakage-free"
    />
  );
}

/** Each patient on the two two-way choices: sixth finger or rest, and hand or sixth finger. */
export function EachPatient() {
  const S = data.sixth;
  return (
    <figure className="figure">
      <DotStrip
        rows={[
          { label: "Sixth finger or resting?", values: S.rest.values, mean: S.rest.mean },
          { label: "Hand or sixth finger?", values: S.which.values, mean: S.which.mean },
        ]}
        domain={[0.3, 1]}
        ticks={[0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]}
        marker={{ at: 0.5, text: "guessing" }}
        label="Accuracy of each patient's model on two two-way choices"
      />
      <figcaption className="figure-note">
        One dot per patient; point at or tap one for its score. Sixth finger or resting: a simple model reading{" "}
        <StripTerm />. Hand or sixth finger: the best of the models we tried on these runs, so a little optimistic, a
        network that first learned from the other patients.
      </figcaption>
    </figure>
  );
}

/** The switch acting only on its surest decisions, with a slider over how many it takes. */
export function WhenSure() {
  const S = data.sixth;
  const C = S.coverage;
  const [i, setI] = useState(C.length - 1);
  const at = coverageAt(C, i);
  return (
    <>
      <Coverage
        points={C}
        at={i}
        onPick={setI}
        mark={{ share: S.sure.share, acc: S.sure.acc, text: "each patient's own threshold" }}
        label="Accuracy of the sixth-finger switch on its surest decisions, against the share of decisions it takes"
      />
      {/* The thumb (18 px wide) is centred over each point of the chart above. */}
      <div className="scrub" style={{ padding: `0 ${COVERAGE_INSET.right - 9}px 0 ${COVERAGE_INSET.left - 9}px` }}>
        <input
          type="range"
          min={0}
          max={C.length - 1}
          step={1}
          value={i}
          aria-label="Share of decisions the switch takes"
          aria-valuetext={plain(sayCoverage(at))}
          onChange={(e) => setI(Number(e.target.value))}
        />
      </div>
      <p className="chart-say" aria-live="polite">
        <Say said={sayCoverage(at)} />
      </p>
      <p className="figure-note">
        Slide toward fewer decisions to make it stricter. The diamond is how sure each patient&apos;s switch had to be,
        set on runs 1 and 2 alone ({S.sure.n} patients; {S.sure.no_decision === 1 ? "one" : S.sure.no_decision} got no
        decision at all).
      </p>
    </>
  );
}

/** How often rest, hand and sixth-finger trials switch it on, on every decision or only when sure. */
export function WhatSwitchesOn() {
  const S = data.sixth;
  const [sure, setSure] = useState(false);
  const fires = sure ? "sure" : "all";
  return (
    <>
      <div className="toggle" role="radiogroup" aria-label="Which decisions">
        {[false, true].map((on) => (
          <button key={String(on)} type="button" role="radio" aria-checked={sure === on} onClick={() => setSure(on)}>
            {on ? "Only when sure" : "Every decision"}
          </button>
        ))}
      </div>
      <Bars
        rows={[
          { label: "Resting", value: S.fires.rest[fires] },
          { label: "Imagining the hand", value: S.fires.hand[fires], strong: true },
          { label: "Imagining the sixth finger", value: S.fires.finger[fires], strong: true },
        ]}
        format={pctFine}
        label={`How often the switch turns on: resting ${pctFine(S.fires.rest[fires])}, imagining the hand ${pct(S.fires.hand[fires])}, imagining the sixth finger ${pct(S.fires.finger[fires])}`}
      />
    </>
  );
}

/** The setup curves with a slider along the practice, reading both curves where it stands. */
export function SetupCurves() {
  const T = data.calibration.transfer;
  const S = data.calibration.scratch;
  const [i, setI] = useState(0);
  const toSeries = (pts: typeof T) => pts.map((p) => ({ x: p.minutes, y: p.mean, lo: p.ci[0], hi: p.ci[1] }));
  return (
    <>
      <Curves
        series={[
          { label: "Already learned from other patients", short: "From other patients", points: toSeries(T) },
          { label: "Starting from nothing", short: "From nothing", points: toSeries(S), muted: true },
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
        After {T[i].k} practice trial{T[i].k > 1 ? "s" : ""} of each movement ({minutes(T[i].minutes)}): already learned
        from other patients <b>{pct(T[i].mean)}</b>, starting from nothing <b>{pct(S[i].mean)}</b>.
      </p>
    </>
  );
}

/** The weeks-later scores, with or without the short practice on the new day. */
export function LaterBars() {
  const L = data.later;
  const [again, setAgain] = useState(false);
  return (
    <>
      <div className="toggle" role="radiogroup" aria-label="On the new day">
        {[false, true].map((on) => (
          <button key={String(on)} type="button" role="radio" aria-checked={again === on} onClick={() => setAgain(on)}>
            {on ? "Adjusted with 5 practice trials of each" : "Unchanged"}
          </button>
        ))}
      </div>
      <Bars
        rows={[
          { label: "On the day it was built", value: L.same_session },
          { label: "Two weeks later", value: again ? L.post.re_setup.mean : L.post.as_is.mean, strong: true },
          { label: "A month later", value: again ? L.follow.re_setup.mean : L.follow.as_is.mean, strong: true },
        ]}
        guess={1 / 3}
        label="Accuracy of the first session's model on the same day, two weeks later and a month later"
      />
    </>
  );
}

/** The demo's model played as if live: what it catches, how soon, and its mistakes. */
export function LiveFigures() {
  const s = data.switch;
  return (
    <dl className="figures-row">
      <div>
        <dt>{pct(s.detection)}</dt>
        <dd>of imagined movements switch it on</dd>
      </div>
      <div>
        <dt>{s.latency_s.toFixed(1)} s</dt>
        <dd>from the start of imagining</dd>
      </div>
      <div>
        <dt>{s.false_per_minute.toFixed(1)}</dt>
        <dd>mistaken switch-ons per minute of rest</dd>
      </div>
    </dl>
  );
}
