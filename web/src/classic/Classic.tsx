import type { ReactNode } from "react";
import { DemoStage } from "../components/DemoStage";
import { IntroHand } from "../components/IntroHand";
import { ManualTestBanner } from "../components/ManualTestBanner";
import { HowBestChosen, HowEachTested, NumbersAnswer } from "../explain/chapters/Numbers";
import { ProblemSteps } from "../explain/chapters/Problem";
import { data, pct, pctRange } from "../explain/data";
import { DocList } from "../explain/Documents";
import { BenchLines, BenchTable } from "../explain/figures/Benchmark";
import { BrainRhythm, RhythmMeasured } from "../explain/figures/BrainRhythm";
import { DataChecks } from "../explain/figures/DataChecks";
import { Elsewhere } from "../explain/figures/Elsewhere";
import { HeadMap } from "../explain/figures/HeadMap";
import { Journey } from "../explain/figures/Journey";
import { ModelFacts } from "../explain/figures/ModelFacts";
import { PatientSees } from "../explain/figures/PatientSees";
import { Session } from "../explain/figures/Session";
import { SignalChain } from "../explain/figures/SignalChain";
import { LEAK_RANGE, PRACTICE_S, SCRATCH_MIN } from "../explain/findings";
import { LINKS } from "../explain/links";
import { CspTerm, CueTerm, DatasetRef, EegnetRef, EegTerm, ModelTerm, TherapyTerm } from "../explain/refs";
import { READ_TITLE } from "../explain/siteDocs";
import { useLandOnLink } from "../lib/landOnLink";
import { useDemoStream } from "../stream/useDemoStream";
import { Answers } from "./Answers";
import { ANSWERS, type Answer } from "./findings";
import { Chapter } from "./Chapter";
import { chapterName } from "./chapters";
import "./classic.css";

const S = data.sixth;
// Hand or sixth finger, tested fairly: from the published method to the best we found.
const TENTHS = [...new Set([data.leak.mean_leakfree, S.which.mean].map((v) => Math.round(v * 10)))].join(" to ");

/** What each research question asks for, under the question itself. */
const ASKED: Record<Answer["key"], ReactNode> = {
  leak: (
    <>
      The paper that shared these recordings, <DatasetRef>Wang et al. (2026)</DatasetRef>, reports a standard method
      telling the hand from the sixth finger {pct(data.leak.published[0])} of the time.
    </>
  ),
  setup: <>Starting from nothing, or from a model that has already learned from other patients.</>,
  sixth: (
    <>
      Or does the model only notice that <em>some</em> movement is being imagined?
    </>
  ),
  switch: (
    <>
      In real use nobody tells the model when the <CueTerm /> came, so it must watch all the time and decide by itself
      when imagining starts.
    </>
  ),
  later: <>Two weeks or a month later, after therapy.</>,
};

