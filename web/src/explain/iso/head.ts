// A real adult head wearing an EEG cap, drawn in the bench's finish. The surface is MNE's
// template head (fsaverage's outer skin; scripts/make_web_explain_data.py writes it to
// head.json) and the electrodes are the 10-05 montage defined on that same head, so every
// sensor sits where a cap puts it. Faces turned to the viewer are painted back to front in
// the kit's four tones; the cap is the scalp above its seam, a shade darker; outlines are
// the edges where the surface turns away. A chin strap holds the cap on.

import { data } from "../data";
import mesh from "../head.json";
import * as K from "./kit";

export type V3 = [number, number, number];
const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const mul = (a: V3, s: number): V3 => [a[0] * s, a[1] * s, a[2] * s];
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const unit = (a: V3): V3 => mul(a, 1 / (Math.hypot(a[0], a[1], a[2]) || 1));
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];

/** The direction toward the viewer (the kit's depth grows along it). */
export function toViewer(P: K.Projection): V3 {
  const a = ((P.azimuth ?? K.AZIMUTH) * Math.PI) / 180;
  const e = ((P.elevation ?? K.ELEVATION) * Math.PI) / 180;
  return [Math.cos(a) * Math.cos(e), Math.sin(a) * Math.cos(e), Math.sin(e)];
}

/** Light from the screen's left and above, as the kit lights its solids. */
function toLight(P: K.Projection): V3 {
  const a = ((P.azimuth ?? K.AZIMUTH) * Math.PI) / 180;
  return unit([-Math.sin(a), Math.cos(a), 1.1]);
}

export interface HeadPose {
  /** Where the template's origin (between the ears, roughly) goes in the world. */
  origin: V3;
  /** World units per millimetre. */
  scale: number;
  /** The plan direction the nose points along. */
  nose: [number, number];
  /** Drop the neck below this height, in the template's millimetres. */
  cutMm: number;
}

export interface PlacedElectrode {
  name: string;
  shown: boolean;
  p: V3;
  n: V3;
  visible: boolean;
}

export interface Head {
  svg: string;
  electrodes: PlacedElectrode[];
  /** The neck's cut: its centre in the world and its radius in world units. */
  neck: { c: V3; r: number };
}

const VERTS = mesh.vertices as unknown as V3[];
const FACES = mesh.faces as unknown as [number, number, number][];
const SENSORS = mesh.electrodes as unknown as Record<string, V3>;

/** +1 if the faces wind so their normals point out of the head, else -1. */
const WIND = (() => {
  const centre = mul(VERTS.reduce((s, v) => add(s, v), [0, 0, 0] as V3), 1 / VERTS.length);
  let out = 0;
  for (const [a, b, c] of FACES) out += Math.sign(dot(cross(sub(VERTS[b], VERTS[a]), sub(VERTS[c], VERTS[a])), sub(VERTS[a], centre)));
  return out < 0 ? -1 : 1;
})();

/** Outward normals at the template's vertices: averaged from their faces, then smoothed
 * over their neighbours, so the tones follow the head's form rather than its facets. */
const VERTEX_NORMALS: V3[] = (() => {
  let acc: V3[] = VERTS.map(() => [0, 0, 0]);
  const neighbours: Set<number>[] = VERTS.map(() => new Set());
  for (const [a, b, c] of FACES) {
    const n = mul(cross(sub(VERTS[b], VERTS[a]), sub(VERTS[c], VERTS[a])), WIND);
    for (const i of [a, b, c]) acc[i] = add(acc[i], n);
    neighbours[a].add(b).add(c);
    neighbours[b].add(a).add(c);
    neighbours[c].add(a).add(b);
  }
  acc = acc.map(unit);
  for (let pass = 0; pass < 3; pass++) {
    acc = acc.map((n, i) => unit([...neighbours[i]].reduce((s, j) => add(s, acc[j]), n)));
  }
  return acc;
})();

/** The cap's seam as a signed height: positive above a tilted plane just under the lowest
 * electrodes at the front and at the back. */
const ABOVE_SEAM = (() => {
  const pts = Object.values(SENSORS);
  const yf = Math.max(...pts.map((p) => p[1]));
  const yb = Math.min(...pts.map((p) => p[1]));
  const zf = Math.min(...pts.filter((p) => p[1] > yf - 40).map((p) => p[2]));
  const zb = Math.min(...pts.filter((p) => p[1] < yb + 40).map((p) => p[2]));
  const slope = (zf - zb) / (yf - yb);
  return (v: V3) => v[2] - (zb - 12 + (v[1] - yb) * slope);
})();

