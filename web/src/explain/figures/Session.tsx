import { Plate } from "../../components/Plate";

// How the recordings are organised: a trial is one 14 s round; a run is 20 trials in a row;
// a session is one visit of 4 runs. Runs 1 and 2 teach the model, runs 3 and 4 test it. Each
// patient came for three sessions.

const RUNS = [1, 2, 3, 4];
const TRIALS = Array.from({ length: 20 }, (_, i) => i);

/** One session as four runs of twenty trials, and the three sessions over time. */
export function Session() {
  return (
    <Plate
      title="Trials, runs and sessions"
      hint="One square is one trial: 14 s of rest, get ready, imagine."
      readout="Patients 21 and 22 lost their first session to a data problem (see chapter 5), so most results use 22 patients."
    >
      <div className="session">
        <div className="session-runs">
          {RUNS.map((r) => (
            <div key={r} className="session-run" data-use={r <= 2 ? "learn" : "test"}>
              <span className="session-run-name">Run {r}</span>
              <span className="session-trials" aria-hidden="true">
                {TRIALS.map((t) => (
                  <i key={t} />
                ))}
              </span>
              <span className="session-run-note">20 trials, about 5 min</span>
            </div>
          ))}
        </div>
        <div className="session-split">
          <p>
            <b>Runs 1 and 2: the model learns.</b> 40 trials, 20 of each movement.
          </p>
          <p>
            <b>Runs 3 and 4: the model is tested.</b> 40 trials it has never seen. The demo plays these.
          </p>
        </div>
        <ol className="session-visits">
          <li>
            <b>Session 1</b> before therapy
          </li>
          <li className="session-gap">two weeks of therapy</li>
          <li>
            <b>Session 2</b> after therapy
          </li>
          <li className="session-gap">one month</li>
          <li>
            <b>Session 3</b> follow-up
          </li>
        </ol>
      </div>
    </Plate>
  );
}
