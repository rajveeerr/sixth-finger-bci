// What the study found, in plain words, with the numbers from data.json. Both ways of
// showing the results (dial gauges and bars) read this list.

import { data } from "./data";

export interface Finding {
  key: string;
  question: string;
  /** The main score, 0 to 1. */
  value: number;
  /** A second score to compare with (the faulty test, or starting from scratch). */
  other?: { value: number; label: string };
  valueLabel: string;
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

export const FINDINGS: Finding[] = [
  {
    key: "moving",
    question: "Is the patient imagining a movement, or resting?",
    value: task("T3_sf_vs_rest").mean,
    valueLabel: "right",
    guess: 0.5,
    lead: "About 3 times in 4.",
    answer: "When a patient imagines a movement, the brain signal shows it clearly.",
    note: "One dot per patient: a model trained on their first two runs, tested on the last two. The line is the average.",
  },
  {
    key: "which",
    question: "Which movement: the hand or the sixth finger?",
    value: task("T1_ah_vs_sf").mean,
    valueLabel: "right",
    guess: 0.5,
    lead: "Only a little better than guessing.",
    answer: "Imagining the hand and imagining the sixth finger look alike in the EEG, which is why the demo also offers an on/off switch.",
    note: "One dot per patient, tested the same way.",
  },
  {
    key: "leak",
    question: "Was the earlier 85% real?",
    value: data.leak.mean_leakfree,
    other: { value: data.leak.mean_replica, label: "tested the old way" },
    valueLabel: "tested fairly",
    guess: 0.5,
    lead: "No.",
    answer: `It was tested on trials the model had already seen. Tested fairly, the same method gets ${pct(data.leak.mean_leakfree)}.`,
    note: `One line per patient, the same method (CSP with LDA) scored both ways: ${data.leak.n_positive} of ${data.leak.subjects.length} fell.`,
  },
  {
    key: "setup",
    question: "How long does a new patient need to set it up?",
    value: data.calibration.transfer[0].mean,
    other: { value: data.calibration.scratch[0].mean, label: "from scratch" },
    valueLabel: "after 30 s",
    guess: 1 / 3,
    lead: "About 30 seconds, starting from other patients.",
    answer: `That gets ${pct(data.calibration.transfer[0].mean)} on all three choices. Starting from scratch, the same takes about 5 minutes.`,
    note: "Three choices: rest, hand, sixth finger. The bands are 95% intervals over 22 patients.",
  },
  {
    key: "switch",
    question: "Does it work as a simple on/off switch?",
    value: data.switch.detection,
    valueLabel: "of tries switch it on",
    lead: "Yes, about 2 times in 3.",
    answer: `It switches on about ${Math.round(data.switch.latency_s)} s after the patient starts imagining, with about ${Math.round(data.switch.false_per_minute)} false switch a minute.`,
    note: "Played back as if live, a decision every 0.5 s with the demo's smoothing. Average of 22 patients.",
  },
];
