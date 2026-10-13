// What the study found, in plain words, with the numbers from data.json: one answer for
// each of the five questions in "What we set out to find", in the same order.

import { data } from "./data";

export interface Finding {
  key: string;
  /** Which research question it answers (1 to 5); the questions list links here. */
  answers: number;
  question: string;
  /** A few words for the dial that opens this answer. */
  short: string;
  /** The main score, 0 to 1. */
  value: number;
  /** A second score to compare with (the faulty test, or starting from scratch). */
  other?: { value: number; label: string };
  /** What blind guessing would score (none for the switch, which has no classes to guess). */
  guess?: number;
  /** The short answer, then the rest of it. */
  lead: string;
  answer: string;
  /** How the evidence under the answer was measured. */
  note: string;
}

const task = (key: string) => data.tasks.find((t) => t.key === key)!;
const pct = (v: number) => `${Math.round(v * 100)}%`;
const L = data.later;

export const FINDINGS: Finding[] = [
  {
    key: "leak",
    answers: 1,
    question: "Is the published 85% real?",
    short: "The published 85%",
    value: data.leak.mean_leakfree,
    other: { value: data.leak.mean_replica, label: "tested the published way" },
    guess: 0.5,
    lead: "No: it was measured on trials the method had already seen.",
    answer: `Like marking an exam with questions the student saw in advance. Tested on trials kept apart, the same method tells the hand from the sixth finger ${pct(data.leak.mean_leakfree)} of the time; guessing gets 50%.`,
    note: `One line per patient: the same method (CSP with LDA) scored the published way and properly. All ${data.leak.n_positive} of ${data.leak.subjects.length} fell. Our rebuild of the published way gives ${pct(data.leak.mean_replica)}; the paper reports 85 to 86%.`,
  },
  {
    key: "setup",
    answers: 2,
    question: "How long must a new patient practise before it works?",
    short: "A new patient",
    value: data.calibration.transfer[0].mean,
    other: { value: data.calibration.scratch[0].mean, label: "from scratch" },
    guess: 1 / 3,
    lead: "About 30 seconds, if the model starts from other patients.",
    answer: `One practice trial of each movement (about 30 s) gives ${pct(data.calibration.transfer[0].mean)} on the three choices. From scratch, the model gets ${pct(data.calibration.scratch[0].mean)} and needs about 5 minutes to catch up.`,
    note: "Three choices (rest, hand, sixth finger), so guessing gets 33%. The shaded bands show the range the average could be in (95%).",
  },
  {
    key: "sixth",
    answers: 3,
    question: "Is the sixth finger a command of its own?",
    short: "The sixth finger alone",
    value: task("T1_ah_vs_sf").mean,
    other: { value: task("T3_sf_vs_rest").mean, label: "telling it from resting" },
    guess: 0.5,
    lead: "Not yet: the model sees that a movement is imagined, but barely which one.",
    answer: `Against resting, ${pct(task("T3_sf_vs_rest").mean)}. Against imagining the hand, ${pct(task("T1_ah_vs_sf").mean)}, a little over guessing: in the EEG the two look alike, and a detector of any imagined movement did as well. So the demo also offers an on/off switch.`,
    note: "One dot per patient, for each two-way choice: trained on the patient's first two runs, tested on the last two. The black line is the average.",
  },
  {
    key: "switch",
    answers: 4,
    question: "Would it work live, as a simple on/off switch?",
    short: "Live, as a switch",
    value: data.switch.detection,
    lead: "Yes, about 2 times in 3.",
    answer: `Played as if live, without being told when the cue came, the finger switches on about ${Math.round(data.switch.latency_s)} s after the patient starts imagining, with about ${Math.round(data.switch.false_per_minute)} false switch a minute while resting.`,
    note: "A reading every 0.5 s, smoothed as in the demo's continuous mode. Average of 22 patients.",
  },
  {
    key: "later",
    answers: 5,
    question: "Does a model still work on another day?",
    short: "Another day",
    value: L.post.as_is.mean,
    other: { value: L.same_session, label: "on the day it was built" },
    guess: 1 / 3,
    lead: "Not on its own, but a few practice trials bring it back.",
    answer: `Brain signals drift between days: the cap sits a little differently, the person feels different, and therapy may change the brain. Five practice trials of each movement on the new day let the model re-align, from ${pct(L.post.as_is.mean)} back to ${pct(L.post.re_setup.mean)} two weeks later.`,
    note: `Three choices, so guessing gets 33%. ${L.post.as_is.n} patients came back after therapy and ${L.follow.as_is.n} a month later.`,
  },
];
