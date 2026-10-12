import { Controls } from "./components/Controls";
import { EEGPanel } from "./components/EEGPanel";
import { ManualTestBanner } from "./components/ManualTestBanner";
import { ModeBadge } from "./components/ModeBadge";
import { Panel } from "./components/Panel";
import { PredictionCard } from "./components/PredictionCard";
import { TrialStrip } from "./components/TrialStrip";
import { Explain } from "./explain/Explain";
import { IsoHand } from "./hands/IsoHand";
import { shownCommand, useDemo } from "./store";
import { useDemoStream } from "./stream/useDemoStream";

const COMMAND_TEXT: Record<string, string> = {
  IDLE: "keep still",
  HAND_GRASP: "close the hand",
  SIXTH_FINGER_FLEX: "bend the finger",
};

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
  const subject = trialUid.split("_")[0]?.replace("sub-0", "").replace("sub-", "");
  return (
    <div className="app">
      <header className="masthead">
        <h1 className="wordmark">Sixth-Finger BCI</h1>
        <div className="masthead-side">
          <p className="tagline">Move a robotic sixth finger by imagining the movement.</p>
          <p className="status">
            {synthetic && <span className="chip chip-warn">Synthetic data</span>}
            <span className="chip">
              {subject ? `Patient ${subject}'s recorded brain signals, played back` : "Recorded brain signals, played back"}
            </span>
            <ModeBadge source={source} />
          </p>
        </div>
      </header>
      <div className="divider" aria-hidden="true" />
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <main className="instrument">
        <Panel
          step={1}
          title="The brain signal"
          note={`EEG from 7 of 40 sensors${nTrials ? `, trial ${trial + 1} of ${nTrials}` : ""}`}
          className="panel-eeg"
          foot={
            <span className="legend-swatches">
              <i data-k="rest" /> rest <i data-k="ready" /> get ready <i data-k="hand" /> imagine hand{" "}
              <i data-k="sixth" /> imagine sixth finger
            </span>
          }
        >
          <EEGPanel />
          <TrialStrip />
        </Panel>
        <Panel
          step={2}
          title="The hand it moves"
          note="the robotic finger is on the wrist"
          className="panel-hand"
          foot={
            <>
              <span className="command" data-command={command}>
                {manual ? "Test pose " : ""}
                {command}: {COMMAND_TEXT[command]}
              </span>
              <span className="muted">keys 1, 2, 3 test it</span>
            </>
          }
        >
          <div className="hand-stage" data-testid="hand" data-command={command}>
            <IsoHand command={command} />
          </div>
        </Panel>
        <PredictionCard />
      </main>
      <Controls stream={stream} />
      <ManualTestBanner />
      <Explain />
      <footer className="colophon">
        <p>
          Brain signals: Wang et al., Scientific Data 13, 1109 (2026), CC BY 4.0. The recordings played here were never
          used to train the model. A research prototype, not a medical device.
        </p>
        <p>B.Tech minor project by Rajveer Singh, Vivek Yadav and Ansh Dahiya, guided by Dr. Suman Lata.</p>
      </footer>
    </div>
  );
}