/** The chin strap: the plane through both ears' level and under the chin (it holds the
 * left-right axis); where it crosses the bare skin is the strap. */
const STRAP = (v: V3) => 85 * (v[1] + 5) + 45 * (v[2] + 15);

interface Corner {
  m: V3; // template millimetres
  n: V3; // smoothed normal
}

/** Split a polygon by a signed function: the parts where it is positive and negative, and
 * the cut between them (two points, when the polygon crosses zero). */
function split(poly: Corner[], f: (v: V3) => number): { pos: Corner[]; neg: Corner[]; cut: Corner[] } {
  const pos: Corner[] = [];
  const neg: Corner[] = [];
  const cut: Corner[] = [];
  for (let k = 0; k < poly.length; k++) {
    const p = poly[k];
    const q = poly[(k + 1) % poly.length];
    const fp = f(p.m);
    const fq = f(q.m);
    (fp >= 0 ? pos : neg).push(p);
    if ((fp >= 0) !== (fq >= 0)) {
      const t = fp / (fp - fq);
      const x: Corner = { m: add(p.m, mul(sub(q.m, p.m), t)), n: unit(add(mul(p.n, 1 - t), mul(q.n, t))) };
      pos.push(x);
      neg.push(x);
      cut.push(x);
    }
  }
  return { pos, neg, cut };
}

function nearestVertex(m: V3) {
  let best = 0;
  let bd = Infinity;
  VERTS.forEach((v, i) => {
    const d = (v[0] - m[0]) ** 2 + (v[1] - m[1]) ** 2 + (v[2] - m[2]) ** 2;
    if (d < bd) {
      bd = d;
      best = i;
    }
  });
  return best;
}

/** The pose's frame: the head's right, forward and up, and the map from template to world. */
export function placeHead(pose: HeadPose) {
  const N = unit([pose.nose[0], pose.nose[1], 0]);
  const Z: V3 = [0, 0, 1];
  const R = cross(N, Z); // the head's right, so (R, N, Z) is right-handed like the template
  const turn = (m: V3): V3 => add(add(mul(R, m[0]), mul(N, m[1])), mul(Z, m[2]));
  const world = (m: V3): V3 => add(pose.origin, mul(turn(m), pose.scale));
  return { N, Z, R, turn, world };
}

