import { useDemo } from "../store";
import { PatientScreen } from "./PatientScreen";
import { TrialStrip } from "./TrialStrip";

const TOLD: Record<string, string> = {
  affected_hand: "Imagine moving the hand",
  sixth_finger: "Imagine moving the sixth finger",
};

/** Step 1: what is on the patient's screen right now, and where in the trial we are. */
export function Told() {
  const { phase, phaseTruth, trial, nTrials, trialUid } = useDemo();
  const patient = trialUid.split("_")[0]?.replace("sub-0", "").replace("sub-", "");
  const text =
    phase === "imagery" ? (TOLD[phaseTruth ?? ""] ?? "Imagine the movement") : phase === "prepare" ? "Get ready" : phase ? "Rest" : "…";
  return (
    <section className="step step-told" aria-label="What the patient is told">
      <h3 className="step-title">
        <span className="step-num">1</span> The patient is told
      </h3>
      <p className="told-now" data-kind={phase === "imagery" ? (phaseTruth ?? "") : (phase ?? "")} aria-live="polite">
        {text}
      </p>
      <PatientScreen kind={phase === "imagery" ? (phaseTruth ?? "") : (phase ?? "")} />
      <TrialStrip />
      <p className="step-note">
        {nTrials ? `Trial ${trial + 1} of ${nTrials}` : ""}
        {patient ? `, patient ${patient}, recorded` : ""}
      </p>
    </section>
  );
}
