import { Chapter } from "./components/Chapter";
import { Controls } from "./components/Controls";
import { IntroHand } from "./components/IntroHand";
import { EEGPanel } from "./components/EEGPanel";
import { ManualTestBanner } from "./components/ManualTestBanner";
import { ModeBadge } from "./components/ModeBadge";
import { PredictionCard } from "./components/PredictionCard";
import { Told } from "./components/Told";
import { data } from "./explain/data";
import { BrainRhythm } from "./explain/figures/BrainRhythm";
import { HeadMap } from "./explain/figures/HeadMap";
import { ModelFacts } from "./explain/figures/ModelFacts";
import { PatientSees } from "./explain/figures/PatientSees";
import { RealLimb } from "./explain/figures/RealLimb";
import { ResultsGauges } from "./explain/figures/Results";
import { SignalChain } from "./explain/figures/SignalChain";
import { useDemo } from "./store";
import { useDemoStream } from "./stream/useDemoStream";

export default function App() {
  const stream = useDemoStream();
  const source = useDemo((s) => s.source);
  const synthetic = useDemo((s) => s.synthetic);
  const error = useDemo((s) => s.error);
  const patient = data.demo.subject.replace("sub-0", "").replace("sub-", "");
  return (
    <div className="page" id="top">
      <main className="column">
        <header className="intro bleed">
          <div className="intro-top">
            <h1 className="intro-title">Sixth-Finger BCI</h1>
            <p className="lede">
              Imagine moving <em>a sixth finger</em>, and a model that reads the brain&apos;s signals moves it.
            </p>
          </div>
          <IntroHand />
          <div className="intro-body">
            <p className="intro-text">
              After a stroke, many people can no longer use one hand well. One idea is a robotic sixth finger, worn on
              the hand, that helps it hold things. The wearer would control it just by imagining the movement, picked up
              by an EEG cap. We took recordings of 24 stroke patients doing exactly that, tested how well a computer can
              read them, and built the demo on this page, where a model reads one patient&apos;s signals as they play
              and moves the finger.
            </p>
            <p className="intro-meta">
              A B.Tech minor project by Rajveer Singh, Vivek Yadav and Ansh Dahiya, guided by Dr. Suman Lata.{" "}
              <a href="#demo">Go to the live demo</a>
            </p>
          </div>
        </header>

        <SignalChain />

        <Chapter
          id="idea"
          n={1}
          title="The idea"
          lede={
            <>
              <p>
                A stroke damages the part of the brain that moves one side of the body. Months later, many patients
                still cannot grip well with their <em>affected hand</em>.
              </p>
              <p>
                A supernumerary, or extra, robotic finger, the one drawn at the top of this page, is worn on the side of
                the hand. It bends toward the palm and presses an object against it, so the weak hand can still hold
                things. To help, it has to move when the wearer wants it to. Here that wish is read from the brain:
                imagining the movement is enough, and no muscle has to move.
              </p>
            </>
          }
        />

        <Chapter
          id="recordings"
          n={2}
          title="The recordings"
          lede={
            <>
              <p>
                We did not record anyone ourselves. The brain signals come from a study of 24 stroke patients in
                Tianjin, China, published openly in 2026 (Wang et al., Scientific Data). Each patient wore an EEG cap
                and, trial after trial, rested and then imagined moving either their affected hand or a sixth finger.
              </p>
              <p>
                A session has 80 trials. Most patients were recorded three times: before two weeks of training, after
                it, and a month later.
              </p>
            </>
          }
        >
          <HeadMap />
          <PatientSees />
        </Chapter>

        <Chapter
          id="brain"
          n={3}
          title="What changes in the brain"
          lede={
            <p>
              The EEG is the tiny voltage the brain makes at the scalp. Over the part that moves the hands, it carries a
              steady rhythm. When a person imagines moving, that rhythm gets <em>smaller</em>, and a model can learn to
              spot the change.
            </p>
          }
        >
          <BrainRhythm />
        </Chapter>

        <Chapter
          id="model"
          n={4}
          title="The model"
          lede={
            <p>
              The model is EEGNet, a small network built for EEG. It is trained on one patient&apos;s first recordings
              and tested on their later ones, which it has <em>never seen</em>. Every 4 seconds it says which of three
              things the patient is doing: resting, imagining the hand, or imagining the sixth finger.
            </p>
          }
        >
          <ModelFacts />
        </Chapter>

        <Chapter
          id="demo"
          n={5}
          title="Watch it work"
          lede={
            <p>
              Patient {patient}&apos;s later recordings, which the model never trained on, play here at real speed. Read
              left to right.
            </p>
          }
        >
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
          </div>
        </Chapter>

        <Chapter
          id="found"
          n={6}
          title="What we found"
          lede={
            <p>
              We tested the model on 22 patients, always on recordings it had <em>never seen</em>. Five questions, each
              with a plain answer and the evidence under it.
            </p>
          }
        >
          <ResultsGauges />
        </Chapter>

        <Chapter
          id="limb"
          n={7}
          title="Toward a real limb"
          lede={
            <p>
              The brain signals, the model and the commands here are real. Only the last two steps, the motor and the
              finger, are <em>drawn instead of built</em>.
            </p>
          }
        >
          <RealLimb />
        </Chapter>

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
