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
  /**
   * Whether it matches the cue, hand and sixth finger both counting as a movement; null without
   * a cue. In continuous mode the store sets it from the switch-on behind a Move (SwitchCount).
   */
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

/** Seconds after the cue that answer 4 scores as imagining (IMAGERY_S in evaluation/pseudo_online.py). */
export const IMAGERY_S = 6;

export interface SwitchTally {
  /** Times the switch turned on. */
  moved: number;
  /** Switch-ons inside an imagining period. */
  right: number;
  /** Imagining periods that ended without a switch-on inside. */
  missed: number;
}

export const NO_SWITCHES: SwitchTally = { moved: 0, right: 0, missed: 0 };

/**
 * The continuous switch's running score, counted as answer 4 counts it (switch_metrics in
 * evaluation/pseudo_online.py): a switch-on is placed at the end of the window that turned it
 * on, it is right when that falls in the 6 s after the cue, and an imagining period with no
 * switch-on inside is missed. A period is scored only if its trial was seen from the start.
 */
export class SwitchCount {
  tally: SwitchTally = NO_SWITCHES;
  private on = false;
  /** Whether the current run of Move began inside imagining; null while off, or once its trial's imagining is over. */
  private onRight: boolean | null = null;
  private period: { trial: number; from: number; to: number; caught: boolean } | null = null;

  reset() {
    this.tally = NO_SWITCHES;
    this.on = false;
    this.onRight = null;
    this.period = null;
  }

  /** A trial starts from its beginning; `cueOnset` in seconds from that beginning. */
  start(trial: number, cueOnset: number) {
    this.period = { trial, from: cueOnset, to: cueOnset + IMAGERY_S, caught: false };
  }

  /**
   * One half-second reading: whether the switch is on, with `t` the end of its window in
   * seconds from the trial's start. Returns whether the switch-on behind a Move was right,
   * while that trial's imagining lasts.
   */
  read(trial: number, t: number, on: boolean): boolean | null {
    const p = this.period?.trial === trial ? this.period : null;
    if (on && !this.on) {
      const inside = !!p && t >= p.from && t < p.to;
      if (p && inside) p.caught = true;
      this.onRight = inside;
      this.tally = { ...this.tally, moved: this.tally.moved + 1, right: this.tally.right + (inside ? 1 : 0) };
    } else if (!on) {
      this.onRight = null;
    }
    this.on = on;
    if (p && t >= p.to) this.close();
    return this.onRight;
  }

  /** The trial reached its end, and its imagining period with it. */
  end(trial: number) {
    if (this.period?.trial === trial) this.close();
  }

  private close() {
    if (this.period && !this.period.caught) this.tally = { ...this.tally, missed: this.tally.missed + 1 };
    this.period = null;
    // A Move that runs on into the next trial is not marked again: its switch-on was scored.
    this.onRight = null;
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
