import { useMemo } from "react";
import * as K from "../iso/kit";

// A dial gauge in the bench's finish, lying on a small base: the face reads 0 to 100%,
// a hatched arc marks what guessing would score, the black needle is our score and a
// thin grey needle, when there is one, the score it is compared with.

const W = 300;
const H = 175;
const C = 60; // dial centre in plan
const FACE_Z = 21;
const R_FACE = 43;
const SWEEP = (250 * Math.PI) / 180;

const P = K.fitProjection(
  [...K.boxCorners({ x: 0, y: 0, w: 120, d: 120, r: 0 }, 0, 6), [C, C, FACE_Z + 6]],
  W,
  H,
  { pad: 6, azimuth: 45 },
);

// The dial's "up" on screen is the plan direction away from the viewer.
const TOP = Math.atan2(-Math.cos(Math.PI / 4), Math.sin(Math.PI / 4));
const angleOf = (v: number) => TOP - SWEEP / 2 + v * SWEEP;
const onFace = (angle: number, r: number, z = FACE_Z): K.Point3 => [C + Math.sin(angle) * r, C - Math.cos(angle) * r, z];

function arc(from: number, to: number, r0: number, r1: number, z = FACE_Z + 0.05) {
  const steps = 40;
  const outer: K.Point3[] = [];
  const inner: K.Point3[] = [];
  for (let i = 0; i <= steps; i++) {
    const a = angleOf(from + ((to - from) * i) / steps);
    outer.push(onFace(a, r1, z));
    inner.push(onFace(a, r0, z));
  }
  return K.pathOf([...outer, ...inner.reverse()].map((p) => K.iso(p, P)), true);
}

function needle(v: number, length: number, width: number) {
  const a = angleOf(v);
  const side = a + Math.PI / 2;
  const tip = onFace(a, length, FACE_Z + 1.5);
  const tail = onFace(a + Math.PI, 7, FACE_Z + 1.5);
  const l: K.Point3 = [C + Math.sin(side) * width, C - Math.cos(side) * width, FACE_Z + 1.5];
  const r: K.Point3 = [C - Math.sin(side) * width, C + Math.cos(side) * width, FACE_Z + 1.5];
  return K.pathOf([tip, l, tail, r].map((p) => K.iso(p, P)), true);
}

/** A dial; without a label it is decoration, for when the words beside it say the same. */
export function Gauge({ value, other, guess, label }: { value: number; other?: number; guess?: number; label?: string }) {
  const art = useMemo(() => {
    const parts: string[] = [];
    const base: K.Plan = { x: 0, y: 0, w: 120, d: 120, r: 10 };
    parts.push(K.solidSvg(K.slabOf(base, 0, 6, P, 8, 0.8), { tone: "mid", halo: true }));
    parts.push(K.dotsSvg(K.corners(base, 9).map(([x, y]) => K.iso([x, y, 6], P)), { size: 1.4, tone: "mid" }));
    parts.push(K.solidSvg(K.cylinder(C, C, 52, 6, 12, P, 72, 1), { tone: "hi" }));
    parts.push(K.lineSvg(K.knurl(C, C, 52, 6, 18, 90, P, 2), { tone: "faint" }));
    parts.push(K.solidSvg(K.cylinder(C, C, 47, 18, FACE_Z - 18, P, 72, 0.6), { tone: "hi", lit: true }));
    if (guess !== undefined && guess > 0) parts.push(`<path class="gauge-guess" d="${arc(0, guess, R_FACE - 9, R_FACE)}"/>`);
    const minor: string[] = [];
    const major: string[] = [];
    for (let i = 0; i <= 50; i++) {
      const a = angleOf(i / 50);
      const big = i % 5 === 0;
      (big ? major : minor).push(K.segment(onFace(a, R_FACE - (big ? 6 : 3)), onFace(a, R_FACE), P));
    }
    parts.push(K.lineSvg(minor.join(""), { tone: "mid" }), K.lineSvg(major.join(""), { tone: "hi" }));
    return parts.join("");
  }, [guess]);
  const hub = useMemo(() => K.solidSvg(K.cylinder(C, C, 4.5, FACE_Z + 1.5, 2, P, 24), { tone: "hi" }), []);
  return (
    <svg className="iso-svg gauge" viewBox={`0 0 ${W} ${H}`} role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <g dangerouslySetInnerHTML={{ __html: art }} />
      {other !== undefined && <path className="gauge-ghost" d={needle(other, R_FACE - 4, 1.4)} />}
      <path className="gauge-needle" d={needle(value, R_FACE - 2, 2.2)} />
      <g dangerouslySetInnerHTML={{ __html: hub }} />
    </svg>
  );
}
