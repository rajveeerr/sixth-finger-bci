// What the study found, in plain words, with the numbers from data.json: one answer for
// each of the five questions in "What we set out to find", in the same order.

import { data } from "./data";
import type { Split } from "./figures/LearnTest";

export interface Finding {
  key: string;
  /** Which research question it answers (1 to 5); the questions list links here. */
  answers: number;
  question: string;
  /** A few words for the dial that opens this answer. */
  short: string;
  /** What the dial's number means, so the five can be read side by side. */
  scale: string;
  /** The main score, 0 to 1. */
  value: number;
  /** A second score to compare with (the faulty test, or starting from scratch). */
  other?: { value: number; label: string };
  /** What blind guessing would score (none for the switch, which has no classes to guess). */
  guess?: number;
  /** The short answer, then the rest of it. */
  lead: string;
  answer: string;
  /** The answer's steps, when a list says it more plainly than a paragraph. */
  points?: string[];
  /** How the evidence under the answer was measured. */
  note: string;
  /** How we reached the answer, in a few plain sentences, and where the page shows it. */
  how: string;
  /** What the model learned from and what it was tested on, drawn above the "how". */
  split?: Split;
  see: { href: string; text: string }[];
}

const task = (key: string) => data.tasks.find((t) => t.key === key)!;
const pct = (v: number) => `${Math.round(v * 100)}%`;
const L = data.later;
const T0 = data.calibration.transfer[0];
// When starting from scratch first does as well as one trial of each movement from other patients.
const scratchReach = data.calibration.scratch.find((p) => p.mean >= T0.mean - 0.005)?.minutes ?? NaN;
/** Seconds of practice, to the nearest ten. */
export const PRACTICE_S = Math.round((T0.minutes * 60) / 10) * 10;
/** Minutes from scratch, to the nearest minute. */
export const SCRATCH_MIN = Math.round(scratchReach);
const S_END = data.calibration.scratch[data.calibration.scratch.length - 1];
const T_END = data.calibration.transfer[data.calibration.transfer.length - 1];
/** Practice trials of each movement the patient's own model needs to match that. */
export const SCRATCH_K = data.calibration.scratch.find((p) => p.minutes === scratchReach)?.k ?? NaN;

