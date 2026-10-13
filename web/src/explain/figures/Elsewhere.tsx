import { useState } from "react";
import { Plate } from "../../components/Plate";
import { data, pct } from "../data";

// The mistake behind the published 85%, measured in other data: two public datasets of
// imagined hand movements (healthy volunteers) and two of depression detection from
// resting EEG. Each row is one dataset and method, scored the leaky way and fairly.

const E = data.elsewhere;
const NAMES: Record<string, string> = {
  BNCI2014_001: "BNCI 2014-001",
  Cho2017: "Cho 2017",
  mumtaz: "Mumtaz",
  modma: "MODMA",
};
const METHOD: Record<string, string> = { bp_lr: "frequency bands", ts_lr: "sensor pairs" };

interface Row {
  key: string;
  name: string;
  about: string;
  leaky: number;
  fair: number;
  why: string;
}

const MOTOR_WHY =
  "Leaky: the method's first step learned from every trial and its label, test trials included, before the test. Fair: it learned from the learning trials only.";
const DEPRESSION_WHY =
  "Each person's recording is cut into 4 s pieces. Leaky: pieces of the same person go into both learning and testing, so the model can recognise the person instead of depression. Fair: all of a person's pieces stay on one side.";

const GROUPS: { title: string; about?: string; rows: Row[] }[] = [
  {
    title: "Imagined movement",
    rows: [
      {
        key: "ours",
        name: "These recordings",
        about: `${data.leak.subjects.length} stroke patients, hand or sixth finger`,
        leaky: data.leak.mean_replica,
        fair: data.leak.mean_leakfree,
        why: MOTOR_WHY,
      },
      ...E.motor.map((m) => ({
        key: m.dataset,
        name: NAMES[m.dataset] ?? m.dataset,
        about: `${m.n} healthy volunteers, left or right hand`,
        leaky: m.leaky,
        fair: m.fair,
        why: MOTOR_WHY,
      })),
    ],
  },
  {
    title: "Depression from resting EEG",
    about:
      "Not part of the sixth-finger work: a second, unrelated field where EEG studies often test this way, used to check whether the mistake matters beyond our recordings.",
    rows: E.depression.map((d) => ({
      key: `${d.dataset}-${d.pipeline}`,
      name: `${NAMES[d.dataset] ?? d.dataset}, ${METHOD[d.pipeline] ?? d.pipeline}`,
      about: `${d.n} people, with and without depression`,
      leaky: d.leaky,
      fair: d.fair,
      why: DEPRESSION_WHY,
    })),
  },
];

const X0 = 0.4;
const X1 = 1;
const at = (v: number) => `${((v - X0) / (X1 - X0)) * 100}%`;

/** Leaky and fair scores side by side for every dataset we checked. */
export function Elsewhere() {
  const [on, setOn] = useState<string | null>(null);
  const all = GROUPS.flatMap((g) => g.rows);
  const picked = all.find((r) => r.key === on);
  return (
    <Plate
      title="The same mistake in other data"
      hint={`Each row is one dataset: grey is the score tested the leaky way, black tested fairly. The further apart, the more the leak flattered the result. As a check, with the diagnoses shuffled among the Mumtaz volunteers so that they mean nothing, the leaky test still scored ${pct(E.depression_shuffled.leaky)} and the fair one ${pct(E.depression_shuffled.fair)} (${E.depression_shuffled.shuffles} shuffles): the leaky test recognises the person, not the illness.`}
      readout={
        picked ? (
          <>
            <b>{picked.name}.</b> {picked.why}
          </>
        ) : (
          "Point at or tap a row for how the leak worked there."
        )
      }
      className="plate-elsewhere"
      label="Leaky and fair scores for seven dataset and method pairs"
    >
      <div className="dumbbells" id="elsewhere">
        {GROUPS.map((g) => (
          <section key={g.title}>
            <h4>{g.title}</h4>
            {g.about && <p className="dumbbell-about">{g.about}</p>}
            {g.rows.map((r) => (
              <button
                type="button"
                key={r.key}
                className="dumbbell"
                data-on={on === r.key ? "" : undefined}
                onPointerEnter={() => setOn(r.key)}
                onPointerLeave={(e) => e.pointerType === "mouse" && setOn(null)}
                onFocus={() => setOn(r.key)}
                onClick={() => setOn(r.key)}
              >
                <span className="dumbbell-name">
                  {r.name}
                  <small>{r.about}</small>
                </span>
                <span className="dumbbell-track" aria-hidden="true">
                  <i
                    className="dumbbell-line"
                    style={{ left: at(r.fair), width: `calc(${at(r.leaky)} - ${at(r.fair)})` }}
                  />
                  <i className="dumbbell-dot dumbbell-fair" style={{ left: at(r.fair) }} />
                  <i className="dumbbell-dot dumbbell-leaky" style={{ left: at(r.leaky) }} />
                </span>
                <span className="dumbbell-values">
                  {pct(r.leaky)} <span aria-hidden="true">to</span> <b>{pct(r.fair)}</b>
                </span>
              </button>
            ))}
          </section>
        ))}
        <div className="dumbbell-axis" aria-hidden="true">
          <span />
          <span className="dumbbell-ticks">
            {[0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1].map((t) => (
              <i key={t} style={{ left: at(t) }}>
                {pct(t)}
              </i>
            ))}
          </span>
          <span />
        </div>
      </div>
    </Plate>
  );
}
