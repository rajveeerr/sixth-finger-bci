// The parts of a real system in the bench's finish, each drawn once for the patient's path: the
// wearer's head in an EEG cap wired to an amplifier, the laptop, the server that runs the model,
// and a finger board wired to the motor of the robotic finger. What this project has not built
// sits in a `data-needed` group, which the page draws dashed.

import { headSvg, HEAD_BOUNDS, placeHead, type HeadPose } from "./head";
import * as K from "./kit";

const AZ = 62;
export const BASE = 6; // the height of each station's plate

/** What a real system needs and this project has not built, drawn dashed by the page. */
export const needed = (svg: string, extra = "") => `<g data-needed=""${extra}>${svg}</g>`;

/**
 * A laptop, its screen showing the three lamps with the sixth finger's lit, and in a corner a
 * small window for the bridge program, which is not built.
 */
export function laptopSvg(P: K.Projection) {
  const out: string[] = [];
  // the laptop's base, keyboard rows and the screen standing behind it
  const base: K.Plan = { x: 12, y: 40, w: 136, d: 62, r: 5 };
  out.push(K.solidSvg(K.slabOf(base, 6, 5, P, 6, 0.6), { tone: "hi" }));
  for (let row = 0; row < 4; row++) {
    const y = base.y + 10 + row * 9;
    out.push(K.lineSvg(K.lineOnTop([base.x + 14, y], [base.x + base.w - 14, y], 11, P), { tone: "faint" }));
  }
  out.push(K.solidSvg(K.slabOf({ x: 12, y: 32, w: 136, d: 8, r: 3 }, 6, 100, P, 6, 0.6), { tone: "hi" }));
  const fy = 40.05;
  const face = (pts: K.Point3[]) =>
    K.pathOf(
      pts.map((p) => K.iso(p, P)),
      true,
    );
  out.push(
    `<path class="screen-glass" d="${face([
      [20, fy, 14],
      [140, fy, 14],
      [140, fy, 98],
      [20, fy, 98],
    ])}"/>`,
  );
  const shown = [
    { x: 50, r: 9, cls: "pc-lamp" },
    { x: 80, r: 9, cls: "pc-lamp" },
    { x: 110, r: 9, cls: "pc-lamp pc-lamp-on" },
  ];
  shown.forEach((l) => {
    const ring = Array.from({ length: 24 }, (_, i) => {
      const t = (i / 24) * Math.PI * 2;
      return [l.x + Math.cos(t) * l.r, fy, 56 + Math.sin(t) * l.r] as K.Point3;
    });
    out.push(`<path class="${l.cls}" d="${face(ring)}"/>`);
  });
  const win = face([
    [24, fy, 72],
    [52, fy, 72],
    [52, fy, 93],
    [24, fy, 93],
  ]);
  const bar = K.segment([24, fy, 88], [52, fy, 88], P);
  out.push(needed(`<path class="screen-window" d="${win}"/><path class="screen-window-bar" d="${bar}"/>`));
  return out.join("");
}

/** The points a laptop drawing must keep in view. */
export const LAPTOP_BOUNDS: K.Point3[] = [
  ...K.boxCorners({ x: 12, y: 40, w: 136, d: 62, r: 0 }, BASE, BASE + 5),
  ...K.boxCorners({ x: 12, y: 32, w: 136, d: 8, r: 0 }, BASE, BASE + 100),
];

// The head: three-quarter view with the nose toward the viewer's left, as on the bench.
const READ_PLATE: K.Plan = { x: 0, y: 0, w: 214, d: 124, r: 10 };
const HEAD = { cx: 58, cy: 64, scale: 0.6, cut: -72 };
const a0 = (AZ * Math.PI) / 180;
const POSE: HeadPose = {
  origin: [HEAD.cx, HEAD.cy, BASE + 18 - HEAD.cut * HEAD.scale],
  scale: HEAD.scale,
  nose: [Math.cos(a0) * 0.3 - Math.sin(a0) * 0.95, Math.sin(a0) * 0.3 + Math.cos(a0) * 0.95],
  cutMm: HEAD.cut,
};
const AMP: K.Plan = { x: 128, y: 34, w: 70, d: 70, r: 5 };
const AMP_TOP = BASE + 42;

