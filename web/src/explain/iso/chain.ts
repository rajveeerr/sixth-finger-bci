// The bench, built once: a head in an EEG cap (the template head of iso/head.ts), an
// amplifier whose pen writes the EEG on a moving paper strip, a frame that holds the
// newest 4 s of that paper, the decoder with one lamp per command, and the robotic finger
// it drives. World units are millimetres of the model; x runs along the bench, y across
// it toward the viewer, z up. The live parts (the ink on the paper, the lamps and the
// finger) are drawn by SignalChain.tsx from the same projection.
//
// It comes apart: the drawing is a list of runs in paint order, each tagged with the part
// it belongs to, so a picked part can rise off the bench as one piece while everything in
// front of it still covers it where it should.

import { HEAD_BOUNDS, headSvg, placeHead, type HeadPose } from "./head";
import * as K from "./kit";

export const VIEW_W = 1000;
export const VIEW_H = 330;
const AZIMUTH = 70;

const BENCH: K.Plan = { x: 0, y: 0, w: 676, d: 150, r: 10 };
const TOP = 12; // bench top

// The head: a real head on a short stand, three-quarter view, the nose toward the viewer's
// left, so the cap's top and the motor strip face the reader.
const HEAD = { cx: 70, cy: 76 };
const HEAD_SCALE = 0.6; // world units per millimetre of head
const HEAD_CUT = -72; // the neck stops here, in the template's millimetres
const a0 = (AZIMUTH * Math.PI) / 180;
const POSE: HeadPose = {
  origin: [HEAD.cx, HEAD.cy, TOP + 18 - HEAD_CUT * HEAD_SCALE],
  scale: HEAD_SCALE,
  nose: [Math.cos(a0) * 0.3 - Math.sin(a0) * 0.95, Math.sin(a0) * 0.3 + Math.cos(a0) * 0.95],
  cutMm: HEAD_CUT,
};

const AMP: K.Plan = { x: 150, y: 38, w: 74, d: 76, r: 5 };
const AMP_TOP = TOP + 46;

export const TRAY: K.Plan = { x: 238, y: 24, w: 244, d: 102, r: 4 };
const TRAY_TOP = TOP + 6;
export const PAPER: K.Plan = { x: 246, y: 36, w: 230, d: 76, r: 0 };
export const PAPER_Z = TRAY_TOP + 0.6;
export const PEN_X = 252; // the newest ink; older ink moves toward +x
export const SECONDS = 7.6; // seconds of EEG on the paper
export const PX_PER_S = (PAPER.x + PAPER.w - PEN_X) / SECONDS;
export const WINDOW_X1 = PEN_X + 4 * PX_PER_S; // the frame holds the newest 4 s
const RAIL_Z = TRAY_TOP + 3;
const FRAME_Z = TRAY_TOP + 8;

const DECODER: K.Plan = { x: 506, y: 34, w: 86, d: 70, r: 5 };
const DECODER_TOP = TOP + 44;
export const LAMPS = [
  { name: "rest", x: 523 },
  { name: "affected_hand", x: 549 },
  { name: "sixth_finger", x: 575 },
] as const;
const LAMP_Y = 66;

const STAND: K.Plan = { x: 612, y: 52, w: 50, d: 46, r: 4 };
const POST = { x: 637, y: 75, r: 6, top: TOP + 52 };
export const FINGER_ROOT: K.Point3 = [POST.x, POST.y, POST.top + 4];
export const LINKS = [24, 19, 15] as const;
export const LINK_R = [5.6, 5.1, 4.6] as const;

export const ROW_Y = Array.from({ length: 7 }, (_, c) => PAPER.y + 6 + ((c + 0.5) * (PAPER.d - 12)) / 7);

