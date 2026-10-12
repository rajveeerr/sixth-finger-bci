import { Plate } from "../components/Plate";
import { BrainRhythm } from "./figures/BrainRhythm";
import { PatientSees } from "./figures/PatientSees";
import { RealLimb } from "./figures/RealLimb";
import { ResultsBars, ResultsGauges } from "./figures/Results";
import { SignalChain } from "./figures/SignalChain";

// Two ways to show the results while the choice is open: ?results=gauges (default) or bars.
const RESULTS = new URLSearchParams(window.location.search).get("results") === "bars" ? "bars" : "gauges";

/** The explanation under the demo: how it works, what we found, and the way to a real limb. */
export function Explain() {
  return (
    <div className="explain">
      <section className="chapter" aria-labelledby="how">
        <header className="chapter-head">
          <h2 id="how">How it works</h2>
          <p>
            A stroke can leave a hand weak, but imagining a movement still changes the brain&apos;s signals. A small
            model learns to read that change from one patient&apos;s recordings and turns it into a command for a
            robotic finger.
          </p>
        </header>
        <div className="figures">
          <SignalChain />
          <div className="wide">
            <PatientSees />
          </div>
          <div className="wide">
            <BrainRhythm />
          </div>
        </div>
      </section>
      <section className="chapter" aria-labelledby="found">
        <header className="chapter-head">
          <h2 id="found">What we found</h2>
          <p>
            We tested the model on 22 patients, always on recordings it had never seen. Five questions, each with a
            plain answer.
          </p>
        </header>
        <div className="figures">
          <div className="wide">
            <Plate
              fig={7}
              title="Five questions"
              hint={RESULTS === "bars" ? "The dashed line is what guessing gets" : "The needle is our score"}
              readout="22 patients"
              className="plate-results"
            >
              {RESULTS === "bars" ? <ResultsBars /> : <ResultsGauges />}
            </Plate>
          </div>
        </div>
      </section>
      <section className="chapter" aria-labelledby="limb">
        <header className="chapter-head">
          <h2 id="limb">From the demo to a real limb</h2>
          <p>
            The brain signals, the model and the commands are real. Only the last two steps, the motor and the
            finger, are drawn instead of built.
          </p>
        </header>
        <div className="figures">
          <div className="wide">
            <RealLimb />
          </div>
        </div>
      </section>
    </div>
  );
}