export const HEADSET_BOUNDS: K.Point3[] = [
  ...K.boxCorners(READ_PLATE, 0, BASE),
  ...HEAD_BOUNDS.map(placeHead(POSE).world),
  [AMP.x, AMP.y, AMP_TOP + 14],
];

/** The wearer on a stand in the cap, wired to the amplifier: the wearer solid, the rest dashed. */
export function headsetArt(P: K.Projection) {
  const at = (p: K.Point3) => K.iso(p, P);
  const out: string[] = [];
  out.push(K.solidSvg(K.slabOf(READ_PLATE, 0, BASE, P, 8, 0.8), { tone: "mid", halo: true }));
  const head = headSvg(P, POSE);
  out.push(K.solidSvg(K.cylinder(HEAD.cx, HEAD.cy, 40, BASE, 4, P, 56, 0.6), { tone: "mid" }));
  out.push(
    K.solidSvg(
      K.cylinder(head.neck.c[0], head.neck.c[1], head.neck.r * 0.6, BASE + 4, head.neck.c[2] - BASE - 2, P, 32),
      { tone: "hi" },
    ),
  );
  out.push(needed(head.svg, ' data-cap=""'));

  // the amplifier: body, top panel, input connector, gain knob, three lights, vents
  const amp: string[] = [];
  amp.push(K.solidSvg(K.slabOf(AMP, BASE, AMP_TOP - BASE, P, 8, 1.2), { tone: "hi" }));
  amp.push(K.lineSvg(K.planOutline(K.insetPlan(AMP, 6), AMP_TOP, P), { tone: "faint" }));
  amp.push(
    K.dotsSvg(
      K.corners(AMP, 3.2).map(([x, y]) => at([x, y, AMP_TOP])),
      { size: 0.9, tone: "mid" },
    ),
  );
  const shown = head.electrodes.filter((e) => e.shown && e.visible).sort((p, q) => p.p[1] - q.p[1]);
  const input: K.Plan = { x: AMP.x + 8, y: AMP.y + 14, w: 14, d: 42, r: 2 };
  const pin = (i: number) => input.y + 5 + (i * (input.d - 10)) / Math.max(1, shown.length - 1);
  amp.push(K.solidSvg(K.slabOf(input, AMP_TOP, 4, P), { tone: "hi" }));
  amp.push(
    K.dotsSvg(
      shown.map((_, i) => at([input.x + 7, pin(i), AMP_TOP + 4])),
      { size: 1.1, tone: "hi" },
    ),
  );
  amp.push(K.solidSvg(K.cylinder(AMP.x + 48, AMP.y + 24, 8, AMP_TOP, 6, P, 32, 0.6), { tone: "hi" }));
  amp.push(K.lineSvg(K.knurl(AMP.x + 48, AMP.y + 24, 8, AMP_TOP, AMP_TOP + 6, 36, P), { tone: "lo" }));
  amp.push(
    K.dotsSvg(
      [0, 1, 2].map((i) => at([AMP.x + 40 + i * 8, AMP.y + 54, AMP_TOP])),
      { size: 1.6, tone: "hi" },
    ),
  );
  for (let i = 0; i < 6; i++) {
    const y = AMP.y + 16 + i * 8;
    amp.push(K.lineSvg(K.segment([AMP.x + AMP.w, y, BASE + 12], [AMP.x + AMP.w, y, BASE + 28], P), { tone: "lo" }));
  }

  // the leads: off each drawn electrode in view, gathered side by side into the input
  shown.forEach((e, i) => {
    const from: K.Point3 = [e.p[0] + e.n[0] * 2, e.p[1] + e.n[1] * 2, e.p[2] + e.n[2] * 2];
    const off: K.Point3 = [e.p[0] + e.n[0] * 9, e.p[1] + e.n[1] * 9, e.p[2] + e.n[2] * 9];
    const end: K.Point3 = [input.x + 7, pin(i), AMP_TOP + 4];
    const gather: K.Point3 = [input.x - 10, end[1], AMP_TOP + 22];
    amp.push(K.wireSvg(at(from), at(end), { via: [at(off), at(gather)], tone: "mid", size: 1 }));
  });
  out.push(needed(amp.join("")));
  return out.join("");
}

