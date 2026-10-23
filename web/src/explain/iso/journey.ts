// A patient's path through the system as four stations in the bench's finish: the cap going
// on, the practice with the model beside it, therapy with the finger, and the calendar of the
// next visit. All share one camera and one scale, and each stands on the floor of a box of the
// same height, so they line up as a timeline. What a real system would still need is drawn
// inside a `data-needed` group, dashed by the page, as in the real system's pipeline.

import { headSvg, HEAD_BOUNDS, placeHead, type HeadPose } from "./head";
import * as K from "./kit";
import {
  BASE,
  fingerSvg,
  LAPTOP_BOUNDS,
  laptopSvg,
  MOTOR,
  MOTOR_FINGER_BOUNDS,
  motorSvg,
  needed,
  SERVER,
  serverBox,
} from "./pipeline";

export type Station = "cap" | "practice" | "therapy" | "calendar";

const AZ = 62;
const PAD = 6;
/** A box one column wide, in viewBox units; the stations are wider or narrower than that. */
const BOX_W = 200;
const WIDTH: Record<Station, number> = { cap: 1, practice: 1.4, therapy: 1.3, calendar: 0.6 };

const plate = (p: K.Plan, P: K.Projection) => K.solidSvg(K.slabOf(p, 0, BASE, P, 8, 0.8), { tone: "mid", halo: true });

/** Draws a group made for one place in the world at another, `by` world units away, `s` times its size. */
function moved(svg: string, P: K.Projection, by: K.Point3, s = 1) {
  const [dx, dy] = K.axisVector(P, by);
  const [ox, oy] = P.origin;
  const tx = (1 - s) * ox + dx;
  const ty = (1 - s) * oy + dy;
  return `<g transform="translate(${tx.toFixed(2)} ${ty.toFixed(2)})${s === 1 ? "" : ` scale(${s})`}">${svg}</g>`;
}

// The cap: the patient's head on a stand, the cap on it, and a small bridge box behind with
// its cable; the cap streaming live and the bridge are what a real system needs.
const CAP_PLATE: K.Plan = { x: 0, y: 0, w: 186, d: 108, r: 10 };
const HEAD = { cx: 60, cy: 56, scale: 0.6, cut: -72 };
const a0 = (AZ * Math.PI) / 180;
const POSE: HeadPose = {
  origin: [HEAD.cx, HEAD.cy, BASE + 18 - HEAD.cut * HEAD.scale],
  scale: HEAD.scale,
  nose: [Math.cos(a0) * 0.3 - Math.sin(a0) * 0.95, Math.sin(a0) * 0.3 + Math.cos(a0) * 0.95],
  cutMm: HEAD.cut,
};
const BRIDGE: K.Plan = { x: 138, y: 30, w: 36, d: 30, r: 3 };
const BRIDGE_TOP = BASE + 16;

function capArt(P: K.Projection) {
  const at = (p: K.Point3) => K.iso(p, P);
  const out: string[] = [plate(CAP_PLATE, P)];
  const head = headSvg(P, POSE);
  out.push(K.solidSvg(K.cylinder(HEAD.cx, HEAD.cy, 40, BASE, 4, P, 56, 0.6), { tone: "mid" }));
  out.push(
    K.solidSvg(
      K.cylinder(head.neck.c[0], head.neck.c[1], head.neck.r * 0.6, BASE + 4, head.neck.c[2] - BASE - 2, P, 32),
      { tone: "hi" },
    ),
  );
  // The bridge sits behind the head, so it is drawn first.
  const live: string[] = [];
  live.push(K.solidSvg(K.slabOf(BRIDGE, BASE, BRIDGE_TOP - BASE, P, 6, 0.8), { tone: "hi" }));
  live.push(K.dotsSvg([at([BRIDGE.x + 8, BRIDGE.y + BRIDGE.d, BASE + 10])], { size: 1.4, tone: "hi" }));
  const back = head.electrodes
    .filter((e) => e.visible && e.shown)
    .sort((p, q) => q.p[0] - q.p[1] - (p.p[0] - p.p[1]))[0];
  if (back) {
    const from: K.Point3 = [back.p[0] + back.n[0] * 2, back.p[1] + back.n[1] * 2, back.p[2] + back.n[2] * 2];
    const off: K.Point3 = [back.p[0] + back.n[0] * 14, back.p[1] + back.n[1] * 14, back.p[2] + back.n[2] * 14];
    const end: K.Point3 = [BRIDGE.x + 10, BRIDGE.y + BRIDGE.d / 2, BRIDGE_TOP];
    const via = [at(off), at([end[0], end[1], BRIDGE_TOP + 22])];
    live.push(K.wireSvg(at(from), at(end), { via, tone: "mid", size: 1 }));
  }
  out.push(needed(live.join("")));
  out.push(needed(head.svg, ' data-cap=""'));
  return out.join("");
}