export const FINDINGS: Finding[] = [
  {
    key: "leak",
    answers: 1,
    question: "Is the published 85% real?",
    short: "Tested fairly",
    scale: "guessing gets 50%",
    value: data.leak.mean_leakfree,
    other: { value: data.leak.mean_replica, label: "tested the published way" },
    guess: 0.5,
    lead: "No. The method had already seen the trials it was tested on.",
    answer: `The 85% comes from the paper that shared these recordings: it reports that a standard method (CSP with LDA) tells imagining the hand from imagining the sixth finger ${pct(data.leak.published[0])} to ${pct(data.leak.published[1])} of the time.`,
    points: [
      "The catch: the method's first step, CSP, learns from labelled trials how to combine the 40 sensors. In the paper's analysis code it learned from every trial of a session, including the ones it was later tested on. It is like marking an exam whose questions the student saw in advance.",
      `Tested fairly, with that step learning only from the trials used for learning, the same method gets ${pct(data.leak.mean_leakfree)}, where guessing gets 50%. Every one of the ${data.leak.subjects.length} patients scored lower.`,
      "Nothing else differs between the two tests: the same patients, the same trials, the same method, and the same test trials each time.",
    ],
    note: `Each grey line is one patient, scored the published way (left) and fairly (right); the black line is the average. All ${data.leak.n_positive} of ${data.leak.subjects.length} scored lower when tested fairly. Our rebuild of the published way gives ${pct(data.leak.mean_replica)}, close to the paper's 85 to 86%.`,
    how: "We rebuilt the paper's method from its published code and scored it twice on the same patients and trials. Once as the paper did: the method's first step learned from all the trials, and only then were some set aside for testing. Once fairly: that step learned only from the trials used for learning. Nothing else changed.",
    see: [
      { href: "#checks", text: "Problem 4 in chapter 5, and how we spotted it" },
      { href: "#elsewhere", text: "The same mistake in other data" },
    ],
  },
  {
    key: "setup",
    answers: 2,
    question: "How much practice does a new patient need before the model works?",
    short: "A new patient",
    scale: "after 30 s; guessing 33%",
    value: data.calibration.transfer[0].mean,
    other: { value: data.calibration.scratch[0].mean, label: "starting from nothing" },
    guess: 1 / 3,
    lead: `About ${PRACTICE_S} seconds if the model has already learned from other patients; about ${SCRATCH_MIN} minutes if it starts from nothing.`,
    answer:
      "Every person's brain signals look a little different, so the model needs examples from each new patient. The patient imagines each movement a few times while the screen says which one; each example takes about 15 seconds.",
    points: [
      `Starting from nothing, the model needs ${SCRATCH_K} examples of each movement (about ${SCRATCH_MIN} minutes) to be right ${pct(T0.mean)} of the time on the three choices. Guessing gets 33%.`,
      `Having already learned from the recordings of all the other patients, it is right ${pct(T0.mean)} of the time after 1 example of each (about ${PRACTICE_S} seconds).`,
      `With much more practice (about ${Math.round(S_END.minutes)} minutes), the model that started from nothing ends a little ahead, ${pct(S_END.mean)} against ${pct(T_END.mean)}. So learning from others saves time at the start; it does not make the model better in the end.`,
    ],
    note: "Three choices (rest, hand, sixth finger), so guessing gets 33%. The shaded bands show where the true average very likely lies, given only 22 patients.",
    how: `For each patient in turn we pretended they were new. Their first two runs supplied the practice trials (from 1 to 20 of each movement) and their last two runs the test, which the model never saw. "Already learned from other patients" means the model also learned from every recording of all the other patients, after each person's signals were shifted to a common centre so that the differences between people matter less.`,
    split: {
      label: "What the model learned from and what it was tested on, for each patient in turn",
      rows: [
        {
          title: "Other patients",
          note: "skipped when starting from nothing",
          many: true,
          runs: ["learn", "learn", "learn", "learn"],
          learns: "learns from all their sessions, shifted to a common centre",
          sometimes: true,
        },
        {
          title: "The new patient",
          note: "session 1",
          runs: ["pick", "pick", "test", "test"],
          picked: 6,
          learns: "learns from 1 to 20 trials of each movement in runs 1 and 2",
          tested: "tested on runs 3 and 4",
        },
      ],
      note: "Dark squares in runs 1 and 2: one example of the practice trials, which were picked at random.",
    },
    see: [
      { href: "#setup-flow", text: "The new patient's steps, above" },
      { href: "#recordings", text: "Runs and sessions, in chapter 2" },
    ],
  },
  {
    key: "sixth",
    answers: 3,
    question: "Is the sixth finger a command of its own?",
    short: "Sixth finger or hand",
    scale: "guessing gets 50%",
    value: task("T1_ah_vs_sf").mean,
    other: { value: task("T3_sf_vs_rest").mean, label: "telling it from resting" },
    guess: 0.5,
    lead: "Not yet. The model tells imagining from resting, but barely which movement.",
    answer: `Imagining the sixth finger is told apart from resting ${pct(task("T3_sf_vs_rest").mean)} of the time. Some of that may not be the imagining: during rest the screen shows a cross and during imagining a picture, and sensors at the back of the head, over the parts that handle sight, can also tell the two apart. Told apart from imagining the hand, ${pct(task("T1_ah_vs_sf").mean)}, a little over guessing: the rhythm drops by about the same amount for both. A model trained only on imagining the hand picked out sixth-finger imagining about as well as one trained on the sixth finger itself. So the demo also offers an on/off switch.`,
    note: "One dot per patient, for each two-way choice: trained on the patient's first two runs, tested on the last two. The black line is the average.",
    how: "For each patient, a model learned each two-way choice from the first two runs and was tested on the last two. A model trained to find imagined hand movements was then asked to find imagined sixth-finger movements, and compared with a model trained on those.",
    split: {
      label: "What each model learned from and what it was tested on",
      rows: [
        {
          title: "Each patient",
          note: "session 1, each two-way choice",
          runs: ["learn", "learn", "test", "test"],
          learns: "learns from runs 1 and 2",
          tested: "tested on runs 3 and 4",
        },
      ],
    },
    see: [
      { href: "#model", text: "The model, in chapter 6" },
      { href: "#brain", text: "What changes in the brain, in chapter 3" },
    ],
  },
  {
    key: "switch",
    answers: 4,
    question: "Would it work live, as a simple on/off switch?",
    short: "Live, as a switch",
    scale: "of imagining periods caught",
    value: data.switch.detection,
    lead: "Partly. It catches about 2 in 3 imagined movements, but switches on by mistake too often for a device yet.",
    answer: `Played as if live, without being told when the instruction came, the finger switches on about ${Math.round(data.switch.latency_s)} s after the patient starts imagining: the model needs a few seconds of imagining inside the 4 s it reads. While the patient rests, it switches on by mistake about ${Math.round(data.switch.false_per_minute)} time a minute.`,
    note: `Every half second the model reads the newest 4 s and gives the chance that a movement is being imagined (hand and sixth finger added together). A running average steadies that chance; the finger turns on when it is above 60% twice in a row, and off when it falls below 45%. Average of ${data.switch.n} patients.`,
    how: "We played each of a patient's last two runs to the model as one unbroken signal, a reading every half second, without telling it when the instructions came, and counted when the finger would have switched on: while the patient imagined (caught) or while they rested (a mistake).",
    split: {
      label: "What the model learned from and what it was played",
      rows: [
        {
          title: "Each patient",
          note: "session 1",
          runs: ["learn", "learn", "replay", "replay"],
          learns: "learns from runs 1 and 2",
          tested: "runs 3 and 4 each played start to end, a reading every half second",
        },
      ],
    },
    see: [{ href: "#demo", text: "Try it in the demo: continuous mode with the on/off switch" }],
  },
  {
    key: "later",
    answers: 5,
    question: "Does a model still work on another day?",
    short: "Another day",
    scale: `unchanged; ${pct(L.post.re_setup.mean)} after adjusting`,
    value: L.post.as_is.mean,
    other: { value: L.same_session, label: "on the day it was built" },
    guess: 1 / 3,
    lead: "Not unchanged, but a few practice trials on the day bring it back.",
    answer: `Brain signals change between days: the cap sits a little differently, the person feels different, and therapy may change the brain. On the new day the patient does 5 practice trials of each movement, a little over 2 minutes, and the model is adjusted to them. Two weeks later that takes it from ${pct(L.post.as_is.mean)} back to ${pct(L.post.re_setup.mean)}, close to the ${pct(L.same_session)} on the day it was built.`,
    note: `Three choices, so guessing gets 33%. ${L.post.as_is.n} patients two weeks later and ${L.follow.as_is.n} a month later, those with usable recordings of both days.`,
    how: "The model built from a patient's first session was tested unchanged on their sessions two weeks and a month later. Then it was adjusted to the new day with 5 practice trials of each movement and tested again.",
    split: {
      label: "What the first session's model learned from and what it was tested on, weeks later",
      rows: [
        {
          title: "Session 1",
          note: "the model is built",
          runs: ["learn", "learn", "learn", "learn"],
          learns: "learns from all four runs",
        },
        {
          title: "Sessions 2 and 3",
          note: "two weeks and a month later",
          runs: ["pick", "pick", "test", "test"],
          picked: 10,
          learns: "only when adjusted: 5 trials of each movement in runs 1 and 2",
          sometimes: true,
          tested: "tested on runs 3 and 4",
        },
      ],
      note: "Dark squares in runs 1 and 2: one example of a random pick. The score on the day it was built uses the usual split instead: it learns from runs 1 and 2 of session 1 and is tested on its runs 3 and 4.",
    },
    see: [{ href: "#recordings", text: "The three sessions, in chapter 2" }],
  },
];
