// Turns noisy class probabilities into stable commands (continuous mode only).
// Same algorithm and defaults as server/app/gate.py; both are tested on the same vectors.

export interface GateOptions {
  nClasses: number;
  restIndex: number;
  alpha: number;
  threshold: number;
  dwell: number;
  release: number;
}

export const DEFAULT_GATE: GateOptions = {
  nClasses: 3,
  restIndex: 0,
  alpha: 0.3,
  threshold: 0.6,
  dwell: 2,
  release: 0.45,
};

export class CommandGate {
  readonly opts: GateOptions;
  smoothed: number[] = [];
  active = 0;
  private candidate = 0;
  private count = 0;

  constructor(opts: Partial<GateOptions> = {}) {
    this.opts = { ...DEFAULT_GATE, ...opts };
    this.reset();
  }

  reset(): void {
    const { nClasses, restIndex } = this.opts;
    this.smoothed = Array.from({ length: nClasses }, () => 1 / nClasses);
    this.active = restIndex;
    this.candidate = restIndex;
    this.count = 0;
  }

  update(probs: number[]): number {
    const { alpha, threshold, dwell, release, restIndex } = this.opts;
    this.smoothed = this.smoothed.map((s, i) => alpha * probs[i] + (1 - alpha) * s);
    const best = this.smoothed.indexOf(Math.max(...this.smoothed));

    if (this.active !== restIndex && this.smoothed[this.active] < release) {
      this.active = restIndex;
    }

    if (best !== restIndex && this.smoothed[best] >= threshold) {
      this.count = best === this.candidate ? this.count + 1 : 1;
      this.candidate = best;
      if (this.count >= dwell) this.active = best;
    } else {
      this.candidate = restIndex;
      this.count = 0;
    }
    return this.active;
  }
}