export const P = K.fitProjection(
  [
    ...K.boxCorners(BENCH, -8, TOP),
    [FINGER_ROOT[0] + 30, FINGER_ROOT[1], FINGER_ROOT[2] + 60],
    ...HEAD_BOUNDS.map(placeHead(POSE).world),
    [AMP.x, AMP.y, AMP_TOP + 14],
  ],
  VIEW_W,
  VIEW_H,
  { pad: 14, azimuth: AZIMUTH },
);

/** The parts the figure names, each numbered on the bench's front edge under it. */
export const PARTS = (
  [
    { id: "cap", name: "EEG cap", text: "40 sensors on the scalp pick up the brain's tiny voltage.", x: HEAD.cx },
    { id: "amp", name: "Amplifier", text: "Makes the tiny signal strong enough to record, and writes it onto the paper.", x: AMP.x + AMP.w / 2 },
    { id: "frame", name: "4 s frame", text: "Holds the newest 4 seconds of signal: what the model reads each time.", x: PEN_X + 2 * PX_PER_S },
    { id: "model", name: "Model", text: "Reads those 4 seconds and lights one lamp: rest, hand or sixth finger.", x: DECODER.x + DECODER.w / 2 },
    { id: "finger", name: "Robotic finger", text: "Bends when the sixth-finger lamp lights.", x: POST.x },
  ] as const
).map(({ x, ...part }) => ({ ...part, at: [x, BENCH.d - 13, TOP] as K.Point3 }));

export type PartId = (typeof PARTS)[number]["id"];

/** How far a picked part rises off the bench, in screen units: about 14 px where the figure is 760 px wide. */
export const LIFT = 19;
const LIFT_Z = LIFT / Math.abs(K.axisVector(P, [0, 0, 1])[1]);

/** Screen units per world unit. */
export const UNIT = Math.abs(K.axisVector(P, [0, 0, 1])[1]) / Math.cos(Math.PI / 6);

const at = (p: K.Point3) => K.iso(p, P);
const solid = (paths: K.SolidPaths, style: K.SolidStyle = {}) => K.solidSvg(paths, style);
const slab = (plan: K.Plan, z: number, h: number, bevel = 0) => K.slabOf(plan, z, h, P, 8, bevel);

/** One run of the drawing, in paint order. */
export interface Layer {
  /**
   * The bench and the paper tray stay put; a part's runs rise with it; a wire bends to keep
   * its ends on its two parts; a shadow marks where a lifted part stood; the hit areas are
   * never seen.
   */
  kind: "bench" | "hits" | "part" | "tray" | "wire" | "shadow";
  svg: string;
  /** The part a run belongs to, or the part at a wire's first end. */
  part?: PartId;
  /** The part at a wire's other end. */
  to?: PartId;
  /** For a wire: the transforms that keep its first and its other end on their parts as each lifts. */
  bend?: [string, string];
  /** Stays bright while this part is picked, without rising. */
  hold?: PartId;
  /** A live element SignalChain.tsx draws in this run. */
  live?: "ink-old" | "ink-new" | "finger";
}

export interface ChainArt {
  layers: Layer[];
}

/** The 2D affine map that lifts screen point `a` by LIFT and keeps `b` still, shearing what lies between. */
export function bend(a: K.Flat, b: K.Flat): [number, number, number, number, number, number] {
  const dx = a[0] - b[0];
  const dy = a[1] - b[1];
  const n = dx * dx + dy * dy || 1;
  const ux = dx / n;
  const uy = dy / n;
  return [1, -LIFT * ux, 0, 1 - LIFT * uy, 0, LIFT * (ux * b[0] + uy * b[1])];
}

const bendCss = (a: K.Flat, b: K.Flat) => {
  const [m0, m1, m2, m3, m4, m5] = bend(a, b);
  return `matrix(${m0}, ${m1.toFixed(5)}, ${m2}, ${m3.toFixed(5)}, ${m4}, ${m5.toFixed(3)})`;
};

