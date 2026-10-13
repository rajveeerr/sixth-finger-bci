// How the paper tested its method against how we did, on one round of the test: twenty
// squares are trials, the orange ones the trials that round is scored on, and the bracket
// what the method's first step (CSP) learned from. The test repeats ten times so that every
// trial is scored once; only where the bracket ends differs.

import { data, pct } from "../data";

const L = data.leak;

const N = 20;
const TEST = new Set([6, 15]);

/** The runs of trials CSP learned from, as [first, last] indices. */
function segments(learnsFromTest: boolean): [number, number][] {
  const out: [number, number][] = [];
  for (let i = 0; i < N; i++) {
    if (!learnsFromTest && TEST.has(i)) continue;
    const last = out[out.length - 1];
    if (last && last[1] === i - 1) last[1] = i;
    else out.push([i, i]);
  }
  return out;
}

function Row({ title, note, learnsFromTest }: { title: string; note: string; learnsFromTest: boolean }) {
  return (
    <div className="leak-row">
      <div className="leak-label">
        <b>{title}</b>
        <span>{note}</span>
      </div>
      <div className="leak-strip">
        <div className="leak-squares" aria-hidden="true">
          {Array.from({ length: N }, (_, i) => (
            <i key={i} data-test={TEST.has(i) ? "" : undefined} />
          ))}
        </div>
        <div className="leak-bracket" aria-hidden="true">
          {segments(learnsFromTest).map(([from, to]) => (
            <i key={from} style={{ gridColumn: `${from + 1} / ${to + 2}` }} />
          ))}
        </div>
        <span className="leak-bracket-label">
          {learnsFromTest ? "CSP learns from all 20, test trials included" : "CSP learns from the 18 others only"}
        </span>
      </div>
    </div>
  );
}

/** The one step that differs between the paper's test and a fair one. */
export function LeakDiagram() {
  return (
    <figure className="leak" aria-label="The paper's test against a fair test, on one round of twenty trials">
      <Row
        title="The paper's way"
        note={`${pct(L.published[0])} to ${pct(L.published[1])} reported; ${pct(L.mean_replica)} in our rebuild`}
        learnsFromTest
      />
      <Row title="Fair" note={`${pct(L.mean_leakfree)}, where guessing gets 50%`} learnsFromTest={false} />
      <figcaption>
        Squares are trials; orange ones are the trials one round is scored on. CSP is the method&apos;s first step: it
        learns from labelled trials how to combine the 40 sensors. Only the bracket differs between the two rows.
      </figcaption>
    </figure>
  );
}
