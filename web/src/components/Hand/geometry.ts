// The hand's shapes, built once from a few measured curves (centimetres; x toward the little
// finger, y along the fingers, z out of the back of the hand). Every part is one smooth
// surface with computed normals, so the clay material shades it without seams.

import { BufferGeometry, Float32BufferAttribute, LatheGeometry, Vector2 } from "three";

/** Smoothstep between edges a and b. */
export function smooth(a: number, b: number, x: number): number {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
}

const signedPow = (v: number, p: number) => Math.sign(v) * Math.abs(v) ** p;

export interface SweepSection {
  /** Half width (x), half thickness (z) and centre offset in z at height y. */
  halfWidth: number;
  halfDepth: number;
  zOffset?: number;
  /** Shift in y applied at this section, as a function of x across it. */
  yShift?: (x: number) => number;
  /** Bends the section back in z by this much per cm² of x (a curved plate). */
  zCurve?: number;
}

/**
 * A closed surface swept along y with rounded-rectangle sections (a superellipse with
 * exponent `n`); the ends close smoothly over `cap` centimetres.
 */
export function sweep(
  length: number,
  section: (y: number) => SweepSection,
  { n = 3, around = 56, along = 48, cap = 1 }: { n?: number; around?: number; along?: number; cap?: number } = {},
): BufferGeometry {
  const positions: number[] = [];
  const index: number[] = [];
  const e = 2 / n;
  for (let j = 0; j <= along; j++) {
    const v = j / along;
    const y = v * length;
    // Round the ends: the section shrinks on a quarter circle over the last `cap` cm.
    const fromEnd = Math.min(y, length - y);
    const s = fromEnd >= cap ? 1 : Math.sqrt(Math.max(0, 1 - ((cap - fromEnd) / cap) ** 2));
    const sec = section(y);
    for (let i = 0; i < around; i++) {
      const u = (i / around) * Math.PI * 2;
      const x = sec.halfWidth * s * signedPow(Math.cos(u), e);
      const z = sec.halfDepth * s * signedPow(Math.sin(u), e) + (sec.zOffset ?? 0) - (sec.zCurve ?? 0) * x * x;
      positions.push(x, y + (sec.yShift ? sec.yShift(x) * (y / length) : 0), z);
    }
  }
  for (let j = 0; j < along; j++) {
    for (let i = 0; i < around; i++) {
      const a = j * around + i;
      const b = j * around + ((i + 1) % around);
      const c = a + around;
      const d = b + around;
      index.push(a, c, b, b, c, d);
    }
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
  geometry.setIndex(index);
  geometry.computeVertexNormals();
  return geometry;
}

export const PALM_LENGTH = 8.9;

/** Where the knuckle line sits at x: highest at the middle finger, lower toward the little finger. */
export function knuckleY(x: number): number {
  return PALM_LENGTH - 0.42 * (x / 4) ** 2 - 0.38 * Math.max(0, x / 4) - 0.25;
}

/** The palm: wider at the knuckles than the wrist, arched across the back. */
export function palmGeometry(): BufferGeometry {
  return sweep(
    PALM_LENGTH,
    (y) => {
      const t = y / PALM_LENGTH;
      return {
        halfWidth: 3.05 + 0.95 * smooth(0, 0.75, t) + 0.22 * Math.sin(Math.PI * t),
        halfDepth: 1.3 - 0.28 * t,
        zOffset: 0.15 * Math.sin(Math.PI * t),
        yShift: (x) => knuckleY(x) - knuckleY(0) - 0.12 * (x / 4) ** 2,
      };
    },
    { n: 3.2, cap: 0.95 },
  );
}

/** The wrist and the start of the forearm, narrowest just above the wrist bones. */
export function forearmGeometry(length = 8.5): BufferGeometry {
  return sweep(
    length,
    (y) => {
      const t = y / length; // 0 at the cut, 1 at the wrist
      return { halfWidth: 3.45 - 0.55 * smooth(0, 1, t), halfDepth: 2.35 - 0.45 * smooth(0, 1, t), zOffset: -0.1 };
    },
    { n: 2.4, cap: 0.35, along: 24 },
  );
}

/**
 * One phalanx turning about its base: a sphere at the joint (y = 0), a shaft with a slight
 * waist, and a rounded end. The fingertip's end is longer and fuller, like a finger pad.
 */
export function phalanxGeometry(length: number, r0: number, r1: number, tip = false): BufferGeometry {
  const pts: Vector2[] = [];
  const capSteps = 8;
  for (let i = 0; i <= capSteps; i++) {
    const a = -Math.PI / 2 + (i / capSteps) * (Math.PI / 2);
    pts.push(new Vector2(Math.max(r0 * Math.cos(a), 1e-4), r0 * Math.sin(a)));
  }
  const shaftSteps = 10;
  for (let i = 1; i < shaftSteps; i++) {
    const t = i / shaftSteps;
    const r = r0 + (r1 - r0) * t - 0.07 * r0 * Math.sin(Math.PI * t);
    pts.push(new Vector2(r, t * length));
  }
  const endR = tip ? r1 * 1.02 : r1;
  const stretch = tip ? 1.35 : 1;
  for (let i = 0; i <= capSteps; i++) {
    const a = (i / capSteps) * (Math.PI / 2);
    pts.push(new Vector2(Math.max(endR * Math.cos(a), 1e-4), length + endR * stretch * Math.sin(a) - (tip ? endR * 0.35 : 0)));
  }
  const g = new LatheGeometry(pts, 28);
  g.scale(1, 1, 0.84); // fingers are flatter front to back than side to side
  g.computeVertexNormals();
  return g;
}

/** A nail: a thin curved plate lying on the back of a fingertip. */
export function nailGeometry(width: number, length: number): BufferGeometry {
  return sweep(
    length,
    () => ({ halfWidth: width / 2, halfDepth: 0.05, zCurve: 0.9 / width }),
    { n: 4, cap: Math.min(length, width) * 0.45, around: 24, along: 10 },
  );
}
