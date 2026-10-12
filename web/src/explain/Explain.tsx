import { data, pct } from "./data";
import { Calibration } from "./figures/Calibration";
import { Electrodes } from "./figures/Electrodes";
import { Leak } from "./figures/Leak";
import { RealLimb } from "./figures/RealLimb";
import { Rhythm } from "./figures/Rhythm";
import { SignalChain } from "./figures/SignalChain";
import { Switch } from "./figures/Switch";
import { TellApart } from "./figures/TellApart";
import { Trial } from "./figures/Trial";

/** The explanation under the instrument: how it works and what the study found. */
export function Explain() {
  return (
    <div className="explain">
      <section className="chapter" aria-labelledby="how">
        <header className="chapter-head">
          <h2 id="how">How it works</h2>
          <p>
            A stroke can leave a hand weak, but imagining its movement still changes the EEG over the motor cortex.
            A small network, trained on one patient&apos;s own recordings, reads that change in each{" "}
            <strong>4 s window</strong> and turns it into a command for a robotic sixth finger worn at the wrist.
          </p>
        </header>
        <div className="figures">
          <SignalChain />
          <Electrodes />
          <Rhythm />
          <div className="wide">
            <Trial />
          </div>
        </div>
      </section>
      <section className="chapter" aria-labelledby="found">
        <header className="chapter-head">
          <h2 id="found">What we found</h2>
          <p>
            Across 22 patients, <strong>rest and imagery are easy to tell apart</strong>; which movement was imagined
            is not. A published 85% for that harder question came from test data leaking into training. The decoder
            in the demo scores {pct(data.demo.held_out_bal_acc)} (balanced over the three commands) on the{" "}
            {data.demo.trials * 2} windows replayed above.
          </p>
        </header>
        <div className="figures">
          <TellApart />
          <Leak />
          <Calibration />
          <Switch />
        </div>
      </section>
      <section className="chapter" aria-labelledby="limb">
        <header className="chapter-head">
          <h2 id="limb">From the demo to a limb</h2>
          <p>
            The EEG, the decoder and the commands are real. Only the last two layers, the controller and the
            limb, are drawn instead of built.
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
