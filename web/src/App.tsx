import { lazy, Suspense } from "react";
import { Controls } from "./components/Controls";
import { EEGPanel } from "./components/EEGPanel";
import { ManualTestBanner } from "./components/ManualTestBanner";
import { ModeBadge } from "./components/ModeBadge";
import { Plate } from "./components/Plate";
import { PredictionCard } from "./components/PredictionCard";
import { TrialStrip } from "./components/TrialStrip";
import { Explain } from "./explain/Explain";
import { shownCommand, useDemo } from "./store";
import { useDemoStream } from "./stream/useDemoStream";

// three.js and the hand load after the page, so the EEG and the decision come up first.
const Hand = lazy(() => import("./components/Hand/Hand").then((m) => ({ default: m.Hand })));

export default function App() {
  const stream = useDemoStream();
  const source = useDemo((s) => s.source);
  const synthetic = useDemo((s) => s.synthetic);
  const trialUid = useDemo((s) => s.trialUid);
  const error = useDemo((s) => s.error);
  const manual = useDemo((s) => s.manualMode);
  const trial = useDemo((s) => s.trial);
  const nTrials = useDemo((s) => s.nTrials);
  const command = useDemo(shownCommand);
  const subject = trialUid.split("_")[0];
  return (
    <div className="app">
      <header className="masthead">
        <div className="masthead-text">
          <h1>Sixth-Finger BCI</h1>
          <p className="lede">
            A stroke patient imagines a movement. A decoder reads it from the EEG and moves a robotic sixth finger.
          </p>
        </div>
        <div className="status">
          {synthetic && <span className="chip chip-warn">Synthetic data</span>}
          <span className="chip">{subject ? `Patient ${subject}, recorded EEG replayed` : "Recorded EEG, replayed"}</span>
          <ModeBadge source={source} />
        </div>
      </header>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <main className="instrument">
        <Plate
          fig={1}
          title="EEG over the hand area"
          hint="7 of 40 channels, the last 8 s"
          readout={nTrials ? `Trial ${trial + 1} of ${nTrials}` : ""}
          className="plate-eeg"
          label="EEG"
        >
          <EEGPanel />
          <TrialStrip />
        </Plate>
        <Plate
          fig={2}
          title="Hand and robotic sixth finger"
          hint="Drag to turn it. Keys 1, 2, 3 test the poses"
          readout={
            <span className="command" data-command={command}>
              {manual ? "Manual test " : ""}
              {command}
            </span>
          }
          className="plate-hand"
        >
          <Suspense
            fallback={
              <div className="hand hand-loading" data-testid="hand" data-command={command}>
                Loading the 3D hand
              </div>
            }
          >
            <Hand command={command} />
          </Suspense>
        </Plate>
        <PredictionCard />
      </main>
      <Controls stream={stream} />
      <ManualTestBanner />
      <Explain />
      <footer className="colophon">
        <p>
          EEG: Wang et al., Scientific Data 13, 1109 (2026), CC BY 4.0. The runs replayed here were never used in
          training. Research prototype, not a medical device.
        </p>
        <p>B.Tech minor project by Rajveer Singh, Vivek Yadav and Ansh Dahiya, guided by Dr. Suman Lata.</p>
      </footer>
    </div>
  );
}
