import { Controls } from "./components/Controls";
import { EEGPanel } from "./components/EEGPanel";
import { ManualTestBanner } from "./components/ManualTestBanner";
import { ModeBadge } from "./components/ModeBadge";
import { PredictionCard } from "./components/PredictionCard";
import { Told } from "./components/Told";
import { Explain } from "./explain/Explain";
import { useDemo } from "./store";
import { useDemoStream } from "./stream/useDemoStream";

export default function App() {
  const stream = useDemoStream();
  const source = useDemo((s) => s.source);
  const synthetic = useDemo((s) => s.synthetic);
  const error = useDemo((s) => s.error);
  return (
    <div className="app">
      <header className="top">
        <h1 className="top-name">Sixth-Finger BCI</h1>
        <p className="status">
          {synthetic && <span className="warn">Synthetic data</span>}
          <ModeBadge source={source} />
        </p>
      </header>
      <p className="lede">
        Imagine moving <em>a sixth finger</em>, and a model that reads the brain&apos;s signals moves it.
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <main className="stage">
        <Told />
        <section className="step step-signal" aria-label="The brain signal">
          <h2 className="step-title">
            <span className="step-num">2</span> Their brain signal
          </h2>
          <p className="step-note">Three of the 40 sensors, over the part of the brain that moves the hands</p>
          <EEGPanel />
        </section>
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
