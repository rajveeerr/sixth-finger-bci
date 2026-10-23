// A patient's path through a real system as four stations in the bench's finish, each part of
// the system drawn once: the cap and its amplifier going on, the practice at the laptop with the
// server beside it, therapy with the finger, and the calendar of the next visit. All share one
// camera and one scale, and each stands on the floor of a box of the same height, so they line
// up as a timeline. What this project has not built is drawn inside a `data-needed` group,
// dashed by the page.

import * as K from "./kit";
import {
  BASE,
  FINGER_RIG_BOUNDS,
  fingerRigArt,
  HEADSET_BOUNDS,
  headsetArt,
  LAPTOP_BOUNDS,
  laptopSvg,
  SERVER,
  SERVER_TOP,
  serverBox,
} from "./parts";

export type Station = "cap" | "practice" | "therapy" | "calendar";

const AZ = 62;
const PAD = 6;
/** The widest station's width, in viewBox units; the others keep its scale. */
const WIDEST = 280;

const plate = (p: K.Plan, P: K.Projection) => K.solidSvg(K.slabOf(p, 0, BASE, P, 8, 0.8), { tone: "mid", halo: true });

/** Draws a group made for one place in the world at another, `by` world units away. */
function moved(svg: string, P: K.Projection, by: K.Point3) {
  const [dx, dy] = K.axisVector(P, by);
  return `<g transform="translate(${dx.toFixed(2)} ${dy.toFixed(2)})">${svg}</g>`;
}

// Practice: the laptop showing this page, its bridge program in a corner, and beside it the
// server that runs the model, which learns from the practice.
const PRACTICE_PLATE: K.Plan = { x: 0, y: 0, w: 252, d: 112, r: 10 };
const SERVER_AT: K.Point3 = [170 - SERVER.x, PRACTICE_PLATE.d / 2 + 4 - (SERVER.y + SERVER.d / 2), 0];

const practiceArt = (P: K.Projection) => plate(PRACTICE_PLATE, P) + laptopSvg(P) + moved(serverBox(P), P, SERVER_AT);

const practiceBounds: K.Point3[] = [
  ...K.boxCorners(PRACTICE_PLATE, 0, BASE),
  ...LAPTOP_BOUNDS,
  ...K.boxCorners({ ...SERVER, x: SERVER.x + SERVER_AT[0], y: SERVER.y + SERVER_AT[1] }, BASE, SERVER_TOP),
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
  cap: HEADSET_BOUNDS,
  practice: practiceBounds,
  therapy: FINGER_RIG_BOUNDS,
  calendar: calendarBounds,
};

const BUILD: Record<Station, (P: K.Projection) => string> = {
  cap: headsetArt,
  practice: practiceArt,
  therapy: fingerRigArt,
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
 * Every station at one scale, each standing on the floor of a box of the same height; drawn at
 * widths in proportion to `w`, they keep that scale and share one floor.
 */
export function journeyArt(): Record<Station, StationArt> {
  const all = Object.keys(BOUNDS) as Station[];
  const boxes = Object.fromEntries(all.map((s) => [s, extent(BOUNDS[s])])) as Record<
    Station,
    ReturnType<typeof extent>
  >;
  const scale = (WIDEST - PAD * 2) / Math.max(...all.map((s) => boxes[s].right - boxes[s].left));
  const boxH = Math.ceil(Math.max(...all.map((s) => (boxes[s].down - boxes[s].up) * scale)) + PAD * 2);
  return Object.fromEntries(
    all.map((s) => {
      const b = boxes[s];
      const w = Math.ceil((b.right - b.left) * scale + PAD * 2);
      const P: K.Projection = { origin: [PAD - b.left * scale, boxH - PAD - b.down * scale], scale, azimuth: AZ };
      const y = Math.max(0, Math.floor(boxH - PAD * 2 - (b.down - b.up) * scale));
      return [s, { svg: BUILD[s](P), y, w, h: boxH - y }];
    }),
  ) as Record<Station, StationArt>;
}
