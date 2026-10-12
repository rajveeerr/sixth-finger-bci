import { Controls } from "./components/Controls";
import { EEGPanel } from "./components/EEGPanel";
import { Hand } from "./components/Hand/Hand";
import { ManualTestBanner } from "./components/ManualTestBanner";
import { ModeBadge } from "./components/ModeBadge";
import { PhaseBar } from "./components/PhaseBar";
import { PredictionCard } from "./components/PredictionCard";
import { RealLimbPanel } from "./components/RealLimbPanel";
import { shownCommand, useDemo } from "./store";
import { useDemoStream } from "./stream/useDemoStream";

export default function App() {
  const stream = useDemoStream();
  const source = useDemo((s) => s.source);
  const synthetic = useDemo((s) => s.synthetic);
  const trialUid = useDemo((s) => s.trialUid);
  const error = useDemo((s) => s.error);
  const command = useDemo(shownCommand);
  const subject = trialUid.split("_")[0];
  return (
    <div className="app">
      <header className="masthead">
        <div>
          <h1>Sixth-Finger BCI</h1>
          <p className="subtitle">
            {subject ? `Recorded EEG of stroke patient ${subject}, replayed at real speed` : "Recorded EEG, replayed at real speed"}
          </p>
        </div>
        <div className="status">
          {synthetic && <span className="chip">Synthetic data</span>}
          <ModeBadge source={source} />
        </div>
      </header>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <main className="bench">
        <section className="paper" aria-label="EEG">
          <EEGPanel />
          <PhaseBar />
        </section>
        <Hand command={command} />
        <PredictionCard />
      </main>
      <Controls stream={stream} />
      <ManualTestBanner />
      <RealLimbPanel />
      <footer>
        EEG: Wang et al., Scientific Data 13, 1109 (2026), CC BY 4.0, held-out runs never used in
        training. Research prototype, not a medical device.
      </footer>
    </div>
  );
}
