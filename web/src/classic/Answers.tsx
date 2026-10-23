import { useEffect, useRef, useState } from "react";
import { pct } from "../explain/data";
import { EachPatient, LaterBars, LeakSlope, LiveFigures, SetupCurves, WhatSwitchesOn, WhenSure } from "../explain/figures/Evidence";
import { Gauge } from "../explain/figures/Gauge";
import { LeakDiagram } from "../explain/figures/LeakDiagram";
import { LearnTest } from "../explain/figures/LearnTest";
import { WhenSureTerm } from "../explain/refs";
import { ANSWERS, type Answer } from "./findings";

/** Answer 3 has three figures, each under a small name. */
function SixthEvidence() {
  return (
    <>
      <h4 className="evidence-title">Each patient</h4>
      <EachPatient />
      <h4 className="evidence-title">
        <WhenSureTerm>Acting only when sure</WhenSureTerm>
      </h4>
      <WhenSure />
      <h4 className="evidence-title">What switches the finger on</h4>
      <WhatSwitchesOn />
      <p className="evidence-say">
        How often each kind of trial in runs 3 and 4 switches it on. It never learned from an imagined hand movement,
        yet those switch it on almost as often as the sixth finger.
      </p>
    </>
  );
}

function Evidence({ a }: { a: Answer }) {
  switch (a.key) {
    case "leak":
      return (
        <>
          <LeakDiagram />
          <LeakSlope />
        </>
      );
    case "setup":
      return <SetupCurves />;
    case "sixth":
      return <SixthEvidence />;
    case "switch":
      return <LiveFigures />;
    case "later":
      return <LaterBars />;
  }
}

/** Which answer a #answer-N link asks for, if any. */
const fromHash = () => {
  const m = /^#answer-(\d)$/.exec(window.location.hash);
  const i = m ? Number(m[1]) - 1 : -1;
  return i >= 0 && i < ANSWERS.length ? i : null;
};

/** The five answers, one at a time: the dials are the tabs, each showing its score. */
export function Answers() {
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
  const a = ANSWERS[open];
  const n = open + 1;
  // The address follows the open answer, so a link to it opens it again later.
  const show = (i: number) => {
    setOpen(i);
    window.history.replaceState(null, "", `#answer-${i + 1}`);
  };
  const go = (i: number) => {
    const to = (i + ANSWERS.length) % ANSWERS.length;
    show(to);
    tabs.current[to]?.focus();
  };
  return (
    <div className="answers">
      <div className="answer-tabs" role="tablist" aria-label="The five answers">
        {ANSWERS.map((g, i) => (
          <button
            key={g.key}
            ref={(el) => {
              tabs.current[i] = el;
            }}
            id={`answer-${i + 1}`}
            type="button"
            role="tab"
            aria-selected={open === i}
            aria-controls="answer-panel"
            tabIndex={open === i ? 0 : -1}
            className="answer-tab"
            onClick={() => show(i)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight") go(i + 1);
              else if (e.key === "ArrowLeft") go(i - 1);
              else if (e.key === "Home") go(0);
              else if (e.key === "End") go(ANSWERS.length - 1);
              else return;
              e.preventDefault();
            }}
          >
            <Gauge value={g.value} other={g.other} guess={g.guess} />
            <span className="answer-tab-n">Question {i + 1}</span>
            <span className="answer-tab-name">{g.short}</span>
            <span className="answer-tab-value">
              <b>{pct(g.value)}</b> {g.scale}
            </span>
          </button>
        ))}
      </div>
      <section id="answer-panel" className="answer" role="tabpanel" aria-labelledby={`answer-${n}`}>
        <p className="finding-kicker">
          <a href={`#question-${n}`}>Question {n}</a>
        </p>
        <h3 className="finding-q">{a.question}</h3>
        <p className="finding-lead">{a.lead}</p>
        {a.answer && <p className="finding-a">{a.answer}</p>}
        {a.lines && (
          <dl className="finding-lines">
            {a.lines.map((l, i) => (
              <div key={i}>
                <dt>{l.label}</dt>
                <dd>{l.text}</dd>
              </div>
            ))}
          </dl>
        )}
        {a.points && (
          <ul className="finding-points">
            {a.points.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        )}
        <Evidence key={a.key} a={a} />
        <p className="finding-note">{a.note}</p>
        <div className="how">
          <h4>How we found this</h4>
          {a.split && <LearnTest split={a.split} />}
          <p>{a.how}</p>
          <ul>
            {a.see.map((s) => (
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
