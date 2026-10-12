// The hand both prototypes draw: an artist's segmented hand model (a palm block, ball
// knuckles and round segments) wearing the robotic sixth finger on a wrist strap.
// Centimetres; x toward the little finger, y out of the back of the hand, z up the fingers.

import type { FingerPose, HandPose } from "../components/Hand/poses";

export type P3 = [number, number, number];

export const PALM = { w: 8.2, d: 2.6, h: 9.0, r: 1.1 }; // centred on x = 0, y = 0, from z = 0
export const FINGERS = [
  { x: -2.75, lengths: [3.9, 2.4, 2.0], r: 0.92, splay: -0.07 },
  { x: -0.92, lengths: [4.3, 2.7, 2.1], r: 0.95, splay: -0.015 },
  { x: 0.95, lengths: [4.0, 2.5, 2.0], r: 0.9, splay: 0.04 },
  { x: 2.75, lengths: [3.2, 2.1, 1.8], r: 0.8, splay: 0.1 },
] as const;
export const KNUCKLE_Z = PALM.h + 0.15;
export const THUMB = { base: [-3.4, -0.3, 2.4] as P3, lengths: [3.6, 3.0, 2.4], r: 1.05 };
export const WRIST = { rx: 3.0, ry: 2.05, z0: -7.5 };
export const STRAP = { z0: -2.6, h: 1.9, grow: 0.3 };
export const HOUSING = { x: 4.0, y: -1.0, w: 2.0, d: 2.2, z0: -2.9, h: 2.8 };
export const SIXTH = { root: [5.0, 0.1, 0.2] as P3, lengths: [3.5, 3.0, 2.5], r: 0.62 };

export interface Segment {
  kind: "segment" | "link";
  a: P3;
  b: P3;
  r: number;
  part: string;
}
export interface Ball {
  kind: "ball";
  c: P3;
  r: number;
  part: string;
}
export type Piece = Segment | Ball;

const add = (p: P3, d: P3, s: number): P3 => [p[0] + d[0] * s, p[1] + d[1] * s, p[2] + d[2] * s];
const norm = (d: P3): P3 => {
  const n = Math.hypot(...d) || 1;
  return [d[0] / n, d[1] / n, d[2] / n];
};

/** A finger rising from `base`, tilted sideways by `splay`, curling toward the palm (−y). */
function chain(base: P3, lengths: readonly number[], r0: number, splay: number, pose: FingerPose, part: string, kind: "segment" | "link") {
  const out: Piece[] = [];
  let p = base;
  let theta = 0;
  lengths.forEach((len, i) => {
    theta += pose[i];
    const d: P3 = norm([Math.sin(splay) * Math.cos(theta), -Math.sin(theta), Math.cos(splay) * Math.cos(theta)]);
    const q = add(p, d, len);
    const r = kind === "link" ? r0 : r0 * (1 - 0.1 * i);
    out.push({ kind, a: p, b: q, r, part: `${part}${i}` });
    p = q;
  });
  return out;
}

/** The thumb: each segment turns from its open direction toward its grasp direction. */
function thumb(pose: FingerPose): Piece[] {
  const t = Math.min(1, Math.max(0, (pose[0] - 0.1) / 0.65));
  const open: P3[] = [[-0.85, -0.15, 0.5], [-0.68, -0.1, 0.72], [-0.48, -0.05, 0.88]];
  const grasp: P3[] = [[-0.2, -0.75, 0.62], [0.55, -0.75, 0.35], [0.9, -0.3, -0.2]];
  const out: Piece[] = [];
  let p = THUMB.base;
  THUMB.lengths.forEach((len, i) => {
    const d = norm([
      open[i][0] + (grasp[i][0] - open[i][0]) * t,
      open[i][1] + (grasp[i][1] - open[i][1]) * t,
      open[i][2] + (grasp[i][2] - open[i][2]) * t,
    ]);
    const q = add(p, d, len);
    out.push({ kind: "segment", a: p, b: q, r: THUMB.r * (1 - 0.1 * i), part: `thumb${i}` });
    if (i < 2) out.push({ kind: "ball", c: q, r: THUMB.r * (0.95 - 0.1 * i), part: `thumbj${i}` });
    p = q;
  });
  return out;
}

/** Every moving piece of the hand in a pose. */
export function pieces(pose: HandPose): Piece[] {
  const out: Piece[] = [];
  FINGERS.forEach((f, i) => {
    const base: P3 = [f.x, 0.1, KNUCKLE_Z];
    out.push({ kind: "ball", c: base, r: f.r * 1.08, part: `knuckle${i}` });
    const segs = chain(base, f.lengths, f.r, f.splay, pose.fingers[i], `f${i}s`, "segment");
    out.push(...segs);
    segs.slice(0, 2).forEach((s, j) => out.push({ kind: "ball", c: (s as Segment).b, r: f.r * (0.98 - 0.1 * j), part: `f${i}j${j}` }));
  });
  out.push({ kind: "ball", c: THUMB.base, r: THUMB.r * 1.1, part: "thumbbase" });
  out.push(...thumb(pose.thumb));
  const sixth = chain(SIXTH.root, SIXTH.lengths, SIXTH.r, 0.06, pose.sixth, "x", "link");
  out.push(...sixth);
  return out;
}

export const centroid = (p: Piece): P3 =>
  p.kind === "ball" ? p.c : [(p.a[0] + p.b[0]) / 2, (p.a[1] + p.b[1]) / 2, (p.a[2] + p.b[2]) / 2];

/** Hidden by the palm block: inside the planes of its three faces that face the viewer. */
export function behindPalm(p: Piece): boolean {
  const [x, y, z] = centroid(p);
  return y < PALM.d / 2 && x < PALM.w / 2 && z < PALM.h && z > 0;
}
