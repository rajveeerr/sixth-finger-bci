// The numbers the chapters say in words, worked out once from data.json, and what each test's
// model learned from and was tested on, drawn under "How we know".

import { data } from "./data";
import type { Split } from "./figures/LearnTest";

/** A share, with one decimal when it is small enough for rounding to hide it. */
export const pctFine = (v: number) => (v < 0.095 ? `${(v * 100).toFixed(1)}%` : `${Math.round(v * 100)}%`);

const C = data.calibration;
/** One practice trial of each movement, already learned from other patients. */
export const FIRST = C.transfer[0];
/** Where starting from nothing first does as well as FIRST. */
export const REACH = C.scratch.find((p) => p.mean >= FIRST.mean - 0.005) ?? C.scratch[C.scratch.length - 1];
/** Seconds of practice with help from other patients, to the nearest ten. */
export const PRACTICE_S = Math.round((FIRST.minutes * 60) / 10) * 10;
/** Minutes of practice starting from nothing, to the nearest minute. */
export const SCRATCH_MIN = Math.round(REACH.minutes);
/** The practice on a later day, as it was tested: 5 trials of each movement. */
export const AGAIN_K = 5;
export const AGAIN_MIN = (AGAIN_K * FIRST.minutes) / FIRST.k;

const POINTS = [
  data.leak.mean_diff_points,
  ...data.elsewhere.motor.map((m) => m.points),
  ...data.elsewhere.depression.map((d) => d.points),
];
/** How far the leak raised the score, across every dataset and method we checked, in points. */
export const LEAK_RANGE = [Math.round(Math.min(...POINTS)), Math.round(Math.max(...POINTS))];

/** "about 30 s" or "about 5 min". */
export const about = (minutes: number) =>
  minutes < 1 ? `about ${Math.round((minutes * 60) / 10) * 10} s` : `about ${Math.round(minutes)} min`;

/** How often a rate per minute comes to, in words: "once", "twice", "3 times". */
export const timesWord = (n: number) => {
  const r = Math.round(n);
  return r <= 1 ? "once" : r === 2 ? "twice" : `${r} times`;
};

export const SPLITS: Record<"setup" | "sixth" | "live" | "later", Split> = {
  setup: {
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
  sixth: {
    label: "What each model learned from and what it was tested on",
    rows: [
      {
        title: "Other patients",
        note: "only for hand or sixth finger",
        many: true,
        runs: ["learn", "learn", "learn", "learn"],
        learns: "the network first learns from all their sessions",
        sometimes: true,
      },
      {
        title: "Each patient",
        note: "session 1",
        runs: ["learn", "learn", "test", "test"],
        learns: "learns from runs 1 and 2, and how sure to be before acting",
        tested: "tested on runs 3 and 4, hand trials too",
      },
    ],
    note: "The switch learned from rest and sixth-finger trials only, so the hand trials of runs 3 and 4 were new to it.",
  },
  live: {
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
  later: {
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
    note: "Dark squares in runs 1 and 2: one example of a random pick.",
  },
};