export function Classic() {
  const stream = useDemoStream();
  useLandOnLink();
  const patient = data.demo.subject.replace("sub-0", "").replace("sub-", "");
  return (
    <div className="page classic" id="top">
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
            the brain through an <EegTerm /> cap: a <a href="#use">brain-computer interface</a>, or BCI. We took
            recordings of 24 stroke patients imagining that movement, tested how well a computer{" "}
            <ModelTerm>model</ModelTerm> can learn to read them, and built a <a href="#demo">live demo</a> that reads
            one patient&apos;s signals as the recording plays.
          </p>
          <p className="hero-meta">
            A B.Tech minor project by Rajveer Singh, Vivek Yadav and Ansh Dahiya, guided by Dr. Suman Lata.
          </p>
          <p className="hero-read">
            <a href="#read">{READ_TITLE}</a>
          </p>
        </header>

        <Chapter
          id="idea"
          lede={
            <p>
              A stroke damages the part of the brain that moves one side of the body, and months later many patients
              still cannot grip well with their <em>affected hand</em>. The problem, and what a sixth finger does about
              it:
            </p>
          }
        >
          <ProblemSteps />
          <div className="chapter-lede">
            <p>Here is the whole system, from the cap to the finger.</p>
          </div>
          <SignalChain />
        </Chapter>

        <Chapter
          id="recordings"
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
          lede={
            <p>
              The EEG is the tiny voltage the brain makes at the scalp, measured in millionths of a volt. Over the part
              that moves the hands, it carries a steady rhythm. When a person imagines moving, that rhythm gets smaller,
              and a model can learn to spot the change.
            </p>
          }
        >
          <BrainRhythm />
          <RhythmMeasured />
        </Chapter>

        <Chapter
          id="research"
          lede={
            <p>
              Our main question: can a model that has already learned from other patients be set up for a new patient
              quickly, even for a movement the body never had? Every new user first gives the model some practice
              trials, and a stroke patient tires quickly, so fewer is better. Around it, five questions, each answered
              in <a href="#found">{chapterName("found")}</a>; every score side by side is in{" "}
              <a href="#numbers">{chapterName("numbers")}</a>, and what is new in all this in{" "}
              <a href="#new">{chapterName("new")}</a>.
            </p>
          }
        >
          <ol className="questions">
            {ANSWERS.map((a, i) => (
              <li key={a.key} id={`question-${i + 1}`}>
                <h3>{a.question}</h3>
                <p>
                  {ASKED[a.key]} <a href={`#answer-${i + 1}`}>Answer</a>
                </p>
              </li>
            ))}
          </ol>
          <details className="aside">
            <summary>How we kept the answers honest</summary>
            <p>
              We wrote these questions down, with how we would test each and what would count as a yes, before running
              the tests on all the patients, so the results could not bend the questions. Every test is on trials the
              model never saw while learning, and we checked the data first (<a href="#data">{chapterName("data")}</a>
              ).
            </p>
          </details>
        </Chapter>

        <Chapter
          id="data"
          lede={
            <p>
              Before any test, we went through the recordings and the published analysis, looking for anything that
              could make a result look better than it is. We found four problems: three in the shared recordings and one
              in how the paper tested its method. None was in our model; the fourth is why the paper&apos;s{" "}
              {pct(data.leak.published[0])} is too high.
            </p>
          }
        >
          <DataChecks />
        </Chapter>

        <Chapter
          id="model"
          lede={
            <p>
              The demo runs <EegnetRef />, a small neural network built for EEG. It is one model that chooses between
              three things at once: resting, imagining the hand, or imagining the sixth finger. For some questions we
              also trained simpler two-way versions, such as sixth finger or rest, and compared EEGNet with older
              methods such as <CspTerm />: tested fairly, EEGNet scored a little higher at telling the movements apart,
              but lower at telling imagining from rest, where a simpler method does best (
              <a href="#numbers">{chapterName("numbers")}</a>). In the demo, its two movements are added together into
              one switch: move or rest.
            </p>
          }
        >
          <ModelFacts />
        </Chapter>

        <Chapter
          id="demo"
          lede={
            <p>Patient {patient}&apos;s last two runs, which the model never trained on, played at real speed.</p>
          }
        >
          <DemoStage stream={stream} />
        </Chapter>

        <Chapter
          id="found"
          lede={
            <p>
              One answer to each question in <a href="#research">{chapterName("research")}</a>, with its evidence.
              Every test is on trials the model had <em>never seen</em>.
            </p>
          }
        >
          <Answers />
        </Chapter>

        <Chapter
          id="numbers"
          lede={
            <p>
              <NumbersAnswer />
            </p>
          }
        >
          <BenchTable />
          <BenchLines />
          <div className="how">
            <h4>How each was tested</h4>
            <HowEachTested />
            <h4>How the best were chosen</h4>
            <HowBestChosen />
          </div>
        </Chapter>

        <Chapter
          id="new"
          lede={
            <p>
              Telling the hand from the sixth finger did not get much better: tested fairly, it is right {TENTHS} times
              in 10, not 8 or 9. What we added is a fair measure of what these recordings can do, the reason the
              published number was higher, how quickly a new patient could start, and what the sixth finger can be used
              as today.
            </p>
          }
        >
          <ol className="adds">
            <li>
              <h3>A fair test of a published result</h3>
              <p>
                We found a step in the published analysis that inflates its {pct(data.leak.published[0])}, and measured
                it: {pct(data.leak.mean_leakfree)} tested fairly, lower for every one of the{" "}
                {data.leak.subjects.length} patients (<a href="#answer-1">question 1</a>).
              </p>
            </li>
            <li>
              <h3>The same mistake, measured in other data</h3>
              <p>
                We repeated the check on two public datasets of imagined hand movements from healthy volunteers. As a
                second, unrelated test, we also checked EEG studies that try to detect depression, where a related leak
                (the same person on both sides of the test) is a known risk; this project is not about depression. The
                leak raised the score in every dataset we checked, by {LEAK_RANGE[0]} to {LEAK_RANGE[1]} points (the
                figure below).
              </p>
            </li>
            <li>
              <h3>A check of the shared recordings</h3>
              <p>
                Three problems in the public data, found by comparing every pair of runs, and one in its analysis, all
                dealt with before any result was looked at (<a href="#data">{chapterName("data")}</a>).
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
                A switch that says &quot;move now&quot;, right {pct(S.rest.mean)} of the time and {pct(S.sure.acc)} when
                it acts only when sure, but not yet a command apart from the hand; also tested as if live, and weeks
                later (<a href="#answer-3">questions 3 to 5</a>).
              </p>
            </li>
            <li>
              <h3>A benchmark in healthy people</h3>
              <p>
                In {S.healthy.people} healthy people, two grasps of one hand, learned on one day and tested a week later,
                are told apart {pctRange(S.healthy.pairs)} of the time, about what guessing gets: two movements of one
                hand are hard to tell apart in anyone (<a href="#answer-3">question 3</a>).
              </p>
            </li>
            <li>
              <h3>An open demo</h3>
              <p>
                The model runs on trials it never saw, on our server or, if that cannot be reached, in your browser (
                <a href="#demo">{chapterName("demo")}</a>); the paper, the slides and the report are in{" "}
                <a href="#read">{chapterName("read")}</a>.
              </p>
            </li>
          </ol>
          <Elsewhere />
        </Chapter>

        <Chapter
          id="use"
          lede={
            <>
              <p>
                A brain-computer interface (BCI) turns brain signals into commands for a machine, without the body
                moving. It works as a loop: the person imagines, the machine moves, the person sees it move, and over
                time both get better at it. Sensors on the scalp, as here, are safe and cheap but blurry; sensors inside
                the skull are much sharper but need surgery.
              </p>
              <p>
                Below, a patient&apos;s visits, with each part of a real system drawn once: solid where this project
                built it, dashed where a real system still needs it. The model, its server and this page are built; the
                live headset, its bridge and the finger are not.
              </p>
            </>
          }
        >
          <Journey />
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

        <Chapter id="read">
          <DocList text={{ slides: "The talk for the final evaluation, with backup slides." }} />
        </Chapter>

        <Chapter id="more">
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
