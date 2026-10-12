import { useDemo } from "../store";

const LABEL: Record<string, string> = { affected_hand: "affected hand", sixth_finger: "sixth finger" };

/** What the patient was doing at this moment of the recording. */
export function PhaseBar() {
  const { phase, phaseTruth, trial, nTrials } = useDemo();
  const steps = [
    { key: "rest", text: "Rest" },
    { key: "prepare", text: "Get ready" },
    { key: "imagery", text: phase === "imagery" && phaseTruth ? `Imagine: ${LABEL[phaseTruth] ?? phaseTruth}` : "Imagine" },
  ];
  return (
    <div className="phase-bar" data-testid="phase" data-phase={phase ?? ""}>
      <ol>
        {steps.map((s) => (
          <li key={s.key} className={phase === s.key ? "on" : ""} data-cue={s.key === "imagery" ? (phaseTruth ?? "") : ""}>
            {s.text}
          </li>
        ))}
      </ol>
      <span className="trial-count">{nTrials ? `Trial ${trial + 1} of ${nTrials}` : ""}</span>
    </div>
  );
}
