// The page is a list of questions, in the order an examiner would ask them. Each chapter takes
// its title from here, and the list under the opening shows every answer in a few words.

import { benchRow, data, pct } from "./data";
import { PRACTICE_S } from "./findings";

const SWITCH = benchRow("T3_sf_vs_rest");
const WHICH = benchRow("T1_ah_vs_sf");

export interface Question {
  id: string;
  ask: string;
  /** The answer in a few words, for the list under the opening. */
  short: string;
}

export const QUESTIONS: Question[] = [
  {
    id: "problem",
    ask: "What problem does it solve?",
    short: "A stroke often leaves a hand too weak to grip",
  },
  { id: "what", ask: "What is this?", short: "A robotic sixth finger, moved by reading the brain" },
  { id: "demo", ask: "Can we see it work?", short: "Yes, on recordings the model never learned from" },
  { id: "data", ask: "Did you record the brain signals?", short: "No: a public recording of 24 stroke patients" },
  {
    id: "published",
    ask: `The paper reports ${pct(data.leak.published[0])}. Is that right?`,
    short: `No: tested fairly, the same method gets ${pct(data.leak.mean_leakfree)}`,
  },
  {
    id: "command",
    ask: "Can the sixth finger be a command of its own?",
    short: "As a switch, yes; apart from the hand, not yet",
  },
  {
    id: "use",
    ask: "How would a patient use it, and which parts are built?",
    short: `About ${PRACTICE_S} s of practice to start; the model is built, the headset link and finger are not`,
  },
  {
    id: "numbers",
    ask: "How good is it, in numbers?",
    short: `${pct(SWITCH.best.mean)} on sixth finger or rest, ${pct(WHICH.best.mean)} on hand or sixth finger; guessing gets ${pct(SWITCH.chance)}`,
  },
  {
    id: "added",
    ask: "What did you add?",
    short: "A fair test of what was already there, and what it shows",
  },
];

export const question = (id: string) => {
  const i = QUESTIONS.findIndex((q) => q.id === id);
  if (i < 0) throw new Error(`No question ${id}`);
  return { ...QUESTIONS[i], n: i + 1 };
};
