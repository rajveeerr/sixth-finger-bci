import { useEffect } from "react";
import { IntroHand } from "./components/IntroHand";
import { ManualTestBanner } from "./components/ManualTestBanner";
import { Added } from "./explain/chapters/Added";
import { OwnCommand } from "./explain/chapters/OwnCommand";
import { PatientUse } from "./explain/chapters/PatientUse";
import { Published } from "./explain/chapters/Published";
import { SeeItWork } from "./explain/chapters/SeeItWork";
import { TheData } from "./explain/chapters/TheData";
import { WhatIsThis } from "./explain/chapters/WhatIsThis";
import { QUESTIONS } from "./explain/questions";
import { useDemoStream } from "./stream/useDemoStream";

// The page is drawn after the browser looks for the address's #target, so go to it once it
// exists; and a link to something inside a closed fold opens the fold first.
function useLandOnLink() {
  useEffect(() => {
    const land = (always: boolean) => {
      const id = decodeURIComponent(window.location.hash.slice(1));
      const target = id ? document.getElementById(id) : null;
      if (!target) return;
      const fold = target.closest("details");
      if (fold && !fold.open) fold.open = true;
      else if (!always) return;
      target.scrollIntoView();
    };
    land(true);
    const onHash = () => land(false);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
}

export default function App() {
  const stream = useDemoStream();
  useLandOnLink();
  return (
    <div className="page" id="top">
      <main className="column">
        <header className="hero">
          <h1 className="hero-name">Sixth-Finger BCI</h1>
          <p className="hero-line">
            Imagine moving <em>a sixth finger</em>, and a model that reads the brain&apos;s signals moves it.
          </p>
          <IntroHand />
          <p className="hero-meta">
            A B.Tech minor project by Rajveer Singh, Vivek Yadav and Ansh Dahiya, guided by Dr. Suman Lata.
          </p>
        </header>

        <nav className="index" aria-labelledby="index-title">
          <h2 id="index-title" className="index-title">
            The questions this page answers, in order
          </h2>
          <ol>
            {QUESTIONS.map((q) => (
              <li key={q.id}>
                <a href={`#${q.id}`}>
                  <span className="index-ask">{q.ask}</span>
                  <span className="index-short">{q.short}</span>
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <WhatIsThis />
        <SeeItWork stream={stream} />
        <TheData />
        <Published />
        <OwnCommand />
        <PatientUse />
        <Added />

        <footer className="colophon">
          <p>
            Brain signals: Wang et al., Scientific Data 13, 1109 (2026), CC BY 4.0. The recordings played here were
            never used to train the model. A research prototype, not a medical device.
          </p>
          <p>B.Tech minor project by Rajveer Singh, Vivek Yadav and Ansh Dahiya, guided by Dr. Suman Lata.</p>
        </footer>
      </main>
      <ManualTestBanner />
    </div>
  );
}
