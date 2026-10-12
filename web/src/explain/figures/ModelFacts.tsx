import { data } from "../data";

/** The model in a few plain lines, every number from the export. */
export function ModelFacts() {
  const d = data.demo;
  const patient = d.subject.replace("sub-0", "").replace("sub-", "");
  const rows = [
    { term: "What it is", text: `EEGNet, a small network for EEG: ${d.parameters.toLocaleString("en")} numbers, ${Math.round(d.model_bytes / 1000)} KB on disk.` },
    { term: "What it reads", text: "4 s of all 40 sensors at once, 1,000 readings from each." },
    { term: "What it says", text: "How likely rest, the hand and the sixth finger are. The likeliest is the command." },
    { term: "What it learned from", text: `${d.training_trials} trials of patient ${patient}, from the first two of four recordings.` },
    { term: "How it did", text: `${Math.round(d.held_out_bal_acc * 100)}% right on the ${d.trials} later trials it never saw, the ones the demo plays, against 33% for guessing.` },
    { term: "Where it runs", text: "On a server, or in this browser when there is none. The demo says which, and how long each reading took." },
  ];
  return (
    <section className="facts" aria-label="The model in six lines">
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
