import { Chapter } from "./components/Chapter";
import { Controls } from "./components/Controls";
import { EEGPanel } from "./components/EEGPanel";
import { IntroHand } from "./components/IntroHand";
import { ManualTestBanner } from "./components/ManualTestBanner";
import { ModeBadge } from "./components/ModeBadge";
import { PredictionCard } from "./components/PredictionCard";
import { Told } from "./components/Told";
import { data, pct } from "./explain/data";
import { BciLoop } from "./explain/figures/BciLoop";
import { BrainRhythm } from "./explain/figures/BrainRhythm";
import { DataChecks } from "./explain/figures/DataChecks";
import { HeadMap } from "./explain/figures/HeadMap";
import { ModelFacts } from "./explain/figures/ModelFacts";
import { PatientSees } from "./explain/figures/PatientSees";
import { RealLimb } from "./explain/figures/RealLimb";
import { ResultsGauges } from "./explain/figures/Results";
import { Session } from "./explain/figures/Session";
import { SignalChain } from "./explain/figures/SignalChain";
import { LINKS } from "./explain/links";
import { CspTerm, CueTerm, DatasetRef, EegnetRef, TherapyTerm } from "./explain/refs";
import { useDemo } from "./store";
import { useDemoStream } from "./stream/useDemoStream";

