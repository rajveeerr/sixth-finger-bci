// EEGNet drawn as five small stations: a card with the 4 s the model reads, then its four
// steps as instruments, each showing on its front what comes out of it, the last with the
// three lamps. Every station is its own SVG so the row can run down the page on a phone;
// they share one projection, so they are drawn at the same scale. The signal on the card
// and the shapes on the panels are drawings; the sizes in STAGES are the real model's.

import { data } from "../data";
import * as K from "./kit";

export const VIEW_W = 240;
export const VIEW_H = 196;
const AZIMUTH = 58;

const PAD: K.Plan = { x: -12, y: -6, w: 144, d: 80, r: 9 };
const PAD_H = 5;
const BOX: K.Plan = { x: 0, y: 6, w: 120, d: 52, r: 4 };
const BOX_TOP = PAD_H + 70;
const FRONT_Y = BOX.y + BOX.d;
// The card stands in a slotted foot, as tall as an instrument.
const FOOT: K.Plan = { x: 2, y: 34, w: 116, d: 22, r: 4 };
const FOOT_TOP = PAD_H + 7;
const CARD: K.Plan = { x: 4, y: 43, w: 112, d: 3, r: 0.6 };
const CARD_TOP = FOOT_TOP + 70;

const P = K.fitProjection(
  [...K.boxCorners(PAD, 0, PAD_H), ...K.boxCorners(BOX, PAD_H, BOX_TOP), ...K.boxCorners(CARD, FOOT_TOP, CARD_TOP)],
  VIEW_W,
  VIEW_H,
  { pad: 8, azimuth: AZIMUTH },
);

/**
 * EEGNet as the browser runs it (public/demo/model.onnx, braindecode's defaults: F1 = 8,
 * D = 2, F2 = 16, kernel 64), read from the exported graph. `learned` counts each step's
 * weights there, where the batch norms are folded into the convolutions; the four add up
 * to data.demo.parameters.
 */
export const STAGES = {
  rhythms: { filters: 8, kernel: 64, learned: 8 * 64 + 8 },
  sensors: { perFilter: 2, outputs: 16, pool: 4, learned: 16 * 40 + 16 },
  combine: { kernel: 16, outputs: 16, pool: 8, steps: 31, learned: 16 * 16 + 16 * 16 + 16 },
  decide: { classes: 3, learned: 3 * 16 * 31 + 3 },
} as const;
export const SFREQ = 250;
export const CHANNELS = 40;
export const WINDOW_S = 4;

const at = (p: K.Point3) => K.iso(p, P);

