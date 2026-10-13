import { DemoStage } from "./components/DemoStage";
import { ManualTestBanner } from "./components/ManualTestBanner";
import { data } from "./explain/data";
import { useDemoStream } from "./stream/useDemoStream";

/** The demo alone on one screen (/live), for presenting; the full page explains it. */
export function Live() {
  const stream = useDemoStream();
  const patient = data.demo.subject.replace("sub-0", "").replace("sub-", "");
  return (
    <div className="page live">
      <main className="live-main" id="demo">
        <header className="live-head">
          <h1>
            <a href="/">Sixth-Finger BCI</a>
          </h1>
          <p>
            Patient {patient}&apos;s last two runs, which the model never trained on, played at real speed. Follow the
            three panels in order: what the patient is told, their brain signal, what the model reads.
          </p>
        </header>
        <DemoStage stream={stream} />
        <p className="live-foot">
          <a href="/">The whole project, explained</a>
        </p>
      </main>
      <ManualTestBanner />
    </div>
  );
}