const task = (key: string) => data.tasks.find((t) => t.key === key)!;

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
              After a stroke, many people can no longer use one hand well. One idea is a{" "}
              <mark>robotic sixth finger</mark>, worn on the hand, that helps it hold things, controlled{" "}
              <mark>just by imagining the movement</mark>, which an EEG cap picks up: a brain-computer interface, or{" "}
              <a href="#bci">BCI</a>. We took recordings of 24 stroke patients doing exactly that, asked how well and
              how quickly a computer can learn to read them, and built the <a href="#demo">demo</a> on this page, where
              a model reads one patient&apos;s signals as they play.
            </p>
            <p className="intro-meta">
              A B.Tech minor project by Rajveer Singh, Vivek Yadav and Ansh Dahiya, guided by Dr. Suman Lata.{" "}
              <a href="#demo">Go to the live demo</a>
            </p>
          </div>
        </header>

        <section className="short" aria-labelledby="short-title">
          <h2 id="short-title">In short</h2>
          <ul>
            <li>
              Telling <mark>imagining the sixth finger from resting works</mark>: right about 3 times in 4 (
              {pct(task("T3_sf_vs_rest").mean)}).
            </li>
            <li>
              Telling <mark>which movement</mark> was imagined, the hand or the sixth finger, is{" "}
              <mark>barely better than guessing</mark> ({pct(task("T1_ah_vs_sf").mean)}), so for now the finger works
              best as an on/off switch.
            </li>
            <li>
              The <mark>published 85% came from a testing mistake</mark>; tested fairly, the same method gets{" "}
              {pct(data.leak.mean_leakfree)}.
            </li>
            <li>
              Starting from other patients, a new patient needs <mark>30 seconds of practice instead of 5 minutes</mark>
              .
            </li>
          </ul>
        </section>

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
                The <a href="#top">robotic finger at the top of this page</a> is worn beside the little finger. It bends
                toward the palm and presses an object against it, so the weak hand can still hold things. To help, it
                has to move when the wearer wants it to, and the wearer may not be able to press a button. So the wish
                is <mark>read from the brain</mark>: imagining the movement is enough.
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
                We did not record anyone ourselves. The brain signals come from a study of{" "}
                <mark>24 stroke patients</mark> in Tianjin, China, shared openly with its paper in 2026 (
                <DatasetRef>Wang et al., Scientific Data</DatasetRef>; the recordings are{" "}
                <a href={LINKS.data.url}>free to download</a>). Each patient wore an EEG cap and, trial after trial,
                rested and then, at a <CueTerm />, imagined moving either their affected hand or a sixth finger.
              </p>
              <p>
                A <b>trial</b> is one 14-second round. Twenty trials in a row make a <b>run</b>, and one visit of four
                runs is a <b>session</b>: 80 trials, half of each movement. Most patients came for three sessions,
                before and after <TherapyTerm>two weeks of therapy</TherapyTerm> and a month later.
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
              that moves the hands, it carries a steady rhythm. When a person imagines moving,{" "}
              <mark>that rhythm gets smaller</mark>, and a model can learn to spot the change.
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
            <>
              <p>
                Our main question:{" "}
                <mark>
                  can a model that has already learned from other patients be set up for a new patient quickly
                </mark>
                , even for a movement the body never had? Every new user has to give the model some practice trials
                first, and a stroke patient tires quickly, so fewer is better.
              </p>
              <p>
                Around it, five questions. Each is answered in <a href="#found">chapter 8</a>.
              </p>
            </>
          }
        >
          <ol className="questions">
            <li id="question-1">
              <h3>Is the published 85% real?</h3>
              <p>
                The paper that shared these recordings, <DatasetRef>Wang et al. (2026)</DatasetRef>, reports that a
                standard method tells imagining the hand from imagining the sixth finger{" "}
                <mark>about 85% of the time</mark>. Before building on that, we checked how it was tested.{" "}
                <a href="#answer-1">Answer</a>
              </p>
            </li>
            <li id="question-2">
              <h3>How long must a new patient practise before it works?</h3>
              <p>
                Does starting from a model built on other patients cut the practice a new patient needs, compared with
                starting from scratch? <a href="#answer-2">Answer</a>
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
                In real use nobody tells the model when the <CueTerm /> came; it has to notice by itself.{" "}
                <a href="#answer-4">Answer</a>
              </p>
            </li>
            <li id="question-5">
              <h3>Does a model still work on another day?</h3>
              <p>
                A patient comes back days or weeks later, after therapy. <a href="#answer-5">Answer</a>
              </p>
            </li>
          </ol>
          <p className="chapter-after">
            We wrote these questions down, with how we would test each and what would count as a yes,{" "}
            <mark>before running the tests on all the patients</mark>, so the results could not bend the questions. We
            tested only on trials the model had never seen, and checked the data first.
          </p>
        </Chapter>

        <Chapter
          id="checks"
          n={5}
          title="First, we checked the data"
          lede={
            <p>
              Before any test, we went through the recordings and the published analysis, looking for anything that
              could make a result look better than it is. <mark>We found four problems.</mark>
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
              three things at once: <mark>resting, imagining the hand, or imagining the sixth finger</mark>. For some
              questions we also trained simpler two-way versions, such as sixth finger or rest, and compared EEGNet with
              older methods such as <CspTerm />.
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
              Patient {patient}&apos;s last two runs, which the model never trained on, play here at real speed. Read
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
            <dl className="modes">
              <div>
                <dt>Three choices or on/off switch</dt>
                <dd>
                  Three choices shows the model as trained: rest, hand or sixth finger. The on/off switch bends the
                  finger for any imagined movement, the use our results support.
                </dd>
              </div>
              <div>
                <dt>Per trial or continuous</dt>
                <dd>
                  Per trial reads the two 4 s pieces of each trial, timed from the cue, as the study did. Continuous
                  reads the newest 4 s every half second without being told when the cue came, as a live system would.
                  It makes more mistakes; try it with the on/off switch.
                </dd>
              </div>
            </dl>
          </div>
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
          id="bci"
          n={9}
          title="What a BCI is, and how it could be used"
          lede={
            <>
              <p>
                A <mark>brain-computer interface</mark> (BCI) turns brain signals into commands for a machine, without
                the body moving. It works as a loop: the person imagines, the machine moves, the person sees it move,
                and over time both get better at it.
              </p>
              <p>
                The signals can be picked up by sensors on the scalp, as here, which is safe and cheap but blurry, or by
                sensors placed inside the skull, which are much sharper but need surgery.
              </p>
            </>
          }
        >
          <BciLoop />
          <ol className="uses">
            <li>
              <h3>Help a weak hand hold things</h3>
              <p>
                What this project aims at: a robotic sixth finger that grips when the wearer imagines it, for someone
                whose own fingers no longer close well after a stroke.
              </p>
            </li>
            <li>
              <h3>Help the brain recover</h3>
              <p>
                Practising with a BCI that answers imagined movement is being studied as a stroke therapy; the patients
                in this study who had <TherapyTerm>BCI training</TherapyTerm> did exactly that.
              </p>
            </li>
            <li>
              <h3>Other uses</h3>
              <p>
                Typing for people who cannot move or speak, steering a wheelchair, and moving a prosthetic hand all use
                the same loop.
              </p>
            </li>
          </ol>
          <RealLimb />
        </Chapter>

        <Chapter id="more" n={10} title="Read more">
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
