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
          <dt>Three choices or on/off switch</dt>
          <dd>
            Three choices: the model picks rest, hand or sixth finger, and the finger bends only for sixth finger.
            On/off switch: the finger bends whenever the model thinks either movement is imagined. Our results support
            the switch, since the model can barely tell the two movements apart.
          </dd>
        </div>
        <div>
          <dt>Per trial or continuous</dt>
          <dd>
            Per trial: the model reads two fixed 4 s stretches of each trial, one in the rest and one in the imagining,
            placed from the moment the instruction appeared. Continuous: it reads the newest 4 s every half second
            without knowing when the instruction came, as a real device would, and makes more mistakes.
          </dd>
        </div>
      </dl>
    </div>
  );
}