export function buildChain(): ChainArt {
  const layers: Layer[] = [];
  const put = (kind: Layer["kind"], svg: string, part?: PartId) => {
    const last = layers[layers.length - 1];
    if (last && last.kind === kind && last.part === part && !last.live) last.svg += svg;
    else layers.push({ kind, svg, part });
  };
  const bench = (svg: string) => put("bench", svg);
  const tray = (svg: string) => put("tray", svg);
  const of = (part: PartId) => (svg: string) => put("part", svg, part);
  const wire = (from: PartId, to: PartId, a: K.Flat, b: K.Flat, svg: string) =>
    layers.push({ kind: "wire", svg, part: from, to, bend: [bendCss(a, b), bendCss(b, a)] });
  // A soft footprint where the part meets what it stands on: a wider pale rim and the plan itself.
  const shadow = (part: PartId, outline: (grow: number) => string) =>
    put("shadow", `<path class="part-shadow-rim" d="${outline(3)}"/><path d="${outline(-1)}"/>`, part);
  const hit = (part: PartId, d: string) => `<path data-hit="${PARTS.findIndex((p) => p.id === part)}" d="${d}"/>`;
  // A part's hit area covers it standing and lifted, so it never slides out from under the pointer.
  const hull = (plan: K.Plan, z0: number, z1: number) => K.slabOf(plan, z0, z1 - z0 + LIFT_Z, P).fill;

  // Bench: feet, a bevelled plate with a groove, corner screws and a label plate.
  const feet = K.corners(BENCH, 22).sort((a, b) => K.depthOf([a[0], a[1], 0], P) - K.depthOf([b[0], b[1], 0], P));
  for (const [x, y] of feet) {
    bench(solid(K.cylinder(x, y, 7, -8, 8, P, 24), { tone: "mid" }));
  }
  bench(solid(slab(BENCH, 0, TOP, 1.4), { tone: "mid", halo: true }));
  bench(K.lineSvg(K.planOutline(K.insetPlan(BENCH, 6), TOP, P), { tone: "faint" }));
  bench(K.dotsSvg(K.corners(BENCH, 13).map(([x, y]) => at([x, y, TOP])), { size: 1.3, tone: "mid" }));
  const plate = { x0: 270, x1: 340, z0: 3, z1: 9.5, y: BENCH.y + BENCH.d };
  bench(
    K.lineSvg(
      K.pathOf(
        [
          at([plate.x0, plate.y, plate.z0]),
          at([plate.x1, plate.y, plate.z0]),
          at([plate.x1, plate.y, plate.z1]),
          at([plate.x0, plate.y, plate.z1]),
        ],
        true,
      ),
      { tone: "mid" },
    ),
  );
  for (const z of [5, 6.6, 8]) {
    bench(K.lineSvg(K.segment([plate.x0 + 4, plate.y, z], [plate.x1 - (z === 8 ? 26 : 4), plate.y, z], P), { tone: "lo", free: true }));
  }
  // The hit areas lie under every part, so what is drawn on top (a cup's name, a nearer part) still answers first.
  const hits: Layer = { kind: "hits", svg: "" };
  layers.push(hits);

  // The head on its stand: a disc, a short post into the neck, the head in its cap.
  const cap = of("cap");
  const head = headSvg(P, POSE);
  shadow("cap", (grow) => K.ring(HEAD.cx, HEAD.cy, 44 + grow, TOP, P, 56));
  cap(solid(K.cylinder(HEAD.cx, HEAD.cy, 44, TOP, 4, P, 56, 0.6), { tone: "mid" }));
  cap(solid(K.cylinder(head.neck.c[0], head.neck.c[1], head.neck.r * 0.6, TOP + 4, head.neck.c[2] - TOP - 2, P, 32), { tone: "hi" }));
  cap(head.svg);
  const shown = head.electrodes.filter((e) => e.shown && e.visible);

  // The amplifier: body, top panel, input connector, gain knob, three lights, vents.
  const amp = of("amp");
  shadow("amp", (grow) => K.planOutline(K.insetPlan(AMP, -grow), TOP, P));
  amp(solid(slab(AMP, TOP, AMP_TOP - TOP, 1.2), { tone: "hi" }));
  amp(K.lineSvg(K.planOutline(K.insetPlan(AMP, 6), AMP_TOP, P), { tone: "faint" }));
  amp(K.dotsSvg(K.corners(AMP, 3.2).map(([x, y]) => at([x, y, AMP_TOP])), { size: 0.9, tone: "mid" }));
  const input: K.Plan = { x: AMP.x + 8, y: AMP.y + 18, w: 14, d: 40, r: 2 };
  amp(solid(slab(input, AMP_TOP, 4), { tone: "hi" }));
  amp(K.dotsSvg(Array.from({ length: 7 }, (_, i) => at([input.x + 7, input.y + 5 + i * 5, AMP_TOP + 4])), { size: 1.1, tone: "hi" }));
  amp(solid(K.cylinder(AMP.x + 52, AMP.y + 24, 9, AMP_TOP, 7, P, 32, 0.6), { tone: "hi" }));
  amp(K.lineSvg(K.knurl(AMP.x + 52, AMP.y + 24, 9, AMP_TOP, AMP_TOP + 7, 36, P), { tone: "lo" }));
  amp(K.lineSvg(K.segment([AMP.x + 52, AMP.y + 24, AMP_TOP + 7], [AMP.x + 52 + 6, AMP.y + 24 - 3, AMP_TOP + 7], P), { tone: "hi" }));
  amp(K.dotsSvg([0, 1, 2].map((i) => at([AMP.x + 44 + i * 8, AMP.y + 58, AMP_TOP])), { size: 1.6, tone: "hi" }));
  for (let i = 0; i < 6; i++) {
    const y = AMP.y + 18 + i * 8;
    amp(K.lineSvg(K.segment([AMP.x + AMP.w, y, TOP + 12], [AMP.x + AMP.w, y, TOP + 30], P), { tone: "lo" }));
  }

  // The leads: from each drawn electrode in view, off the cap and gathered side by side
  // as a ribbon into the amplifier's input connector.
  const ribbonZ = AMP_TOP + 22;
  [...shown]
    .sort((p, q) => p.p[1] - q.p[1])
    .forEach((e, i) => {
      const from: K.Point3 = [e.p[0] + e.n[0] * 2, e.p[1] + e.n[1] * 2, e.p[2] + e.n[2] * 2];
      const off: K.Point3 = [e.p[0] + e.n[0] * 9, e.p[1] + e.n[1] * 9, e.p[2] + e.n[2] * 9];
      const end: K.Point3 = [input.x + 7, input.y + 5 + i * 5, AMP_TOP + 4];
      const gather: K.Point3 = [input.x - 10, end[1], ribbonZ];
      wire("cap", "amp", at(from), at(end), K.wireSvg(at(from), at(end), { via: [at(off), at(gather)], tone: "mid", size: 1 }));
    });

  // The paper tray, the paper and the time scale along its front edge, 1 s apart.
  tray(solid(slab(TRAY, TOP, TRAY_TOP - TOP, 0.8), { tone: "mid" }));
  tray(solid(slab(PAPER, TRAY_TOP, 0.6), { tone: "lo", flat: true, lit: true }));
  tray(K.lineSvg(K.planOutline(PAPER, PAPER_Z, P), { tone: "lo" }));
  layers.push({ kind: "tray", svg: "", live: "ink-old" });
  // The newest ink stays dark while the frame is picked: it is what the frame holds.
  layers.push({ kind: "tray", svg: "", live: "ink-new", hold: "frame" });

  const ticks = K.topTicks(PEN_X, PAPER.x + PAPER.w, PX_PER_S / 5, 5, PAPER.y + PAPER.d + 1.5, TRAY_TOP, [2.5, 6], P);
  tray(K.lineSvg(ticks.minor, { tone: "lo" }) + K.lineSvg(ticks.major, { tone: "mid" }));

  // The pen: an arm from the amplifier's side to the paper's edge, and its tip.
  const arm: K.Plan = { x: AMP.x + AMP.w, y: 72, w: PEN_X - (AMP.x + AMP.w) + 2, d: 8, r: 2 };
  amp(solid(K.cylinder(PEN_X - 2, 76, 2.4, PAPER_Z, TOP + 26 - PAPER_Z, P, 16), { tone: "hi" }));
  amp(solid(slab(arm, TOP + 26, 4), { tone: "hi" }));

  // The window: rails on both edges of the tray and a frame over the newest 4 s.
  const rails = [TRAY.y + 2, TRAY.y + TRAY.d - 7];
  for (const y of rails) tray(solid(slab({ x: TRAY.x + 4, y, w: TRAY.w - 8, d: 5, r: 1 }, TRAY_TOP, RAIL_Z - TRAY_TOP), { tone: "mid" }));
  const frame = of("frame");
  const fx0 = PEN_X + 1;
  const fx1 = WINDOW_X1 + 1;
  const fy0 = TRAY.y + 1;
  const fy1 = TRAY.y + TRAY.d - 1;
  const bar = 4.5;
  const bars: K.Plan[] = [
    { x: fx0, y: fy0, w: fx1 - fx0 + bar, d: bar, r: 1 },
    { x: fx0, y: fy0, w: bar, d: fy1 - fy0, r: 1 },
    { x: fx1, y: fy0, w: bar, d: fy1 - fy0, r: 1 },
    { x: fx0, y: fy1 - bar, w: fx1 - fx0 + bar, d: bar, r: 1 },
  ];
  shadow("frame", (grow) => bars.map((b) => K.planOutline(K.insetPlan(b, -grow - 1), RAIL_Z, P)).join(""));
  for (const b of bars) frame(solid(slab(b, RAIL_Z, FRAME_Z - RAIL_Z), { tone: "hi" }));
  frame(K.dotsSvg([[fx0 + bar / 2, fy0 + bar / 2], [fx1 + bar / 2, fy0 + bar / 2], [fx0 + bar / 2, fy1 - bar / 2], [fx1 + bar / 2, fy1 - bar / 2]].map(([x, y]) => at([x, y, FRAME_Z])), { size: 1.1, tone: "hi" }));

  // The decoder: body, lid seam, three lamp bezels, the input socket and its lead.
  const model = of("model");
  shadow("model", (grow) => K.planOutline(K.insetPlan(DECODER, -grow), TOP, P));
  model(solid(slab(DECODER, TOP, DECODER_TOP - TOP, 1.2), { tone: "hi" }));
  model(K.lineSvg(K.sideSeam(DECODER, DECODER_TOP - 6, P), { tone: "faint" }));
  model(K.dotsSvg(K.corners(DECODER, 3.2).map(([x, y]) => at([x, y, DECODER_TOP])), { size: 0.9, tone: "mid" }));
  for (let i = 0; i < 5; i++) {
    const y = DECODER.y + 12 + i * 6;
    model(K.lineSvg(K.segment([DECODER.x + DECODER.w, y, TOP + 24], [DECODER.x + DECODER.w, y, TOP + 34], P), { tone: "lo" }));
  }
  const socket: K.Plan = { x: DECODER.x + 6, y: DECODER.y + 8, w: 12, d: 12, r: 2 };
  model(solid(slab(socket, DECODER_TOP, 4), { tone: "hi" }));
  for (const lamp of LAMPS) {
    model(solid(K.cylinder(lamp.x, LAMP_Y, 10, DECODER_TOP, 3, P, 32, 0.5), { tone: "hi" }));
    model(`<path class="lamp" data-class="${lamp.name}" d="${K.planOutline({ x: lamp.x - 7, y: LAMP_Y - 7, w: 14, d: 14, r: 7 }, DECODER_TOP + 3, P)}"/>`);
  }
  model(K.faceTextSvg(K.sideMatrix([DECODER.x + 10, DECODER.y + DECODER.d], TOP + 14, P, "left"), "EEGNet", { size: 6, tone: "mid" }));
  const fromFrame: K.Point3 = [fx1 + bar / 2, fy0 + bar / 2, FRAME_Z];
  const toSocket: K.Point3 = [socket.x + 6, socket.y + 6, DECODER_TOP + 4];
  wire(
    "frame",
    "model",
    at(fromFrame),
    at(toSocket),
    K.wireSvg(at(fromFrame), at(toSocket), {
      via: [at([fromFrame[0], fromFrame[1], FRAME_Z + 14]), at([toSocket[0] - 30, toSocket[1], DECODER_TOP + 14])],
      tone: "hi",
      size: 1.4,
    }),
  );

  // The finger's stand and post, and the lead from the decoder.
  const finger = of("finger");
  shadow("finger", (grow) => K.planOutline(K.insetPlan(STAND, -grow), TOP, P));
  finger(solid(slab(STAND, TOP, 8, 0.8), { tone: "hi" }));
  finger(K.dotsSvg(K.corners(STAND, 6).map(([x, y]) => at([x, y, TOP + 8])), { size: 1.1, tone: "mid" }));
  const outFrom: K.Point3 = [DECODER.x + DECODER.w, DECODER.y + 40, TOP + 18];
  const outTo: K.Point3 = [STAND.x + 8, STAND.y + 30, TOP + 8];
  wire("model", "finger", at(outFrom), at(outTo), K.wireSvg(at(outFrom), at(outTo), { via: [at([STAND.x - 6, outFrom[1], TOP + 18])], tone: "hi", size: 1.4 }));
  finger(solid(K.cylinder(POST.x, POST.y, POST.r, TOP + 8, POST.top - TOP - 8, P, 28, 0.6), { tone: "hi" }));
  finger(solid(K.cylinder(POST.x, POST.y, POST.r + 2, POST.top - 4, 4, P, 28, 0.5), { tone: "hi" }));
  layers.push({ kind: "part", svg: "", part: "finger", live: "finger" });

  const headPoints = HEAD_BOUNDS.map(placeHead(POSE).world);
  const reach = Math.max(44, ...headPoints.map(([x, y]) => Math.hypot(x - HEAD.cx, y - HEAD.cy)));
  const crown = Math.max(...headPoints.map((p) => p[2]));
  hits.svg = [
    hit("cap", K.cylinder(HEAD.cx, HEAD.cy, reach, TOP, crown - TOP + LIFT_Z, P, 32).fill),
    hit("amp", hull(AMP, TOP, AMP_TOP + 8)),
    hit("amp", hull({ ...arm, y: arm.y - 3, d: arm.d + 6 }, PAPER_Z, TOP + 30)),
    hit("frame", hull({ x: fx0, y: fy0, w: fx1 - fx0 + bar, d: fy1 - fy0, r: 0 }, RAIL_Z, FRAME_Z)),
    hit("model", hull(DECODER, TOP, DECODER_TOP + 4)),
    hit("finger", hull({ ...STAND, w: BENCH.w - STAND.x - 2 }, TOP, FINGER_ROOT[2] + LINKS.reduce((s, l) => s + l, 0))),
  ].join("");

  return { layers };
}

/** The finger's joints in the plane of x and z: angles in radians, positive curls toward +x. */
export function fingerPoints(angles: readonly number[]): K.Point3[] {
  const pts: K.Point3[] = [FINGER_ROOT];
  let a = 0;
  let x = FINGER_ROOT[0];
  let z = FINGER_ROOT[2];
  const y = FINGER_ROOT[1];
  LINKS.forEach((len, i) => {
    a += angles[i];
    x += Math.sin(a) * len;
    z += Math.cos(a) * len;
    pts.push([x, y, z]);
  });
  return pts;
}

export const project = at;
