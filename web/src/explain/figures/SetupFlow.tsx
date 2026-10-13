import { data, pct } from "../data";

// What a new patient goes through before the model can read them, three ways, with the
// practice drawn to scale: starting from nothing, starting from a model that has already
// learned from other patients, and coming back on another day. Every time and score is from data.json.

const S = data.calibration.scratch;
const T = data.calibration.transfer;
const perTrialPair = T[0].minutes / T[0].k; // one trial of each movement, in minutes
const reach = S.find((p) => p.mean >= T[0].mean - 0.005) ?? S[S.length - 1];
const RESETUP_K = 5;

const time = (min: number) =>
  min < 1 ? `about ${Math.round((min * 60) / 10) * 10} s` : `about ${Math.round(min)} min`;

const LANES = [
  {
    name: "Starting from nothing",
    before: null,
    k: reach.k,
    minutes: reach.minutes,
    learns: "Learns from these trials only",
    score: reach.mean,
  },
  {
    name: "Already learned from other patients",
    before: "Done once, beforehand: the recordings of all the other patients",
    k: T[0].k,
    minutes: T[0].minutes,
    learns: "Learns from these trials and the other patients",
    score: T[0].mean,
  },
  {
    name: "The same patient on another day",
    before: "Their model from the first day",
    k: RESETUP_K,
    minutes: RESETUP_K * perTrialPair,
    learns: "The old model is adjusted to today",
    score: data.later.post.re_setup.mean,
  },
];
const longest = Math.max(...LANES.map((l) => l.minutes));

/** The new patient's steps from cap to first reading, the practice to scale. */
export function SetupFlow() {
  return (
    <figure className="flow" id="setup-flow" aria-label="What a new patient does before the model can read them">
      <ol className="flow-lanes">
        {LANES.map((l) => (
          <li key={l.name}>
            <h4>{l.name}</h4>
            {l.before && <p className="flow-before">{l.before}</p>}
            <ol className="flow-steps">
              <li className="flow-step">Cap on</li>
              <li className="flow-step flow-practice">
                <span className="flow-bar" style={{ width: `${Math.max(8, (l.minutes / longest) * 100)}%` }} />
                <span>
                  {l.k} practice trial{l.k > 1 ? "s" : ""} of each movement, <b>{time(l.minutes)}</b>
                </span>
              </li>
              <li className="flow-step">{l.learns}, in seconds</li>
              <li className="flow-step flow-ready">
                <b>{pct(l.score)}</b> right
              </li>
            </ol>
          </li>
        ))}
      </ol>
      <figcaption className="flow-note">
        The bars show the practice time to scale; each trial takes 14 to 15 s. In this study every model was then tested
        on trials it never saw, the last two runs of that day. In real use there is no test: the patient just starts
        using it.
      </figcaption>
    </figure>
  );
}