// The server: a small box running the model, its name on the front.
export const SERVER: K.Plan = { x: 16, y: 18, w: 64, d: 54, r: 4 };
export const SERVER_TOP = BASE + 48;

/** The server box alone, standing at SERVER on a plate BASE high. */
export function serverBox(P: K.Projection) {
  const at = (p: K.Point3) => K.iso(p, P);
  const out: string[] = [];
  out.push(K.solidSvg(K.slabOf(SERVER, BASE, SERVER_TOP - BASE, P, 8, 1.2), { tone: "hi" }));
  out.push(K.lineSvg(K.sideSeam(SERVER, SERVER_TOP - 7, P), { tone: "faint" }));
  out.push(K.lineSvg(K.planOutline(K.insetPlan(SERVER, 6), SERVER_TOP, P), { tone: "faint" }));
  out.push(
    K.dotsSvg(
      K.corners(SERVER, 3.2).map(([x, y]) => at([x, y, SERVER_TOP])),
      { size: 0.9, tone: "mid" },
    ),
  );
  const front = SERVER.y + SERVER.d;
  for (let i = 0; i < 7; i++) {
    const x = SERVER.x + 30 + i * 4.5;
    out.push(K.lineSvg(K.segment([x, front, BASE + 8], [x, front, BASE + 20], P), { tone: "lo" }));
  }
  out.push(K.dotsSvg([at([SERVER.x + 10, front, SERVER_TOP - 14])], { size: 1.6, tone: "hi" }));
  out.push(
    K.faceTextSvg(K.sideMatrix([SERVER.x + 16, front], SERVER_TOP - 12, P, "left"), "EEGNet", { size: 6, tone: "mid" }),
  );
  for (let i = 0; i < 5; i++) {
    const y = SERVER.y + 12 + i * 7;
    out.push(
      K.lineSvg(K.segment([SERVER.x + SERVER.w, y, BASE + 22], [SERVER.x + SERVER.w, y, BASE + 34], P), {
        tone: "lo",
      }),
    );
  }
  return out.join("");
}

// The finger board, the motor and the robotic finger: the bench's links, a little larger,
// on a small motor.
const ACT_PLATE: K.Plan = { x: 0, y: 0, w: 206, d: 120, r: 10 };
const BOARD: K.Plan = { x: 16, y: 32, w: 74, d: 56, r: 3 };
const BOARD_Z = BASE + 6;
const PIN_X = (i: number) => BOARD.x + 20 + i * 5.6;
const MOTOR: K.Plan = { x: 124, y: 48, w: 54, d: 34, r: 2.5 };
const MOTOR_TOP = BASE + 42;
const SHAFT: K.Plane = [161, 65];
const FINGER_ROOT: K.Point3 = [SHAFT[0], SHAFT[1], MOTOR_TOP + 7];
const LINKS = [40, 32, 25] as const;
const LINK_R = [8.4, 7.8, 7.1] as const;
const BENT = [0.35, 0.5, 0.45];

function fingerJoints(): K.Point3[] {
  const pts: K.Point3[] = [FINGER_ROOT];
  let [x, , z] = FINGER_ROOT;
  let a = 0;
  LINKS.forEach((len, i) => {
    a += BENT[i];
    x += Math.sin(a) * len;
    z += Math.cos(a) * len;
    pts.push([x, FINGER_ROOT[1], z]);
  });
  return pts;
}

export const FINGER_RIG_BOUNDS: K.Point3[] = [
  ...K.boxCorners(ACT_PLATE, 0, BASE),
  ...fingerJoints().map(([x, y, z]) => [x + 8, y, z + 8] as K.Point3),
];

