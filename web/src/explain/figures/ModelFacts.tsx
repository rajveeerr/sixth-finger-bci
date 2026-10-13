import { data } from "../data";

/** The model as one strip from input to output, then who it was built for; every number from the export. */
export function ModelFacts() {
  const d = data.demo;
  const patient = d.subject.replace("sub-0", "").replace("sub-", "");
  const rows = [
    {
      term: "One per patient",
      text: "Every brain is different, so each patient gets their own model. For the results we built one for each of the 22 patients.",
    },
    {
      term: `Why patient ${patient}`,
      text: "The demo plays one patient: the one whose result was closest to the middle of the group, so it shows a typical patient, not the best one.",
    },
    {
      term: "Learned and tested",
      text: `It learned from patient ${patient}'s first two runs (${d.training_trials} trials) and is tested on the last two, which it never saw: ${d.trials} whole trials, right ${Math.round(d.held_out_bal_acc * 100)}% of the time across the three choices, where guessing gets 33%.`,
    },
  ];
  return (
    <section className="facts" aria-label="The model in a few lines">
      <ol className="model-strip">
        <li>
          <span>In</span>
          <b>4 seconds of all 40 sensors</b>
          <small>1,000 readings from each</small>
        </li>
        <li>
          <span>The model</span>
          <b>EEGNet</b>
          <small>
            {d.parameters.toLocaleString("en")} numbers, {Math.round(d.model_bytes / 1000)} KB
          </small>
        </li>
        <li>
          <span>Out</span>
          <b>Rest, hand or sixth finger</b>
          <small>how likely each is; the likeliest is the command</small>
        </li>
      </ol>
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