export function headSvg(P: K.Projection, pose: HeadPose): Head {
  const V = toViewer(P);
  const L = toLight(P);
  const { N, Z, turn, world } = placeHead(pose);
  const W = VERTS.map(world);
  const depth = W.map((p) => K.depthOf(p, P));
  const flatOf = (c: Corner) => K.iso(world(c.m), P);
  const depthOfCorner = (c: Corner) => K.depthOf(world(c.m), P);
  const bias = 4 * pose.scale; // lines draw over the faces they lie on, not over nearer ones

  type Item = { depth: number; kind: string; d: string };
  const items: Item[] = [];
  const facingOf = new Map<string, boolean[]>();
  const above = (v: V3) => v[2] - pose.cutMm;
  for (const [a, b, c] of FACES) {
    const n = unit(mul(cross(sub(W[b], W[a]), sub(W[c], W[a])), WIND));
    const facing = dot(n, V) > 0;
    const zs = [VERTS[a][2], VERTS[b][2], VERTS[c][2]];
    if (Math.max(...zs) <= pose.cutMm) continue;
    if (Math.min(...zs) > pose.cutMm) {
      for (const [i, j] of [
        [a, b],
        [b, c],
        [c, a],
      ]) {
        const key = i < j ? `${i}_${j}` : `${j}_${i}`;
        facingOf.set(key, [...(facingOf.get(key) ?? []), facing]);
      }
    }
    if (!facing) continue;
    const tri: Corner[] = [a, b, c].map((i) => ({ m: VERTS[i], n: VERTEX_NORMALS[i] }));
    const kept = split(tri, above);
    if (kept.cut.length === 2) {
      items.push({ depth: Math.max(...kept.cut.map(depthOfCorner)) + bias, kind: "edge", d: K.pathOf(kept.cut.map(flatOf)) });
    }
    const parts = split(kept.pos, ABOVE_SEAM);
    if (parts.cut.length === 2) {
      items.push({ depth: Math.max(...parts.cut.map(depthOfCorner)) + bias, kind: "seam", d: K.pathOf(parts.cut.map(flatOf)) });
    }
    const strap = split(parts.neg, STRAP);
    if (strap.cut.length === 2) {
      items.push({ depth: Math.max(...strap.cut.map(depthOfCorner)) + bias, kind: "strap", d: K.pathOf(strap.cut.map(flatOf)) });
    }
    for (const [poly, cap] of [
      [parts.pos, true],
      [parts.neg, false],
    ] as const) {
      if (poly.length < 3) continue;
      const nm = unit(turn(unit(poly.reduce((s, q) => add(s, q.n), [0, 0, 0] as V3))));
      const tone = Math.min(4, Math.max(0, Math.floor(((dot(nm, L) + 1) / 2) * 5)));
      const dd = poly.reduce((s, q) => s + depthOfCorner(q), 0) / poly.length;
      items.push({ depth: dd, kind: `${cap ? "cap" : "skin"}${tone}`, d: K.pathOf(poly.map(flatOf), true) });
    }
  }
  // Outlines where the surface turns away from the viewer.
  for (const [key, facing] of facingOf) {
    if (facing.length !== 2 || facing[0] === facing[1]) continue;
    const [i, j] = key.split("_").map(Number);
    items.push({ depth: Math.max(depth[i], depth[j]) + bias, kind: "edge", d: K.pathOf([K.iso(W[i], P), K.iso(W[j], P)]) });
  }
  items.sort((p, q) => p.depth - q.depth);
  const runs: { kind: string; d: string }[] = [];
  for (const it of items) {
    const last = runs[runs.length - 1];
    if (last && last.kind === it.kind) last.d += it.d;
    else runs.push({ kind: it.kind, d: it.d });
  }
  const body = runs
    .map((r) => {
      if (r.kind === "edge" || r.kind === "seam" || r.kind === "strap") return `<path class="head-${r.kind}" d="${r.d}"/>`;
      const cap = r.kind.startsWith("cap");
      return `<path class="head-${cap ? "cap" : "skin"}" data-tone="${r.kind.slice(cap ? 3 : 4)}" d="${r.d}"/>`;
    })
    .join("");

  // The electrodes: a cup on the cap for each, turned to face out of the scalp.
  const byName = new Map(data.electrodes.map((e) => [e.name, e]));
  const electrodes: PlacedElectrode[] = Object.entries(SENSORS).map(([name, m]) => {
    const n = unit(turn(VERTEX_NORMALS[nearestVertex(m)]));
    return { name, shown: !!byName.get(name)?.shown, p: world(m), n, visible: dot(n, V) > 0.15 };
  });
  const cups = electrodes
    .filter((e) => e.visible)
    .sort((a, b) => K.depthOf(a.p, P) - K.depthOf(b.p, P))
    .map((e) => {
      const side = cross(e.n, Z);
      const t1 = unit(Math.hypot(side[0], side[1], side[2]) > 1e-3 ? side : N);
      const t2 = cross(e.n, t1);
      const disc = (lift: number, radius: number) =>
        K.pathOf(
          Array.from({ length: 20 }, (_, k) => {
            const t = (k / 20) * Math.PI * 2;
            const rim = add(mul(t1, Math.cos(t) * radius), mul(t2, Math.sin(t) * radius));
            return K.iso(add(add(e.p, mul(e.n, lift)), rim), P);
          }),
          true,
        );
      const r0 = (e.shown ? 6.5 : 5) * pose.scale;
      return `<g class="${e.shown ? "cup cup-shown" : "cup"}"><title>${e.name}</title><path class="cup-base" d="${disc(1.5 * pose.scale, r0 * 1.2)}"/><path class="cup-top" d="${disc(4 * pose.scale, r0)}"/></g>`;
    });

  // The neck's cut, for whatever the head stands on.
  const ring = VERTS.filter((v) => Math.abs(v[2] - pose.cutMm) < 10);
  const nc: V3 = ring.length ? mul(ring.reduce((s, v) => add(s, v), [0, 0, 0] as V3), 1 / ring.length) : [0, -20, pose.cutMm];
  const nr = ring.length ? Math.min(...ring.map((v) => Math.hypot(v[0] - nc[0], v[1] - nc[1]))) : 40;
  return {
    svg: `<g class="head" data-seamless="">${body}</g><g class="cups">${cups.join("")}</g>`,
    electrodes,
    neck: { c: world([nc[0], nc[1], pose.cutMm]), r: nr * pose.scale },
  };
}

/** Every eighth vertex of the head above the usual neck cut, for fitting a projection. */
export const HEAD_BOUNDS: V3[] = VERTS.filter((v, i) => i % 8 === 0 && v[2] > -95);
