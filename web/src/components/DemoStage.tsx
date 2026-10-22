import { data, pct } from "../explain/data";
import type { DemoStreamControls } from "../stream/useDemoStream";
import { useDemo } from "../store";
import { Controls } from "./Controls";
import { EEGPanel } from "./EEGPanel";
import { ModeBadge } from "./ModeBadge";
import { PredictionCard } from "./PredictionCard";
import { Told } from "./Told";

/** The demo itself: what the patient is told, their signal, what the model reads, and the controls. */
export function DemoStage({ stream }: { stream: DemoStreamControls }) {
  const source = useDemo((s) => s.source);
  const synthetic = useDemo((s) => s.synthetic);
  const error = useDemo((s) => s.error);
  const d = data.demo;
  return (
    <div className="demo bleed">
      <div className="demo-status">
        {synthetic && <span className="warn">Synthetic data</span>}
        <ModeBadge source={source} />
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="stage">
        <Told />
        <section className="step step-signal" aria-label="The brain signal">
          <h3 className="step-title">
            <span className="step-num">2</span> Their brain signal
          </h3>
          <p className="step-note">Three of the 40 sensors, over the part of the brain that moves the hands</p>
          <EEGPanel />
        </section>
        <PredictionCard />
      </div>
      <Controls stream={stream} />
      <dl className="modes">
        <div>
          <dt>Move or rest</dt>
          <dd>
            The finger follows one switch: the model&apos;s chance of rest against its chances of the hand and the sixth
            finger added together. It bends on Move whichever movement was imagined, because the model tells moving
            from resting far better than which movement (<a href="/#answer-3">question 3</a>). On this patient&apos;s{" "}
            {d.trials} trials it never saw, move or rest is right {pct(d.move_rest.acc)} of the time, and the guess at
            which movement {pct(d.hand_finger.acc)}.
          </dd>
        </div>
        <div>
          <dt>Per trial or continuous</dt>
          <dd>
            Per trial: the model reads two fixed 4 s stretches of each trial, one in the rest and one in the imagining,
            placed from the moment the instruction appeared. Continuous: it reads the newest 4 s every half second
            without knowing when the instruction came, as a real device would. The switch turns on when the steadied
            chance of a movement is above 60% twice in a row and off below 45%, as in{" "}
            <a href="/#answer-4">question 4</a>, and it makes more mistakes.
          </dd>
        </div>
      </dl>
    </div>
  );
}