const capBounds: K.Point3[] = [
  ...K.boxCorners(CAP_PLATE, 0, BASE),
  ...HEAD_BOUNDS.map(placeHead(POSE).world),
  ...K.boxCorners(BRIDGE, BASE, BRIDGE_TOP + 22),
];

// Practice: the patient's screen showing the cue, and beside it the server that runs the model,
// which learns from the practice.
const PRACTICE_PLATE: K.Plan = { x: 0, y: 0, w: 244, d: 100, r: 10 };
const SCREEN = { x: 15, w: 120, h: 80, d: 9, lift: 22 };
const FACE_Y = 54;
const SERVER_AT: K.Point3 = [160 - SERVER.x, PRACTICE_PLATE.d / 2 - (SERVER.y + SERVER.d / 2), 0];

function practiceArt(P: K.Projection) {
  const face = (pts: K.Point3[]) =>
    K.pathOf(
      pts.map((p) => K.iso(p, P)),
      true,
    );
  const rect = (x0: number, x1: number, za: number, zb: number) =>
    face([
      [x0, FACE_Y + 0.05, za],
      [x1, FACE_Y + 0.05, za],
      [x1, FACE_Y + 0.05, zb],
      [x0, FACE_Y + 0.05, zb],
    ]);
  const out: string[] = [plate(PRACTICE_PLATE, P)];
  const mid = SCREEN.x + SCREEN.w / 2;
  const top = BASE;
  const foot: K.Plan = { x: mid - 28, y: FACE_Y - 30, w: 56, d: 34, r: 5 };
  const neck: K.Plan = { x: mid - 7, y: FACE_Y - 22, w: 14, d: 9, r: 3 };
  const body: K.Plan = { x: SCREEN.x, y: FACE_Y - SCREEN.d, w: SCREEN.w, d: SCREEN.d, r: 3 };
  out.push(K.solidSvg(K.slabOf(foot, top, 3, P, 8, 0.5), { tone: "hi" }));
  out.push(K.solidSvg(K.slabOf(neck, top + 3, SCREEN.lift - 3, P), { tone: "hi" }));
  out.push(K.solidSvg(K.slabOf(body, top + SCREEN.lift, SCREEN.h, P, 6, 0.8), { tone: "hi" }));
  const x0 = SCREEN.x + 7;
  const x1 = SCREEN.x + SCREEN.w - 7;
  const z0 = top + SCREEN.lift + 7;
  const z1 = top + SCREEN.lift + SCREEN.h - 7;
  out.push(`<path class="screen-glass" d="${rect(x0, x1, z0, z1)}"/>`);
  const cz = (z0 + z1) / 2;
  const bw = (x1 - x0) * 0.28;
  const bh = (z1 - z0) * 0.38;
  out.push(`<path class="screen-sixth" d="${rect(mid - bw / 2, mid + bw / 2, cz - bh / 2, cz + bh / 2)}"/>`);
  out.push(moved(serverBox(P), P, SERVER_AT));
  return out.join("");
}

const practiceBounds: K.Point3[] = [
  ...K.boxCorners(PRACTICE_PLATE, 0, BASE),
  [SCREEN.x, FACE_Y, BASE + SCREEN.lift + SCREEN.h],
  [SCREEN.x + SCREEN.w, FACE_Y - SCREEN.d, BASE + SCREEN.lift + SCREEN.h],
  ...K.boxCorners({ ...SERVER, x: SERVER.x + SERVER_AT[0], y: SERVER.y + SERVER_AT[1] }, BASE, BASE + 48),
];

// Therapy: a laptop showing the switch (rest, and move lit), wired to the motor and the
// robotic finger; the finger and its wire are what a real system needs.
const THERAPY_PLATE: K.Plan = { x: 0, y: 0, w: 244, d: 108, r: 10 };
const LAPTOP_SCALE = 0.68;
const LAPTOP_AT: K.Point3 = [4, 6, 0];
const MOTOR_AT: K.Point3 = [4, -4, 0];
/** A point of the laptop's own drawing where this smaller laptop puts it. */
const lap = ([x, y, z]: K.Point3): K.Point3 => [
  x * LAPTOP_SCALE + LAPTOP_AT[0],
  y * LAPTOP_SCALE + LAPTOP_AT[1],
  BASE + (z - BASE) * LAPTOP_SCALE,
];

