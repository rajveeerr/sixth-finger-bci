import { Chapter } from "../../components/Chapter";
import { DatasetRef, FingerRef, RehabRef } from "../refs";

/** The problem in four steps, from the weak hand to our question; the chapter-by-chapter page shows them too. */
export function ProblemSteps() {
  return (
    <ol className="problem">
      <li>
        <h3>After a stroke</h3>
        <p>Months later, one hand is often still weak. Holding a cup, a bag or a phone with it is hard.</p>
      </li>
      <li>
        <h3>A sixth finger</h3>
        <p>
          A <FingerRef>robotic finger</FingerRef> worn on that wrist presses things against the palm, so the hand can
          hold them again.
        </p>
      </li>
      <li>
        <h3>Moved by imagining</h3>
        <p>
          The patient imagines moving it, and it moves. Pairing imagined movement with a device that moves has also been
          used in <RehabRef>therapy after a stroke</RehabRef>.
        </p>
      </li>
      <li>
        <h3>Our question</h3>
        <p>
          Can the recordings of <DatasetRef>24 stroke patients</DatasetRef> tell when they imagine the sixth finger?
        </p>
      </li>
    </ol>
  );
}

export function Problem() {
  return (
    <Chapter
      q="problem"
      answer={
        <>
          A stroke often leaves one hand too weak to grip; a robotic sixth finger can grip for it, moving when the
          patient imagines it.
        </>
      }
    >
      <ProblemSteps />
    </Chapter>
  );
}
