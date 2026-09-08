import { EEGPanel } from "./components/EEGPanel";
import { Hand } from "./components/Hand/Hand";
import { ModeBadge } from "./components/ModeBadge";
import { PredictionCard } from "./components/PredictionCard";
import { RealLimbPanel } from "./components/RealLimbPanel";
import { useDemo } from "./store";

export default function App() {
  const { source, command, lastPrediction, correct, total } = useDemo();
  return (
    <div className="app">
      <header>
        <h1>Sixth-Finger BCI</h1>
        <ModeBadge source={source} />
      </header>
      <main>
        <EEGPanel channels={[]} />
        <Hand command={command} />
        <PredictionCard prediction={lastPrediction} correct={correct} total={total} />
      </main>
      <RealLimbPanel />
      <footer>
        EEG data: Wang et al., Scientific Data 13, 1109 (2026), CC BY 4.0. Research prototype,
        not a medical device.
      </footer>
    </div>
  );
}
