// What the study found, in plain words: one answer for each of the five questions in "What we
// set out to find", in the same order. The numbers come from data.json through the shared
// findings, and the tests' splits are the ones the other page draws.

import type { Point } from "../components/Chapter";
import { LEAK_POINTS } from "../explain/chapters/Published";
import { data, pct, pctRange } from "../explain/data";
import type { Split } from "../explain/figures/LearnTest";
import { about, AGAIN_K, AGAIN_MIN, FIRST, pctFine, PRACTICE_S, REACH, SCRATCH_MIN, SPLITS, timesWord } from "../explain/findings";
import { chapterName } from "./chapters";

export interface Answer {
  key: "leak" | "setup" | "sixth" | "switch" | "later";
  question: string;
  /** A few words for the dial that opens this answer. */
  short: string;
  /** What the dial's number means, so the five can be read side by side. */
  scale: string;
  /** The main score, 0 to 1, and the one it is compared with. */
  value: number;
  other?: number;
  /** What blind guessing would score (none for the switch, which has no classes to guess). */
  guess?: number;
  /** The short answer, then the rest of it. */
  lead: string;
  answer?: string;
  /** Lines that each say one part of the answer under a few words. */
  lines?: Point[];
  points?: string[];
  /** How the evidence under the answer was measured. */
  note: string;
  /** How we reached the answer, in a few plain sentences, and where the page shows it. */
  how: string;
  split?: Split;
  see: { href: string; text: string }[];
}

const HALF = 0.5;
const THIRD = 1 / 3;
const C = data.calibration;
const L = data.later;
const S = data.sixth;
const W = data.switch;
const N = data.leak.subjects.length;
const S_END = C.scratch[C.scratch.length - 1];
const T_END = C.transfer[C.transfer.length - 1];

