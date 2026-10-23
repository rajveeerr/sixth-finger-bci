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
          <p className="step-note">Three of the 40 sensors, over the hand area</p>
          <EEGPanel />
        </section>
        <PredictionCard />
      </div>
      <Controls stream={stream} />
    </div>
  );
}
