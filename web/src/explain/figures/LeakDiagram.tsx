// How the paper tested its method against a leakage-free test, on one round of it: twenty
// squares are trials, the orange ones the trials that round is scored on, and the bracket
// what the method's first step (CSP) learned from. The test repeats ten times so that every
// trial is scored once; only where the bracket ends differs.

import { data, pct } from "../data";

const L = data.leak;
const R = L.recipe;

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
          {learnsFromTest
            ? "The first step studies all 20 trials, the 2 test trials included"
            : "The first step studies only the 18 learning trials"}
        </span>
      </div>
    </div>
  );
}

/** The one step that differs between the paper's test and a leakage-free one. */
export function LeakDiagram() {
  return (
    <figure className="leak" aria-label="The paper's test against a leakage-free test, on one round of twenty trials">
      {/* The figure exporter keeps only the names in the key, for print. */}
      <p className="leak-key">
        <span>
          <i className="leak-key-learn" />
          <span>
            Learning trials
            <span className="leak-key-more">: the method studies these, with the movement each one was</span>
          </span>
        </span>
        <span>
          <i className="leak-key-test" />
          <span>
            Test trials
            <span className="leak-key-more">
              : kept aside; the method must say which movement each one was, and its score is how often it is right
            </span>
          </span>
        </span>
      </p>
      <Row
        title="The paper's way"
        note={`${pct(L.published[0])} to ${pct(L.published[1])} reported; rebuilt, ${pct(R.paper_way)} their recipe, ${pct(L.mean_replica)} standard`}
        learnsFromTest
      />
      <Row
        title="Leakage-free"
        note={`${pct(R.leakfree)} their recipe, ${pct(L.mean_leakfree)} standard; guessing gets 50%`}
        learnsFromTest={false}
      />
      <figcaption>
        Each square is one trial: one round of resting, then imagining a movement. The test repeats ten times, with
        different test trials each time, so every trial is tested once. The first step (CSP) works out how to combine
        the 40 sensors. Only the bracket differs between the two rows.
      </figcaption>
    </figure>
  );
}
