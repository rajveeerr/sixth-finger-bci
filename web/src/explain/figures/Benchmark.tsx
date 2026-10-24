// Every headline score in one table, tested the same leakage-free way, then one line for each result
// that was tested its own way. The best of each row is the one marked; on a phone each task
// becomes a card.
import { benchRow, data, pct, pct1, pctRange, type BenchRow } from "../data";
import { about, AGAIN_MIN } from "../findings";

const B = data.benchmark;

const METHODS = [
  { key: "csp_lda", name: "CSP+LDA" },
  { key: "ts_lr", name: "Tangent space + logistic regression" },
  { key: "eegnet_scratch", name: "EEGNet per patient" },
] as const;

const TASKS: { key: BenchRow["key"]; name: string }[] = [
  { key: "T3_sf_vs_rest", name: "Sixth finger or rest" },
  { key: "T1_ah_vs_sf", name: "Hand or sixth finger" },
  { key: "T2_rest_ah_sf", name: "Rest, hand or sixth finger" },
];

const BEST: Record<BenchRow["best"]["method"], string> = {
  ts_lr_c14: "Movement-area switch",
  eegnet_ea_ft: "EEGNet that learned from other patients first",
  eegnet_scratch: "EEGNet per patient, the demo's model",
};

export function BenchTable() {
  return (
    <figure className="bench">
      <table className="bench-table">
        <caption>
          Balanced accuracy, the mean of {B.n} patients. Each model learned from runs 1 and 2 of a patient&apos;s first
          session and was tested on runs 3 and 4.
        </caption>
        <thead>
          <tr>
            <th scope="col">Task</th>
            {METHODS.map((m) => (
              <th scope="col" key={m.key} className="bench-num">
                {m.name}
              </th>
            ))}
            <th scope="col" className="bench-best">
              Best
            </th>
          </tr>
        </thead>
        <tbody>
          {TASKS.map(({ key, name }) => {
            const row = benchRow(key);
            return (
              <tr key={key} data-task={key}>
                <th scope="row">
                  <span className="bench-task">{name}</span>
                  <span className="bench-guess">guessing gets {pct(row.chance)}</span>
                </th>
                {METHODS.map((m) => (
                  <td key={m.key} className="bench-num" data-label={m.name}>
                    {pct1(row[m.key])}
                  </td>
                ))}
                <td className="bench-best" data-label="Best">
                  <b>{pct1(row.best.mean)}</b>
                  <span className="bench-how">
                    {BEST[row.best.method]}
                    {row.best.sure !== undefined && <span className="bench-sure">{pct1(row.best.sure)} when sure</span>}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </figure>
  );
}

const S = B.setup;
/** "about 30 s" with the number and its unit kept on one line. */
const aboutTime = (minutes: number) => about(minutes).replace(/ (s|min)$/, "\u00a0$1");
const LIVE = B.live;

const LINES = [
  {
    label: "Setting up",
    text: `Rest, hand or sixth finger: ${pct(S.from_others.mean)} after ${aboutTime(S.from_others.minutes)} of practice if the model learned from other patients first, the one way we tried, ${pct(S.from_nothing.mean)} from nothing; after ${aboutTime(S.from_nothing_end.minutes)}, ${pct(S.from_nothing_end.mean)} from nothing and ${pct(S.from_others_end.mean)} with help, a gap we did not test.`,
  },
  {
    label: "Another day",
    text: `Two weeks later, ${pct(B.later.as_is)} with the first session's model unchanged, ${pct(B.later.re_setup)} after ${aboutTime(AGAIN_MIN)} of practice.`,
  },
  {
    label: "Live",
    text: `Played as if live, the replay fixed in advance gave the sixth-finger command in ${pctRange(LIVE.prereg)} of sixth-finger periods. Read afterwards as switches, the demo's model catches ${pct(LIVE.demo.detection)} of imagined movements with ${LIVE.demo.false_per_minute.toFixed(1)} mistakes a minute of rest, and the movement-area switch ${pct(LIVE.switch.finger_on)} of sixth-finger periods with ${LIVE.switch.false_per_minute.toFixed(1)}.`,
  },
  {
    label: "The leak",
    text: `Hand or sixth finger, the authors' recipe rebuilt: ${pct1(B.leak.recipe_paper_way)} tested the paper's way, ${pct1(B.leak.recipe_leakfree)} leakage-free; a standard CSP+LDA, ${pct1(B.leak.paper_way)} and ${pct1(B.leak.leakfree)}.`,
  },
  {
    label: "Model size",
    text: `The demo's model has ${B.model.parameters.toLocaleString("en")} parameters and weighs ${Math.round(B.model.bytes / 1000)} KB.`,
  },
];

export function BenchLines() {
  return (
    <dl className="bench-lines">
      {LINES.map((l) => (
        <div key={l.label}>
          <dt>{l.label}</dt>
          <dd>{l.text}</dd>
        </div>
      ))}
    </dl>
  );
}
