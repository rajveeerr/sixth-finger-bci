import { Chapter } from "./components/Chapter";
import { DemoStage } from "./components/DemoStage";
import { IntroHand } from "./components/IntroHand";
import { ManualTestBanner } from "./components/ManualTestBanner";
import { data, pct } from "./explain/data";
import { BciLoop } from "./explain/figures/BciLoop";
import { BrainRhythm } from "./explain/figures/BrainRhythm";
import { DataChecks } from "./explain/figures/DataChecks";
import { Elsewhere } from "./explain/figures/Elsewhere";
import { HeadMap } from "./explain/figures/HeadMap";
import { ModelFacts } from "./explain/figures/ModelFacts";
import { PatientSees } from "./explain/figures/PatientSees";
import { ResultsGauges } from "./explain/figures/Results";
import { Session } from "./explain/figures/Session";
import { SignalChain } from "./explain/figures/SignalChain";
import { PRACTICE_S, SCRATCH_MIN } from "./explain/findings";
import { LINKS } from "./explain/links";
import { CspTerm, CueTerm, DatasetRef, EegnetRef, EegTerm, ModelTerm, TherapyTerm } from "./explain/refs";
import { useDemoStream } from "./stream/useDemoStream";

export default function App() {
  const stream = useDemoStream();
  const patient = data.demo.subject.replace("sub-0", "").replace("sub-", "");
  return (
    <div className="page" id="top">
      <main className="column">
        <header className="hero">
          <h1 className="hero-name">Sixth-Finger BCI</h1>
          <p className="hero-line">
            Imagine moving <em>a sixth finger</em>, and a model that reads the brain&apos;s signals moves it.
          </p>
          <IntroHand />
          <p className="hero-text">
            After a stroke, many people can no longer use one hand well. A robotic sixth finger, worn at the wrist, can
            help it hold things, if it moves when the wearer wants. Many cannot press a button, so the wish is read from
            the brain through an <EegTerm /> cap: a <a href="#bci">brain-computer interface</a>, or BCI. We took
            recordings of 24 stroke patients imagining that movement, tested how well a computer{" "}
            <ModelTerm>model</ModelTerm> can learn to read them, and built a <a href="#demo">live demo</a> that reads
            one patient&apos;s signals as the recording plays.
          </p>
          <p className="hero-meta">
            A B.Tech minor project by Rajveer Singh, Vivek Yadav and Ansh Dahiya, guided by Dr. Suman Lata.
          </p>
        </header>

        <Chapter
          id="idea"
          n={1}
          title="The idea"
          lede={
            <p>
              A stroke damages the part of the brain that moves one side of the body, and months later many patients
              still cannot grip well with their <em>affected hand</em>. The robotic finger presses an object against the
              palm so the weak hand can still hold it. Here is the whole system, from the cap to the finger.
            </p>
          }
        >
          <SignalChain />
        </Chapter>

        <Chapter
          id="recordings"
          n={2}
          title="The recordings"
          lede={
            <>
              <p>
                We did not record anyone ourselves. The brain signals come from a study of 24 stroke patients in
                Tianjin, China, shared openly with its paper in 2026 (
                <DatasetRef>Wang et al., Scientific Data</DatasetRef>; the recordings are{" "}
                <a href={LINKS.data.url}>free to download</a>). Each patient wore an EEG cap and, trial after trial,
                rested and then, at a <CueTerm />, imagined moving either their affected hand or a sixth finger.
              </p>
              <p>
                A <b>trial</b> is one round of about 15 seconds. Twenty trials in a row make a <b>run</b>, and one visit
                of four runs is a <b>session</b>: 80 trials, half of each movement. Most patients came for three
                sessions, before and after <TherapyTerm>two weeks of therapy</TherapyTerm> and a month later.
              </p>
            </>
          }
        >
          <HeadMap />
          <PatientSees />
          <Session />
        </Chapter>

        <Chapter
          id="brain"
          n={3}
          title="What changes in the brain"
          lede={
            <p>
              The EEG is the tiny voltage the brain makes at the scalp, measured in millionths of a volt. Over the part
              that moves the hands, it carries a steady rhythm. When a person imagines moving, that rhythm gets smaller,
              and a model can learn to spot the change.
            </p>
          }
        >
          <BrainRhythm />
        </Chapter>

        <Chapter
          id="research"
          n={4}
          title="What we set out to find"
          lede={
            <p>
              Our main question: can a model that has already learned from other patients be set up for a new patient
              quickly, even for a movement the body never had? Every new user first gives the model some practice
              trials, and a stroke patient tires quickly, so fewer is better. Around it, five questions, each answered
              in <a href="#found">chapter 8</a>; what is new in all this is in <a href="#new">chapter 9</a>.
            </p>
          }
        >
          <ol className="questions">
            <li id="question-1">
              <h3>Is the published 85% real?</h3>
              <p>
                The paper that shared these recordings, <DatasetRef>Wang et al. (2026)</DatasetRef>, reports a standard
                method telling the hand from the sixth finger 85% of the time. <a href="#answer-1">Answer</a>
              </p>
            </li>
            <li id="question-2">
              <h3>How much practice does the model need from a new patient?</h3>
              <p>
                Learning from the new patient alone, or also from patients recorded before.{" "}
                <a href="#answer-2">Answer</a>
              </p>
            </li>
            <li id="question-3">
              <h3>Is the sixth finger a command of its own?</h3>
              <p>
                Or does the model only notice that <em>some</em> movement is being imagined?{" "}
                <a href="#answer-3">Answer</a>
              </p>
            </li>
            <li id="question-4">
              <h3>Would it work live, as a simple on/off switch?</h3>
              <p>
                In real use nobody tells the model when the <CueTerm /> came, so it must watch all the time and decide
                by itself when imagining starts. <a href="#answer-4">Answer</a>
              </p>
            </li>
            <li id="question-5">
              <h3>Does a model still work on another day?</h3>
              <p>
                Two weeks or a month later, after therapy. <a href="#answer-5">Answer</a>
              </p>
            </li>
          </ol>
          <details className="aside">
            <summary>How we kept the answers honest</summary>
            <p>
              We wrote these questions down, with how we would test each and what would count as a yes, before running
              the tests on all the patients, so the results could not bend the questions. Every test is on trials the
              model never saw while learning, and we checked the data first (<a href="#checks">chapter 5</a>).
            </p>
          </details>
        </Chapter>

        <Chapter
          id="checks"
          n={5}
          title="First, we checked the data"
          lede={
            <p>
              Before any test, we went through the recordings and the published analysis, looking for anything that
              could make a result look better than it is. We found four problems.
            </p>
          }
        >
          <DataChecks />
        </Chapter>

        <Chapter
          id="model"
          n={6}
          title="The model"
          lede={
            <p>
              The demo runs <EegnetRef />, a small neural network built for EEG. It is one model that chooses between
              three things at once: resting, imagining the hand, or imagining the sixth finger. For some questions we
              also trained simpler two-way versions, such as sixth finger or rest, and compared EEGNet with older
              methods such as <CspTerm />: tested fairly, EEGNet scored a little higher at telling the movements apart,
              and about the same at telling imagining from rest.
            </p>
          }
        >
          <ModelFacts />
        </Chapter>

        <Chapter
          id="demo"
          n={7}
          title="Watch it work"
          lede={
            <p>
              Patient {patient}&apos;s last two runs, which the model never trained on, play here at real speed. Follow
              the three panels in order: what the patient is told, their brain signal, what the model reads.
            </p>
          }
        >
          <DemoStage stream={stream} />
        </Chapter>

        <Chapter
          id="found"
          n={8}
          title="What we found"
          lede={
            <p>
              One answer to each question in <a href="#research">chapter 4</a>, with its evidence. Every test is on
              trials the model had <em>never seen</em>.
            </p>
          }
        >
          <ResultsGauges />
        </Chapter>

        <Chapter
          id="new"
          n={9}
          title="What this project adds"
          lede={
            <p>
              The accuracy did not go up: tested fairly, the hand and the sixth finger are told apart about 6 times in
              10, not 8 or 9. What we added is a fair measure of what these recordings can do, the reason the published
              number was higher, and how quickly a new patient could start.
            </p>
          }
        >
          <ol className="adds">
            <li>
              <h3>A fair test of a published result</h3>
              <p>
                We found the step that raised the paper&apos;s 85% and measured it: {pct(data.leak.mean_leakfree)}{" "}
                tested fairly, lower for every one of the {data.leak.subjects.length} patients (
                <a href="#answer-1">question 1</a>).
              </p>
            </li>
            <li>
              <h3>The same mistake, measured in other data</h3>
              <p>
                We repeated the check on two public datasets of imagined hand movements from healthy volunteers, and on
                EEG used to detect depression, where the same kind of leak is a known risk. It inflated the score every
                time (the figure below).
              </p>
            </li>
            <li>
              <h3>A check of the shared recordings</h3>
              <p>
                Four problems in the public data and its analysis, found by comparing every pair of runs and dealt with
                before any result was looked at (<a href="#checks">chapter 5</a>).
              </p>
            </li>
            <li>
              <h3>How fast a new patient can start, for a movement the body never had</h3>
              <p>
                {PRACTICE_S} seconds of practice with help from other patients, against {SCRATCH_MIN} minutes alone (
                <a href="#answer-2">question 2</a>).
              </p>
            </li>
            <li>
              <h3>What the sixth finger can be used as today</h3>
              <p>
                Not yet a command of its own, but an on/off switch, tested as if live, and what happens weeks later (
                <a href="#answer-3">questions 3 to 5</a>).
              </p>
            </li>
            <li>
              <h3>An open demo</h3>
              <p>
                The model runs on trials it never saw, on our server or, if that cannot be reached, in your browser; the
                code, the results and the data audit are public (<a href="#more">read more</a>).
              </p>
            </li>
          </ol>
          <Elsewhere />
        </Chapter>

        <Chapter
          id="bci"
          n={10}
          title="What a BCI is, and how it could be used"
          lede={
            <p>
              A brain-computer interface (BCI) turns brain signals into commands for a machine, without the body moving.
              It works as a loop: the person imagines, the machine moves, the person sees it move, and over time both
              get better at it. Sensors on the scalp, as here, are safe and cheap but blurry; sensors inside the skull
              are much sharper but need surgery.
            </p>
          }
        >
          <BciLoop />
          <ol className="uses">
            <li>
              <h3>Help a weak hand hold things</h3>
              <p>What this project aims at: a robotic sixth finger that grips when the wearer imagines it.</p>
            </li>
            <li>
              <h3>Help the brain recover</h3>
              <p>
                BCI therapy: the patient imagines a movement over and over, and each time the BCI picks it up, a robot
                or a screen answers with that movement. Showing the patient the result each time is being studied as a
                way to help the brain re-learn to move; 14 patients in this study had{" "}
                <TherapyTerm>two weeks of it</TherapyTerm>.
              </p>
            </li>
            <li>
              <h3>Other uses</h3>
              <p>Typing for people who cannot move or speak, steering a wheelchair, moving a prosthetic hand.</p>
            </li>
          </ol>
        </Chapter>

        <Chapter id="more" n={11} title="Read more">
          <ul className="links">
            {Object.values(LINKS).map((l) => (
              <li key={l.url}>
                <a href={l.url}>{l.title}</a>
                <span>{l.note}</span>
              </li>
            ))}
          </ul>
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