export const ANSWERS: Answer[] = [
  {
    key: "leak",
    question: `Is the published ${pct(data.leak.published[0])} real?`,
    short: "Tested fairly",
    scale: `guessing gets ${pct(HALF)}`,
    value: data.leak.mean_leakfree,
    other: data.leak.mean_replica,
    guess: HALF,
    lead: "No. The method had already seen the trials it was tested on; tested fairly, it is barely better than guessing.",
    lines: LEAK_POINTS,
    note: `Each grey line is one patient, scored the published way (left) and fairly (right); the black line is the average. All ${data.leak.n_positive} of ${N} scored lower when tested fairly. Our rebuild of the published way gives ${pct(data.leak.mean_replica)}, close to the paper's ${pctRange(data.leak.published)}.`,
    how: "We rebuilt the paper's method from its published code and scored it twice on the same patients and trials. Once as the paper did: the method's first step learned from all the trials, and only then were some set aside for testing. Once fairly: that step learned only from the trials used for learning. Nothing else changed.",
    see: [
      { href: "#data", text: `Problem 4 in ${chapterName("data")}, and how we spotted it` },
      { href: "#elsewhere", text: "The same mistake in other data" },
    ],
  },
  {
    key: "setup",
    question: "How much practice does a new patient need before the model works?",
    short: "A new patient",
    scale: `after ${PRACTICE_S} s; guessing ${pct(THIRD)}`,
    value: FIRST.mean,
    other: C.scratch[0].mean,
    guess: THIRD,
    lead: `About ${PRACTICE_S} seconds if the model has already learned from other patients; about ${SCRATCH_MIN} minutes if it starts from nothing.`,
    answer:
      "Every person's brain signals look a little different, so the model needs examples from each new patient. The patient imagines each movement a few times while the screen says which one; each example takes about 15 seconds.",
    points: [
      `Starting from nothing, the model needs ${REACH.k} examples of each movement (about ${SCRATCH_MIN} minutes) to be right ${pct(FIRST.mean)} of the time on the three choices. Guessing gets ${pct(THIRD)}.`,
      `Having already learned from the recordings of all the other patients, it is right ${pct(FIRST.mean)} of the time after ${FIRST.k} example of each (about ${PRACTICE_S} seconds).`,
      `With much more practice (about ${Math.round(S_END.minutes)} minutes), the model that started from nothing ends a little ahead, ${pct(S_END.mean)} against ${pct(T_END.mean)}. So learning from others saves time at the start; it does not make the model better in the end.`,
    ],
    note: `Three choices (rest, hand, sixth finger), so guessing gets ${pct(THIRD)}. The shaded bands show where the true average very likely lies, given only ${N} patients.`,
    how: `For each patient in turn we pretended they were new. Their first two runs supplied the practice trials (from ${C.scratch[0].k} to ${S_END.k} of each movement) and their last two runs the test, which the model never saw. "Already learned from other patients" means the model also learned from every recording of all the other patients, after each person's signals were shifted to a common centre so that the differences between people matter less.`,
    split: SPLITS.setup,
    see: [
      { href: "#journey", text: `A patient's path, visit by visit, in ${chapterName("use")}` },
      { href: "#recordings", text: `Runs and sessions, in ${chapterName("recordings")}` },
    ],
  },
  {
    key: "sixth",
    question: "Is the sixth finger a command of its own?",
    short: "Sixth finger or rest",
    scale: `guessing gets ${pct(HALF)}`,
    value: S.rest.mean,
    other: S.which.mean,
    guess: HALF,
    lead: 'Yes, as a switch that says "move now". Not yet as a command apart from the hand.',
    answer: `For most patients, imagining the sixth finger switches it on and resting leaves it off, read from the 14 sensors over the strip of brain that moves the body alone (all 40 give ${pct(S.rest.all_sensors)}). But imagining the hand switches it on too, so it picks up imagining a movement, not the finger itself. That is why the demo's finger moves for either.`,
    points: [
      `As a switch: right ${pct(S.rest.mean)} of the time, where guessing gets ${pct(HALF)}. ${S.rest.n_ge_80} of ${S.rest.n} patients are at 80% or more, and ${S.rest.n_ge_90} at 90% or more.`,
      `Acting only when sure, with how sure it must be set for each patient on runs 1 and 2 alone: right on ${pct(S.sure.acc)} of the decisions it takes, and it takes ${pct(S.sure.share)} of them. ${S.sure.n_ge_90} of ${S.sure.n} patients are at 90% or more. While the patient rests, it moves the finger by mistake ${pctFine(S.fires.rest.sure)} of the time.`,
      `It also switches on for ${pct(S.fires.hand.all)} of imagined hand movements, nearly as often as for the sixth finger (${pct(S.fires.finger.all)}). So it reads "imagining a movement", not "the finger".`,
      `Hand or sixth finger is much harder. The best model, a network that first learned from the other patients, is right ${pct(S.which.mean)} of the time. When it is sure it is right ${pct(S.which_sure.acc)} of the time, but it is sure on only ${pct(S.which_sure.share)} of trials.`,
      `Two movements of one hand are hard to tell apart even in healthy people: in ${S.healthy.people} of them, two grasps learned on one day were told apart a week later ${pctRange(S.healthy.pairs)} of the time, and three about ${pctRange(S.healthy.three)}, no better than guessing (${pct(HALF)} and ${pct(THIRD)}).`,
    ],
    note: `${S.rest.n} patients. Every model learned from the patient's first two runs and was tested on the last two, which it never saw.`,
    how: `For each patient, a simple model learned sixth finger or rest from runs 1 and 2, reading only the 14 sensors over the movement strip, and was tested on runs 3 and 4. How sure it must be before acting was also set on runs 1 and 2, learning on one and checking on the other. It never learned from an imagined hand movement, so the hand trials of runs 3 and 4 show how often one would switch it on. For hand or sixth finger, a network first learned from every recording of the other patients, then was adjusted to runs 1 and 2. Every method and setting was fixed before runs 3 and 4 were scored. The ${S.healthy.people} healthy people come from another public recording of imagined grasps, made on two days a week apart.`,
    split: SPLITS.sixth,
    see: [
      { href: "#demo", text: "The demo's finger, moved by one switch for either movement" },
      { href: "#answer-4", text: "How it does played as if live, in answer 4" },
      { href: "#model", text: `The model, in ${chapterName("model")}` },
      { href: "#brain", text: `What changes in the brain, in ${chapterName("brain")}` },
    ],
  },
  {
    key: "switch",
    question: "Would it work live, as a simple on/off switch?",
    short: "Live, as a switch",
    scale: "of imagined movements caught",
    value: W.detection,
    lead: `Partly. It catches ${pct(W.detection)} of imagined movements, but switches on by mistake too often for a device yet.`,
    answer: `Played as if live, without being told when the instruction came, the finger switches on about ${W.latency_s.toFixed(1)} s after the patient starts imagining: the model needs a few seconds of imagining inside the 4 s it reads. While the patient rests, it switches on by mistake about ${timesWord(W.false_per_minute)} a minute.`,
    points: [
      `A harder test than question 3's ${pct(S.rest.mean)}. There, the model read 4 s placed from the moment the instruction appeared, so it knew where to look; here it reads every half second and must find the start of imagining itself.`,
      "And another model: here it is the demo's, EEGNet learned from the patient alone on all 40 sensors. Question 3's switch is a simpler model on the 14 sensors over the movement strip.",
      `Played the same way, that simpler model did not do better. Taught to tell rest from any movement, it caught ${pct(W.central.detection)} against ${pct(W.detection)} here, though with fewer mistakes (${W.central.false_per_minute.toFixed(1)} a minute against ${W.false_per_minute.toFixed(1)}).`,
    ],
    note: `Every half second the model reads the newest 4 s and gives the chance that a movement is being imagined (hand and sixth finger added together). A running average steadies that chance; the finger turns on when it is above 60% twice in a row, and off when it falls below 45%. Average of ${W.n} patients.`,
    how: "We played each of a patient's last two runs to the model as one unbroken signal, a reading every half second, without telling it when the instructions came, and counted when the finger would have switched on: while the patient imagined (caught) or while they rested (a mistake).",
    split: SPLITS.live,
    see: [{ href: "#demo", text: "Try it in the demo, in continuous mode" }],
  },
  {
    key: "later",
    question: "Does a model still work on another day?",
    short: "Another day",
    scale: `unchanged; ${pct(L.post.re_setup.mean)} after adjusting`,
    value: L.post.as_is.mean,
    other: L.same_session,
    guess: THIRD,
    lead: "Not unchanged, but a few practice trials on the day bring it back.",
    answer: `Brain signals change between days: the cap sits a little differently, the person feels different, and therapy may change the brain. On the new day the patient does ${AGAIN_K} practice trials of each movement, ${about(AGAIN_MIN)}, and the model is adjusted to them. Two weeks later that takes it from ${pct(L.post.as_is.mean)} back to ${pct(L.post.re_setup.mean)}, close to the ${pct(L.same_session)} on the day it was built.`,
    note: `Three choices, so guessing gets ${pct(THIRD)}. ${L.post.as_is.n} patients two weeks later and ${L.follow.as_is.n} a month later, those with usable recordings of both days.`,
    how: `The model built from a patient's first session was tested unchanged on their sessions two weeks and a month later. Then it was adjusted to the new day with ${AGAIN_K} practice trials of each movement and tested again.`,
    split: SPLITS.later,
    see: [{ href: "#recordings", text: `The three sessions, in ${chapterName("recordings")}` }],
  },
];
