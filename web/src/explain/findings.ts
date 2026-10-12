// What the study found, in plain words, with the numbers from data.json, in the order of
// the questions in "What we set out to find".

import { data } from "./data";

export interface Finding {
  key: string;
  /** Which of the research questions it answers (1 to 4). */
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
    question: "Was the published 85% real?",
    value: data.leak.mean_leakfree,
    other: { value: data.leak.mean_replica, label: "tested the published way" },
    guess: 0.5,
    lead: "No.",
    answer: `It came from a testing mistake: the trials used to test the method had already been used to build it. Tested fairly, the same method tells the hand from the sixth finger ${pct(data.leak.mean_leakfree)} of the time, near guessing.`,
    note: `One line per patient, the same method (CSP with LDA) scored both ways: all ${data.leak.n_positive} of ${data.leak.subjects.length} fell.`,
  },
  {
    key: "moving",
    answers: 1,
    question: "Can it tell imagining the sixth finger from resting?",
    value: task("T3_sf_vs_rest").mean,
    guess: 0.5,
    lead: "Yes, about 3 times in 4.",
    answer: "When a patient imagines the movement, their brain signal shows it clearly enough to read.",
    note: "One dot per patient: a model trained on their first two runs, tested on the last two. The line is the average.",
  },
  {
    key: "which",
    answers: 3,
    question: "Can it tell which movement: the hand or the sixth finger?",
    value: task("T1_ah_vs_sf").mean,
    guess: 0.5,
    lead: "Only a little better than guessing.",
    answer:
      "Imagining the hand and imagining the sixth finger look alike in the EEG. A detector of any imagined movement did as well as one trained for the sixth finger, so we cannot claim the sixth finger is a separate command yet. That is why the demo also offers an on/off switch.",
    note: "One dot per patient, tested the same way.",
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
    key: "switch",
    answers: 4,
    question: "Would it work live, as a simple on/off switch?",
    value: data.switch.detection,
    lead: "Yes, about 2 times in 3.",
    answer: `Playing the recordings as if live, without being told when the cue came, the finger switches on about ${Math.round(data.switch.latency_s)} s after the patient starts imagining, with about ${Math.round(data.switch.false_per_minute)} false switch a minute while resting.`,
    note: "A reading every 0.5 s, smoothed as in the demo's continuous mode. Average of 22 patients.",
  },
  {
    key: "later",
    answers: 4,
    question: "Does a model still work weeks later?",
    value: L.post.as_is.mean,
    other: { value: L.same_session, label: "on the same day" },
    guess: 1 / 3,
    lead: "Not on its own, but a short re-setup brings it back.",
    answer: `A model built in the first session drops from ${pct(L.same_session)} on the same day to ${pct(L.post.as_is.mean)} two weeks later. Five new practice trials of each movement bring it back to ${pct(L.post.re_setup.mean)}.`,
    note: `Three choices. Two weeks later: ${L.post.as_is.n} patients; a month after training (${L.follow.as_is.n} patients): ${pct(L.follow.as_is.mean)}, and ${pct(L.follow.re_setup.mean)} after the re-setup.`,
  },
];
