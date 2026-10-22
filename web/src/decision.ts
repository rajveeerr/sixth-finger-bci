// The demo's reading of each decision: one move-or-rest switch drives the finger, because
// the model tells imagining a movement from resting far better than which movement
// (question 3). Its hand-or-finger lean is shown under it as a guess.

import { CommandGate } from "./lib/gate";
import type { ClassInfo, Prediction } from "./stream/types";

/** The chance that some movement is imagined: the hand's and the sixth finger's added. */
export const moveChance = (probs: number[]) => (probs[1] ?? 0) + (probs[2] ?? 0);

export interface Reading {
  move: boolean;
  /** How strongly the model leans to that reading, from its own estimate. */
  sure: number;
  /** The likelier of the two movements, as a class name: only a guess. */
  guess: string;
  /** Whether it matches the cue, hand and sixth finger both counting as a movement; null without a cue. */
  right: boolean | null;
}

/** The likelier of hand and sixth finger. */
export function guessOf(probs: number[], classes: ClassInfo[]): string {
  const k = probs[1] >= probs[2] ? 1 : 2;
  return classes[k]?.name ?? (k === 1 ? "affected_hand" : "sixth_finger");
}

/** Right when the reading matches the cue: rest as rest, the hand or the sixth finger as a movement. */
export function moveIsRight(move: boolean, p: Prediction, classes: ClassInfo[]): boolean | null {
  if (p.truth === null) return null;
  return move === (p.truth !== (classes[0]?.name ?? "rest"));
}

/** One fixed 4 s window: a movement when the two movements together beat rest. */
export function readWindow(p: Prediction, classes: ClassInfo[]): Reading {
  const chance = moveChance(p.probs);
  const move = chance > p.probs[0];
  return {
    move,
    sure: move ? chance : p.probs[0],
    guess: guessOf(p.probs, classes),
    right: moveIsRight(move, p, classes),
  };
}

/**
 * The continuous switch, as question 4 measured it: the command gate on rest against the two
 * movements added. It turns on when the steadied chance of a movement is above 60% twice in
 * a row, and off when it falls below 45%.
 */
export class MoveSwitch {
  private readonly gate = new CommandGate({ nClasses: 2, restIndex: 0 });

  reset() {
    this.gate.reset();
  }

  read(p: Prediction, classes: ClassInfo[]): Reading {
    const move = this.gate.update([p.probs[0], moveChance(p.probs)]) === 1;
    const [rest, chance] = this.gate.smoothed;
    return {
      move,
      sure: move ? chance : rest,
      guess: guessOf(p.probs, classes),
      right: moveIsRight(move, p, classes),
    };
  }
}

export interface Tally {
  right: number;
  total: number;
}

/** The running score of the fixed windows; the half-second readings of continuous mode are not counted. */
export function countReading(t: Tally, p: Prediction, r: Reading): Tally {
  if (p.window === "sliding" || r.right === null) return t;
  return { right: t.right + (r.right ? 1 : 0), total: t.total + 1 };
}
