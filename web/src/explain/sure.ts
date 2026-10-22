// What the "only when sure" slider reads off the coverage curve: each patient's surest
// decisions first, so a smaller share taken is a stricter bar.

export interface CoveragePoint {
  /** The share of decisions taken, 0 to 1. */
  share: number;
  /** How often those decisions are right, 0 to 1. */
  acc: number;
  ci: [number, number];
}

/** Words with some of them in bold, for a readout. */
export type Said = (string | { b: string })[];

const pct = (v: number) => `${Math.round(v * 100)}%`;

/** The curve's point at a slider position, held to the curve's ends. */
export function coverageAt(curve: CoveragePoint[], i: number): CoveragePoint {
  return curve[Math.min(curve.length - 1, Math.max(0, Math.round(i)))];
}

/** The curve's point nearest a share, for a pointer over the chart. */
export function nearestShare(curve: CoveragePoint[], share: number): number {
  let best = 0;
  curve.forEach((p, i) => {
    if (Math.abs(p.share - share) < Math.abs(curve[best].share - share)) best = i;
  });
  return best;
}

/** The slider's reading, in words. */
export function sayCoverage(p: CoveragePoint): Said {
  if (p.share > 0.995) return ["Taking every decision, it is right ", { b: pct(p.acc) }, " of the time."];
  return [
    "Taking only its surest ",
    { b: pct(p.share) },
    " of decisions, it is right ",
    { b: pct(p.acc) },
    " of the time, and waits on the rest.",
  ];
}

/** Said as plain text, for a label or a test. */
export const plain = (said: Said) => said.map((s) => (typeof s === "string" ? s : s.b)).join("");