function therapyArt(P: K.Projection) {
  const at = (p: K.Point3) => K.iso(p, P);
  const out: string[] = [plate(THERAPY_PLATE, P)];
  const lift: K.Point3 = [LAPTOP_AT[0], LAPTOP_AT[1], BASE * (1 - LAPTOP_SCALE)];
  out.push(moved(laptopSvg(P, { pad: false, lamps: "switch" }), P, lift, LAPTOP_SCALE));
  const m = { x: MOTOR.x + MOTOR_AT[0], y: MOTOR.y + MOTOR_AT[1] };
  const from = lap([148, 80, BASE + 2]);
  const to: K.Point3 = [m.x - 10, m.y + MOTOR.d / 2, BASE + 30];
  const via = [at([from[0] + 14, from[1], BASE + 2]), at([to[0] - 12, to[1], BASE + 2])];
  const wire = K.wireSvg(at(from), at(to), { via, tone: "mid", size: 1 });
  out.push(needed(wire + moved(motorSvg(P) + fingerSvg(P), P, MOTOR_AT)));
  return out.join("");
}

const therapyBounds: K.Point3[] = [
  ...K.boxCorners(THERAPY_PLATE, 0, BASE),
  ...LAPTOP_BOUNDS.map(lap),
  ...MOTOR_FINGER_BOUNDS.map(([x, y, z]) => [x + MOTOR_AT[0], y + MOTOR_AT[1], z] as K.Point3),
];

// The next visit: a page of days with two rings, the day of the visit ringed.
const CAL: K.Plan = { x: 0, y: 0, w: 92, d: 80, r: 5 };

function calendarArt(P: K.Projection) {
  const out: string[] = [];
  out.push(K.solidSvg(K.slabOf(CAL, 0, 5, P, 6, 0.6), { tone: "hi", halo: true }));
  out.push(K.solidSvg(K.slabOf({ x: CAL.x, y: CAL.y, w: CAL.w, d: 15, r: 4 }, 5, 4, P, 6), { tone: "hi" }));
  for (const x of [26, 66]) out.push(K.solidSvg(K.cylinder(x, 7.5, 3, 9, 8, P, 16), { tone: "hi" }));
  const cells: K.Flat[] = [];
  for (let row = 0; row < 4; row++) {
    for (let col = 0; col < 6; col++) cells.push(K.iso([13 + col * 13.2, 26 + row * 13.2, 5], P));
  }
  out.push(K.dotsSvg(cells, { size: 1.6, tone: "mid" }));
  out.push(`<path class="jn-visit" d="${K.ring(13 + 4 * 13.2, 26 + 2 * 13.2, 5.6, 5, P, 24)}"/>`);
  return out.join("");
}

const calendarBounds: K.Point3[] = [...K.boxCorners(CAL, 0, 17)];

const unitView: K.Projection = { origin: [0, 0], scale: 1, azimuth: AZ };

function extent(points: K.Point3[]) {
  const flat = points.map((p) => K.iso(p, unitView));
  const xs = flat.map(([x]) => x);
  const ys = flat.map(([, y]) => y);
  return { left: Math.min(...xs), right: Math.max(...xs), up: Math.min(...ys), down: Math.max(...ys) };
}

const BOUNDS: Record<Station, K.Point3[]> = {
  cap: capBounds,
  practice: practiceBounds,
  therapy: therapyBounds,
  calendar: calendarBounds,
};

const BUILD: Record<Station, (P: K.Projection) => string> = {
  cap: capArt,
  practice: practiceArt,
  therapy: therapyArt,
  calendar: calendarArt,
};

export interface StationArt {
  svg: string;
  /** The viewBox: cut to the station's own top, so a short one carries no empty band above it. */
  y: number;
  w: number;
  h: number;
}

/**
 * Every station at one scale, each standing on the floor of a box of the same height, centred
 * across it; drawn at widths in proportion to `w`, they keep that scale and share one floor.
 */
export function journeyArt(): Record<Station, StationArt> {
  const all = Object.keys(BOUNDS) as Station[];
  const boxes = Object.fromEntries(all.map((s) => [s, extent(BOUNDS[s])])) as Record<
    Station,
    ReturnType<typeof extent>
  >;
  const scale = Math.min(...all.map((s) => (BOX_W * WIDTH[s] - PAD * 2) / (boxes[s].right - boxes[s].left)));
  const boxH = Math.ceil(Math.max(...all.map((s) => (boxes[s].down - boxes[s].up) * scale)) + PAD * 2);
  return Object.fromEntries(
    all.map((s) => {
      const b = boxes[s];
      const w = BOX_W * WIDTH[s];
      const P: K.Projection = {
        origin: [w / 2 - ((b.left + b.right) / 2) * scale, boxH - PAD - b.down * scale],
        scale,
        azimuth: AZ,
      };
      const y = Math.max(0, Math.floor(boxH - PAD * 2 - (b.down - b.up) * scale));
      return [s, { svg: BUILD[s](P), y, w, h: boxH - y }];
    }),
  ) as Record<Station, StationArt>;
}
