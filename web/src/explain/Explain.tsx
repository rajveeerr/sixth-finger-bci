import type { ReactNode } from "react";
import { BrainRhythm } from "./figures/BrainRhythm";
import { PatientSees } from "./figures/PatientSees";
import { RealLimb } from "./figures/RealLimb";
import { ResultsGauges } from "./figures/Results";
import { SignalChain } from "./figures/SignalChain";

function Chapter({ id, n, title, lede, children }: { id: string; n: number; title: string; lede: ReactNode; children: ReactNode }) {
  return (
    <section className="chapter" aria-labelledby={id}>
      <header className="chapter-head">
        <h2 id={id}>{title}</h2>
        <span className="chapter-rule" aria-hidden="true" />
        <span className="chapter-num" aria-hidden="true">
          {String(n).padStart(2, "0")}
        </span>
      </header>
      <p className="chapter-lede">{lede}</p>
      {children}
    </section>
  );
}

/** The explanation under the demo: how it works, what we found, and the way to a real limb. */
export function Explain() {
  return (
    <div className="explain">
      <Chapter
        id="how"
        n={1}
        title="How it works"
        lede={
          <>
            A stroke can leave a hand weak, but <em>imagining</em> a movement still changes the brain&apos;s signals. A
            small model learns that change from one patient&apos;s recordings and turns it into a command for a robotic
            finger.
          </>
        }
      >
        <SignalChain />
        <PatientSees />
        <BrainRhythm />
      </Chapter>
      <Chapter
        id="found"
        n={2}
        title="What we found"
        lede={
          <>
            We tested the model on 22 patients, always on recordings it had <em>never seen</em>. Five questions, each with
            a plain answer.
          </>
        }
      >
        <ResultsGauges />
      </Chapter>
      <Chapter
        id="limb"
        n={3}
        title="From the demo to a real limb"
        lede={
          <>
            The brain signals, the model and the commands are real. Only the last two steps, the motor and the finger,
            are <em>drawn instead of built</em>.
          </>
        }
      >
        <RealLimb />
      </Chapter>
    </div>
  );
}