/** A small deterministic generator, so the drawing is the same on every visit. */
function seeded(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const f1 = (v: number) => (Math.round(v * 10) / 10).toString();
const poly = (pts: [number, number][]) => pts.map(([x, y], i) => `${i ? "L" : "M"}${f1(x)} ${f1(y)}`).join("");

/** Drawing coordinates on a front face: u along the face from its left edge, v down from its top. */
const onFace = (x0: number, y: number, top: number, inner: string) =>
  `<g transform="${K.sideMatrix([x0, y], top, P, "left")}">${inner}</g>`;

function pad() {
  return K.solidSvg(K.slabOf(PAD, 0, PAD_H, P, 8, 0.6), { tone: "mid", halo: true });
}

function instrument(face: string) {
  const out: string[] = [pad()];
  out.push(K.solidSvg(K.slabOf(BOX, PAD_H, BOX_TOP - PAD_H, P, 6, 1), { tone: "hi" }));
  out.push(K.lineSvg(K.planOutline(K.insetPlan(BOX, 7), BOX_TOP, P), { tone: "faint" }));
  out.push(
    K.dotsSvg(
      K.corners(BOX, 3.4).map(([x, y]) => at([x, y, BOX_TOP])),
      { size: 0.9, tone: "mid" },
    ),
  );
  for (let i = 0; i < 4; i++) {
    const y = BOX.y + 14 + i * 7;
    out.push(K.lineSvg(K.segment([BOX.x + BOX.w, y, PAD_H + 22], [BOX.x + BOX.w, y, PAD_H + 48], P), { tone: "lo" }));
  }
  const panel = `<rect class="mdraw-panel" x="7" y="7" width="${BOX.w - 14}" height="${BOX_TOP - PAD_H - 14}" rx="2.5"/>`;
  out.push(onFace(BOX.x, FRONT_Y, BOX_TOP, panel + face));
  return out.join("");
}

/** 40 lines that look like a few seconds of EEG: shared slow rhythms, each sensor's own mix and noise. */
function eegLines(width: number, height: number, inset: number) {
  const rand = seeded(40);
  const n = 110; // about one point per pixel of the card on a wide screen
  const sources = Array.from({ length: 4 }, (_, k) => ({
    f: [2.2, 5.5, 9.5, 17][k],
    phase: rand() * Math.PI * 2,
    wobble: rand() * Math.PI * 2,
  }));
  const gap = (height - inset * 2) / CHANNELS;
  const lines: string[] = [];
  for (let c = 0; c < CHANNELS; c++) {
    const mix = sources.map((_, k) => (0.35 + rand() * 0.65) * [0.5, 0.3, 0.38, 0.14][k]);
    const y0 = inset + gap * (c + 0.5);
    const pts: [number, number][] = [];
    for (let i = 0; i <= n; i++) {
      const t = (i / n) * WINDOW_S;
      let v = (rand() - 0.5) * 0.4;
      sources.forEach((s, k) => {
        const swell = 0.6 + 0.4 * Math.sin(t * 0.9 + s.wobble + c * 0.05);
        v += mix[k] * swell * Math.sin(2 * Math.PI * s.f * t * 0.42 + s.phase + c * 0.07);
      });
      pts.push([inset + (i / n) * (width - inset * 2), y0 + Math.max(-1.2, Math.min(1.2, v)) * gap * 0.4]);
    }
    lines.push(poly(pts));
  }
  return lines.join("");
}

function inputArt() {
  const out: string[] = [pad()];
  out.push(K.solidSvg(K.slabOf(FOOT, PAD_H, FOOT_TOP - PAD_H, P, 6, 0.8), { tone: "hi" }));
  out.push(K.lineSvg(K.planOutline(K.insetPlan(CARD, -1.4), FOOT_TOP, P), { tone: "mid" }));
  out.push(K.solidSvg(K.slabOf(CARD, FOOT_TOP, CARD_TOP - FOOT_TOP, P, 2), { tone: "mid", lit: true }));
  const w = CARD.w;
  const h = CARD_TOP - FOOT_TOP;
  const face = `<path class="mdraw-eeg" d="${eegLines(w, h, 4)}"/>`;
  out.push(onFace(CARD.x, CARD.y + CARD.d, CARD_TOP, face));
  return out.join("");
}

const FACE_W = BOX.w;
const FACE_H = BOX_TOP - PAD_H;
const IN = 12; // drawing margin inside the panel

/** Eight smooth rhythms, slow at the top to fast at the bottom. */
function rhythmsFace() {
  const rows = STAGES.rhythms.filters;
  const gap = (FACE_H - IN * 2) / rows;
  const lines: string[] = [];
  for (let r = 0; r < rows; r++) {
    const y0 = IN + gap * (r + 0.5);
    const cycles = 2 + r * 1.6;
    const pts: [number, number][] = [];
    for (let i = 0; i <= 120; i++) {
      const t = i / 120;
      const swell = 0.55 + 0.45 * Math.sin(Math.PI * (t * (1.1 + r * 0.17) + r * 0.6)) ** 2;
      pts.push([IN + t * (FACE_W - IN * 2), y0 + Math.sin(2 * Math.PI * cycles * t + r) * gap * 0.36 * swell]);
    }
    lines.push(poly(pts));
  }
  return `<path class="mdraw-ink" d="${lines.join("")}"/>`;
}

/** The 40 sensors seen from above, and the 16 weighted sums that leave this step. */
function sensorsFace() {
  const cx = IN + 21;
  const cy = FACE_H / 2;
  const r = 20;
  const head = [
    `<circle class="mdraw-head" cx="${cx}" cy="${cy}" r="${r}"/>`,
    `<path class="mdraw-head" d="M${f1(cx - 4)} ${f1(cy - r + 0.4)}L${cx} ${f1(cy - r - 4.5)}L${f1(cx + 4)} ${f1(cy - r + 0.4)}"/>`,
    `<path class="mdraw-head" d="M${f1(cx - r)} ${cy - 4}q-3 4 0 8M${f1(cx + r)} ${cy - 4}q3 4 0 8"/>`,
  ];
  const dots = data.electrodes
    .map((e) => `<circle cx="${f1(cx + e.x * r * 0.92)}" cy="${f1(cy - e.y * r * 0.92)}" r="1.25"/>`)
    .join("");
  const rows = STAGES.sensors.outputs;
  const x0 = cx + r + 12;
  const x1 = FACE_W - IN;
  const gap = (FACE_H - IN * 2) / rows;
  const rand = seeded(16);
  const lines: string[] = [];
  for (let k = 0; k < rows; k++) {
    const y0 = IN + gap * (k + 0.5);
    const a = rand() * Math.PI * 2;
    const f = 1.5 + rand() * 2.5;
    const pts: [number, number][] = [];
    for (let i = 0; i <= 40; i++) {
      const t = i / 40;
      pts.push([x0 + t * (x1 - x0), y0 + Math.sin(2 * Math.PI * f * t + a) * gap * 0.24]);
    }
    lines.push(poly(pts));
  }
  const toLines = `M${f1(cx + r + 3)} ${cy}H${f1(x0 - 3)}M${f1(x0 - 6)} ${cy - 2.5}L${f1(x0 - 3)} ${cy}L${f1(x0 - 6)} ${cy + 2.5}`;
  return `${head.join("")}<g class="mdraw-sensors">${dots}</g><path class="mdraw-to" d="${toLines}"/><path class="mdraw-ink" d="${lines.join("")}"/>`;
}

/** 16 coarse summaries, one value for every eighth of a second. */
function combineFace() {
  const rows = STAGES.combine.outputs;
  const steps = STAGES.combine.steps;
  const gap = (FACE_H - IN * 2) / rows;
  const step = (FACE_W - IN * 2) / steps;
  const rand = seeded(31);
  const lines: string[] = [];
  for (let k = 0; k < rows; k++) {
    const y0 = IN + gap * (k + 0.5);
    let v = 0;
    const pts: [number, number][] = [];
    for (let s = 0; s < steps; s++) {
      v = Math.max(-1, Math.min(1, v * 0.6 + (rand() - 0.5) * 1.3));
      const y = y0 - v * gap * 0.24;
      pts.push([IN + s * step, y], [IN + (s + 1) * step, y]);
    }
    lines.push(poly(pts));
  }
  return `<path class="mdraw-ink" d="${lines.join("")}"/>`;
}

export const LAMPS = [
  { name: "rest", label: "Rest" },
  { name: "affected_hand", label: "Hand" },
  { name: "sixth_finger", label: "Sixth finger" },
] as const;

/** The three lamps, one per choice; the page lights the likeliest. */
function decideFace() {
  const cy = FACE_H / 2;
  const span = FACE_W - IN * 2;
  return LAMPS.map((l, i) => {
    const cx = IN + span * ((i + 0.5) / LAMPS.length);
    return `<circle class="mdraw-bezel" cx="${f1(cx)}" cy="${cy}" r="13"/><circle class="lamp" data-class="${l.name}" cx="${f1(cx)}" cy="${cy}" r="9.5"/>`;
  }).join("");
}

export interface ModelArt {
  input: string;
  steps: [string, string, string, string];
}

export function buildModel(): ModelArt {
  return {
    input: inputArt(),
    steps: [instrument(rhythmsFace()), instrument(sensorsFace()), instrument(combineFace()), instrument(decideFace())],
  };
}
