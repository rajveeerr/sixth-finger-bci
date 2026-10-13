// What the study found, in plain words, with the numbers from data.json: one answer for
// each of the five questions in "What we set out to find", in the same order.

import { data } from "./data";

export interface Finding {
  key: string;
  /** Which research question it answers (1 to 5); the questions list links here. */
  answers: number;
  question: string;
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
    value: data.leak.mean_leakfree,
    other: { value: data.leak.mean_replica, label: "tested the published way" },
    guess: 0.5,
    lead: "No: it was measured on trials the method had already seen.",
    answer: `The paper tested its method on trials that had also been used to build it, which flatters any method, like marking an exam with questions the student was given in advance. Tested properly, on trials kept apart, the same method tells the hand from the sixth finger ${pct(data.leak.mean_leakfree)} of the time. Guessing gets 50%.`,
    note: `One line per patient: the same method (CSP with LDA) scored the published way and properly. All ${data.leak.n_positive} of ${data.leak.subjects.length} fell. Our rebuild of the published way gives ${pct(data.leak.mean_replica)}; the paper reports 85 to 86%.`,
  },
  {
    key: "setup",
    answers: 2,
    question: "How long must a new patient practise before it works?",
    value: data.calibration.transfer[0].mean,
    other: { value: data.calibration.scratch[0].mean, label: "from scratch" },
    guess: 1 / 3,
    lead: "About 30 seconds, if the model starts from other patients.",
    answer: `A new patient first does a few practice trials so the model can adjust to them; each takes 14 s. Starting from a model built on the other patients, one practice trial of each movement (two trials, about 30 s) already gives ${pct(data.calibration.transfer[0].mean)} on the three choices. A model that starts from scratch gets ${pct(data.calibration.scratch[0].mean)} at that point, and needs about 5 minutes of practice to reach the same ${pct(data.calibration.transfer[0].mean)}.`,
    note: "Three choices (rest, hand, sixth finger), so guessing gets 33%. The shaded bands show the range the average could be in (95%).",
  },
  {
    key: "sixth",
    answers: 3,
    question: "Is the sixth finger a command of its own?",
    value: task("T1_ah_vs_sf").mean,
    other: { value: task("T3_sf_vs_rest").mean, label: "telling it from resting" },
    guess: 0.5,
    lead: "Not yet: the model sees that a movement is imagined, but barely which one.",
    answer: `Telling imagining the sixth finger from resting works, ${pct(task("T3_sf_vs_rest").mean)} of the time. Telling it from imagining the hand is only a little better than guessing, ${pct(task("T1_ah_vs_sf").mean)}: in the EEG the two look alike. A detector of any imagined movement did as well as one trained for the sixth finger. That is why the demo also offers an on/off switch.`,
    note: "One dot per patient, for each two-way choice: trained on the patient's first two runs, tested on the last two. The black line is the average.",
  },
  {
    key: "switch",
    answers: 4,
    question: "Would it work live, as a simple on/off switch?",
    value: data.switch.detection,
    lead: "Yes, about 2 times in 3.",
    answer: `Playing the recordings as if live, without telling the model when the cue came, the finger switches on about ${Math.round(data.switch.latency_s)} s after the patient starts imagining, with about ${Math.round(data.switch.false_per_minute)} false switch a minute while resting.`,
    note: "A reading every 0.5 s, smoothed as in the demo's continuous mode. Average of 22 patients.",
  },
  {
    key: "later",
    answers: 5,
    question: "Does a model still work on another day?",
    value: L.post.as_is.mean,
    other: { value: L.same_session, label: "on the day it was built" },
    guess: 1 / 3,
    lead: "Not on its own, but a few practice trials bring it back.",
    answer: `A model built in the first session drops from ${pct(L.same_session)} on that day to ${pct(L.post.as_is.mean)} two weeks later. Brain signals drift between days: the cap never sits in exactly the same place, the sensors touch the skin a little differently, the person feels different, and after therapy the brain itself may have changed. Five practice trials of each movement on the new day let the model re-align to the new signals, which brings it back to ${pct(L.post.re_setup.mean)}.`,
    note: `Three choices, so guessing gets 33%. ${L.post.as_is.n} patients came back after therapy and ${L.follow.as_is.n} a month later.`,
  },
];