/** The finger board wired to the motor and its finger, on a plate: the plate solid, the rest dashed. */
export function fingerRigArt(P: K.Projection) {
  const at = (p: K.Point3) => K.iso(p, P);
  const out: string[] = [];
  const plate = K.solidSvg(K.slabOf(ACT_PLATE, 0, BASE, P, 8, 0.8), { tone: "mid", halo: true });

  // the board on four standoffs: its chip, two rows of header pins, a USB socket and a light
  const stands = K.corners(BOARD, 4).sort((p, q) => K.depthOf([...p, 0], P) - K.depthOf([...q, 0], P));
  for (const [x, y] of stands) out.push(K.solidSvg(K.cylinder(x, y, 2.6, BASE, 6, P, 16), { tone: "mid" }));
  out.push(K.solidSvg(K.slabOf(BOARD, BOARD_Z, 2.4, P, 6, 0.4), { tone: "hi" }));
  const top = BOARD_Z + 2.4;
  out.push(K.solidSvg(K.slabOf({ x: 11, y: 52, w: 14, d: 16, r: 1 }, top, 5, P), { tone: "hi" }));
  out.push(K.solidSvg(K.slabOf({ x: 42, y: 50, w: 22, d: 22, r: 1 }, top, 3, P), { tone: "hi" }));
  const header = (y: number) => Array.from({ length: 10 }, (_, i) => at([PIN_X(i), y, top]));
  out.push(K.dotsSvg([...header(BOARD.y + 6), ...header(BOARD.y + BOARD.d - 6)], { size: 1.1, tone: "hi" }));
  out.push(K.dotsSvg([at([BOARD.x + 10, BOARD.y + BOARD.d - 12, top])], { size: 1.6, tone: "hi" }));

  out.push(motorSvg(P));
  // three leads from the board's header to the motor
  [0, 1, 2].forEach((i) => {
    const from: K.Point3 = [PIN_X(7 + i), BOARD.y + BOARD.d - 6, top];
    const to: K.Point3 = [MOTOR.x + 8 + i * 3.5, MOTOR.y + MOTOR.d, BASE + 14];
    out.push(
      K.wireSvg(at(from), at(to), {
        via: [at([from[0], from[1], top + 12]), at([to[0] - 12, to[1] + 5, BASE + 19])],
        tone: "mid",
        size: 0.9,
      }),
    );
  });
  out.push(fingerSvg(P));
  return plate + needed(out.join(""));
}

/** The motor at MOTOR on a plate BASE high: body, mounting tabs and the shaft. */
function motorSvg(P: K.Projection) {
  const out: string[] = [];
  out.push(K.solidSvg(K.slabOf(MOTOR, BASE, MOTOR_TOP - BASE, P, 6, 0.8), { tone: "hi" }));
  const tabs: K.Plan = { x: MOTOR.x - 10, y: MOTOR.y, w: MOTOR.w + 20, d: MOTOR.d, r: 1.5 };
  out.push(K.solidSvg(K.slabOf(tabs, MOTOR_TOP - 10, 3, P), { tone: "hi" }));
  out.push(K.solidSvg(K.cylinder(SHAFT[0], SHAFT[1], 8.5, MOTOR_TOP, 3.5, P, 28, 0.5), { tone: "hi" }));
  out.push(K.solidSvg(K.cylinder(SHAFT[0], SHAFT[1], 5.5, MOTOR_TOP + 3.5, 3.5, P, 24), { tone: "hi" }));
  return out.join("");
}

/** The robotic finger bent on the motor's shaft, its light strip lit, drawn as the bench draws it. */
function fingerSvg(P: K.Projection) {
  const at = (p: K.Point3) => K.iso(p, P);
  const unit = Math.abs(K.axisVector(P, [0, 0, 1])[1]) / Math.cos(Math.PI / 6);
  const pts = fingerJoints().map(at);
  const seg = (i: number) => K.pathOf([pts[i], pts[i + 1]]);
  const width = (w: number) => (w * unit).toFixed(2);
  const links = [
    ...LINK_R.map((r, i) => `<path class="link-edge" stroke-width="${width(r * 2 + 1.8 / unit)}" d="${seg(i)}"/>`),
    ...LINK_R.map((r, i) => `<path class="link-body" stroke-width="${width(r * 2)}" d="${seg(i)}"/>`),
    ...LINK_R.map((_, i) => `<path class="link-strip" stroke-width="${width(2.6)}" d="${seg(i)}"/>`),
    ...pts.map(([x, y], i) => {
      const r = i === 3 ? LINK_R[2] * 0.7 : LINK_R[i] * 0.32;
      return `<circle class="${i === 3 ? "link-tip" : "link-pin"}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${width(r)}"/>`;
    }),
  ];
  return `<g class="finger" data-active="">${links.join("")}</g>`;
}
