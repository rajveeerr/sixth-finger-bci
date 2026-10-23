import type { ReactNode } from "react";
import { data, pct } from "../data";
import { ScoreTerm } from "../refs";
import { ModelDrawing } from "./ModelDrawing";

/** The model drawn from input to output, then who it was built for; every number from the export. */
export function ModelFacts() {
  const d = data.demo;
  const rt = data.runtime;
  const patient = d.subject.replace("sub-0", "").replace("sub-", "");
  const kept = data.leak.subjects.length;
  const rows: { term: string; text: ReactNode }[] = [
    {
      term: "One model per patient",
      text: (
        <>
          Brain signals differ from person to person: the shape of the head, where the stroke was, how each person
          imagines a movement. A model learned on one person reads another poorly, so each patient gets their own, as is
          usual for BCIs. It can learn from that patient alone, or also from other patients and then be adjusted to this
          one (<a href="#use">how a patient would use it</a>). For the results we built one for each of the {kept}{" "}
          patients with a usable first session; two lost theirs to a <a href="#data">data problem</a>.
        </>
      ),
    },
    {
      term: "Is that costly?",
      text: (
        <>
          No: the models are tiny. EEGNet has {d.parameters.toLocaleString("en")} numbers to learn, where a phone photo
          has millions of pixels. The simpler method (CSP with LDA) learns a patient in about{" "}
          {rt.csp_lda_fit_s.toFixed(2)} s on a laptop, and EEGNet in seconds. The heaviest training, {rt.pretrain_n}{" "}
          models that each learn from all the other patients, took about {Math.round(rt.pretrain_s_median / 60)} minutes
          each{rt.pretrain_on_gpu ? " on a rented graphics card (GPU)" : ""}.
        </>
      ),
    },
    {
      term: `Why patient ${patient}`,
      text: (
        <>
          The demo plays one patient. We picked the one whose earlier test score ({pct(d.chosen_by_bal_acc)}) was
          closest to the middle of the group ({pct(d.group_median_bal_acc)}), so it shows a typical patient, not the
          best one.
        </>
      ),
    },
    {
      term: "Learned and tested",
      text: (
        <>
          It learned from patient {patient}&apos;s first two runs ({d.training_trials} trials, all that those runs hold
          for this patient) and is tested on the last two, which it never saw. Of their {d.trials_total} trials,{" "}
          {d.trials_total - d.trials} are cut short where a run ends, so the demo plays the {d.trials} whole ones. On
          those it is <ScoreTerm>right {pct(d.held_out_bal_acc)} of the time</ScoreTerm> across the three choices, where
          guessing gets 33%, and {pct(d.move_rest.acc)} at move or rest, the switch that moves the demo&apos;s finger:
          one patient on {d.trials} trials, not a promise for a new patient.
        </>
      ),
    },
  ];
  return (
    <>
      <ModelDrawing />
      <section className="facts" aria-label="The model in a few lines">
        <dl>
          {rows.map((r) => (
            <div key={r.term}>
              <dt>{r.term}</dt>
              <dd>{r.text}</dd>
            </div>
          ))}
        </dl>
      </section>
    </>
  );
}
