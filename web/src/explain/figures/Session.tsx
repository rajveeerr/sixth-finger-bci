import { useState } from "react";
import { Plate } from "../../components/Plate";
import { TherapyTerm } from "../refs";

// How the recordings are organised: a trial is one 14 s round; a run is 20 trials in a row;
// a session is one visit of 4 runs. Runs 1 and 2 teach the model, runs 3 and 4 test it.
// Pointing at a run or a trial says what it is, so the figure itself carries no paragraphs.

const RUNS = [1, 2, 3, 4];
const PER_RUN = 20;

function say(run: number | null, trial: number | null) {
  if (run === null) return "One square is one trial of 14 seconds. Point at a run or a trial.";
  const use =
    run <= 2
      ? "The model learns from it."
      : "The model never sees it while learning; it is tested on it, and the demo plays it.";
  if (trial === null) return `Run ${run}: 20 trials in a row, about 5 minutes. ${use}`;
  return `Trial ${(run - 1) * PER_RUN + trial + 1} of 80, in run ${run}. ${use}`;
}

/** One session as four runs of twenty trials, and the three sessions over time. */
export function Session() {
  const [at, setAt] = useState<{ run: number; trial: number | null } | null>(null);
  return (
    <Plate
      title="Trials, runs and sessions"
      hint="80 trials make a session, about 20 minutes."
      className="plate-session"
    >
      <div className="session" onPointerLeave={() => setAt(null)}>
        <div className="session-runs">
          {RUNS.map((r) => (
            <button
              type="button"
              key={r}
              className="session-run"
              data-use={r <= 2 ? "learn" : "test"}
              data-on={at?.run === r ? "" : undefined}
              onPointerEnter={() => setAt({ run: r, trial: null })}
              onFocus={() => setAt({ run: r, trial: null })}
              onClick={() => setAt({ run: r, trial: null })}
              aria-label={say(r, null)}
            >
              <span className="session-run-name">Run {r}</span>
              <span className="session-trials" aria-hidden="true">
                {Array.from({ length: PER_RUN }, (_, t) => (
                  <i
                    key={t}
                    data-on={at?.run === r && at.trial === t ? "" : undefined}
                    onPointerEnter={() => setAt({ run: r, trial: t })}
                  />
                ))}
              </span>
            </button>
          ))}
        </div>
        <div className="session-brackets" aria-hidden="true">
          <span data-use="learn">the model learns</span>
          <span data-use="test">the model is tested</span>
        </div>
        <p className="session-say" aria-live="polite">
          {say(at?.run ?? null, at?.trial ?? null)}
        </p>
        <ol className="session-visits" aria-label="The three sessions">
          <li>
            <b>Session 1</b>
            <span>before therapy</span>
          </li>
          <li className="session-gap">
            <TherapyTerm />
          </li>
          <li>
            <b>Session 2</b>
            <span>after therapy</span>
          </li>
          <li className="session-gap">one month</li>
          <li>
            <b>Session 3</b>
            <span>follow-up</span>
          </li>
        </ol>
      </div>
    </Plate>
  );
}
