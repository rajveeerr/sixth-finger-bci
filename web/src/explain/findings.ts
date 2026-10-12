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
  answer: string;
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
    answer: `Right ${pct(task("T3_sf_vs_rest").mean)} of the time, about 3 times in 4. Guessing gets half.`,
  },
  {
    key: "which",
    question: "Which movement: the hand or the sixth finger?",
    value: task("T1_ah_vs_sf").mean,
    valueLabel: "right",
    guess: 0.5,
    answer: `Right ${pct(task("T1_ah_vs_sf").mean)} of the time: only a little better than guessing.`,
  },
  {
    key: "leak",
    question: "Was the earlier 85% real?",
    value: data.leak.mean_leakfree,
    other: { value: data.leak.mean_replica, label: "tested the old way" },
    valueLabel: "tested fairly",
    guess: 0.5,
    answer: `No. It was tested on trials the model had already seen. Tested fairly, the same method gets ${pct(data.leak.mean_leakfree)}.`,
  },
  {
    key: "setup",
    question: "How long does a new patient need to set it up?",
    value: data.calibration.transfer[0].mean,
    other: { value: data.calibration.scratch[0].mean, label: "from scratch" },
    valueLabel: "after 30 s, starting from other patients",
    guess: 1 / 3,
    answer: `Starting from other patients' data, 30 seconds gets ${pct(data.calibration.transfer[0].mean)}. From scratch that takes about 5 minutes.`,
  },
  {
    key: "switch",
    question: "Does it work as a simple on/off switch?",
    value: data.switch.detection,
    valueLabel: "of tries switch it on",
    answer: `It switches on ${pct(data.switch.detection)} of the time, about ${Math.round(data.switch.latency_s)} s after the patient starts, with about ${Math.round(data.switch.false_per_minute)} false switch a minute.`,
  },
];
