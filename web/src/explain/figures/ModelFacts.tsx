import { data } from "../data";

/** The model in a few plain lines, every number from the export. */
export function ModelFacts() {
  const d = data.demo;
  const patient = d.subject.replace("sub-0", "").replace("sub-", "");
  const rows = [
    { term: "What it is", text: `EEGNet, a small network for EEG: ${d.parameters.toLocaleString("en")} numbers, ${Math.round(d.model_bytes / 1000)} KB.` },
    { term: "What it reads", text: "4 seconds of all 40 sensors at once: 1,000 readings from each." },
    { term: "What it says", text: "How likely rest, the hand and the sixth finger are. The likeliest is the command." },
    { term: "One per patient", text: "Every brain is different, so each patient gets their own model. For the results we built one for each of the 22 patients." },
    { term: "Why patient " + patient, text: `The demo can play only one patient. We picked the one whose result was closest to the middle of the group, so the demo shows a typical patient, not the best one.` },
    { term: "Learned from", text: `Patient ${patient}'s first two runs: ${d.training_trials} trials.` },
    { term: "Tested on", text: `Their last two runs, which it never saw: ${d.trials} whole trials, two readings each (one resting, one imagining). ${Math.round(d.held_out_bal_acc * 100)}% of its readings are right across the three choices; guessing gets 33%. The demo plays these runs.` },
  ];
  return (
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
  );
}
