// The last seconds of streamed EEG for the display channels, kept outside React: the
// panel draws from it on its own animation frames, so no React state changes per sample.

export const PHASE_CODES = { rest: 1, prepare: 2, imagery: 3 } as const;

/** A decoded window, drawn as a bracket over the trace it was read from. */
export interface ReadMark {
  end: number; // sample count (since reset) of the window's last sample
  len: number; // window length in display samples
  kind: "move" | "rest";
  right: boolean | null;
}

export class EegRing {
  channels: string[] = [];
  data: Float32Array[] = [];
  phase = new Uint8Array(0); // the phase code of each sample (background colour)
  truth: (string | null)[] = []; // the cue of each sample's trial, for the imagery colour
  capacity = 0;
  write = 0; // next index to write
  filled = 0;
  sfreq = 125;
  version = 0; // bumped on every push, so the painter can skip unchanged frames
  trialT = 0; // seconds into the current trial at the newest sample (the trial strip's playhead)
  total = 0; // samples pushed since the last reset
  marks: ReadMark[] = []; // the windows the model has read that are still on screen
  private currentPhase = 0;
  private currentTruth: string | null = null;

  reset(channels: string[], sfreq: number, seconds = 8) {
    this.channels = channels;
    this.sfreq = sfreq;
    this.capacity = Math.round(seconds * sfreq);
    this.data = channels.map(() => new Float32Array(this.capacity));
    this.phase = new Uint8Array(this.capacity);
    this.truth = new Array(this.capacity).fill(null);
    this.write = 0;
    this.filled = 0;
    this.total = 0;
    this.marks = [];
    this.version += 1;
  }

  /** Remember a decoded window ending at the newest sample. */
  mark(m: Omit<ReadMark, "end">) {
    this.marks.push({ ...m, end: this.total });
    this.marks = this.marks.filter((k) => k.end > this.total - this.capacity);
    this.version += 1;
  }

  setPhase(phase: keyof typeof PHASE_CODES, truth: string | null) {
    this.currentPhase = PHASE_CODES[phase];
    if (phase === "imagery") this.currentTruth = truth;
    if (phase === "rest") this.currentTruth = null;
  }

  /** data: display channels × samples, microvolts; t: the chunk's start in the trial, seconds. */
  push(data: number[][], t?: number) {
    if (!this.capacity || !data.length) return;
    const n = data[0].length;
    if (t !== undefined) this.trialT = t + n / this.sfreq;
    for (let i = 0; i < n; i++) {
      for (let c = 0; c < this.data.length; c++) this.data[c][this.write] = data[c]?.[i] ?? 0;
      this.phase[this.write] = this.currentPhase;
      this.truth[this.write] = this.currentTruth;
      this.write = (this.write + 1) % this.capacity;
    }
    this.filled = Math.min(this.filled + n, this.capacity);
    this.total += n;
    if (this.marks.length && this.marks[0].end <= this.total - this.capacity) {
      this.marks = this.marks.filter((k) => k.end > this.total - this.capacity);
    }
    this.version += 1;
  }
}

export const eegBuffer = new EegRing();
