import { useMemo } from "react";
import * as K from "../explain/iso/kit";

// The patient's monitor, drawn like the bench, showing what is on it now: a cross while
// resting, a grey circle to get ready, then the cue (the hand, or the sixth finger).

const W = 320;
const H = 250;
const TOP = 6;
const SCREEN = { x: 20, w: 150, h: 98, d: 12, lift: 34 };
const FACE_Y = 52; // the screen's front face, in plan
const P = K.fitProjection(
  [
    ...K.boxCorners({ x: 0, y: 0, w: 190, d: 110, r: 0 }, 0, TOP),
    [SCREEN.x, FACE_Y, TOP + SCREEN.lift + SCREEN.h],
    [SCREEN.x + SCREEN.w, FACE_Y, TOP + SCREEN.lift + SCREEN.h],
  ],
  W,
  H,
  { pad: 8, azimuth: 62 },
);
const face = (pts: K.Point3[], closed = true) => K.pathOf(pts.map((p) => K.iso(p, P)), closed);

const S = { x0: SCREEN.x + 8, x1: SCREEN.x + SCREEN.w - 8, z0: TOP + SCREEN.lift + 8, z1: TOP + SCREEN.lift + SCREEN.h - 8 };
const CX = (S.x0 + S.x1) / 2;
const CZ = (S.z0 + S.z1) / 2;
const FY = FACE_Y + 0.05;

function staticArt() {
  const out: string[] = [];
  const pad: K.Plan = { x: 0, y: 0, w: 190, d: 110, r: 10 };
  out.push(K.solidSvg(K.slabOf(pad, 0, TOP, P, 8, 0.8), { tone: "mid", halo: true }));
  out.push(K.dotsSvg(K.corners(pad, 9).map(([x, y]) => K.iso([x, y, TOP], P)), { size: 1.2, tone: "mid" }));
  const mid = SCREEN.x + SCREEN.w / 2;
  out.push(K.solidSvg(K.slabOf({ x: mid - 34, y: FACE_Y - 30, w: 68, d: 40, r: 6 }, TOP, 4, P, 8, 0.5), { tone: "hi" }));
  out.push(K.solidSvg(K.slabOf({ x: mid - 8, y: FACE_Y - 22, w: 16, d: 10, r: 3 }, TOP + 4, SCREEN.lift - 4, P), { tone: "hi" }));
  out.push(K.solidSvg(K.slabOf({ x: SCREEN.x, y: FACE_Y - SCREEN.d, w: SCREEN.w, d: SCREEN.d, r: 3 }, TOP + SCREEN.lift, SCREEN.h, P, 6, 0.8), { tone: "hi" }));
  out.push(`<path class="screen-glass" d="${face([[S.x0, FY, S.z0], [S.x1, FY, S.z0], [S.x1, FY, S.z1], [S.x0, FY, S.z1]])}"/>`);
  return out.join("");
}

function glyph(kind: string) {
  const r = (S.z1 - S.z0) * 0.24;
  if (kind === "rest") {
    return `<path class="screen-mark" d="${face([[CX - r, FY, CZ], [CX + r, FY, CZ]], false)}${face([[CX, FY, CZ - r], [CX, FY, CZ + r]], false)}"/>`;
  }
  if (kind === "prepare") {
    const ring = Array.from({ length: 32 }, (_, i) => {
      const t = (i / 32) * Math.PI * 2;
      return [CX + Math.cos(t) * r, FY, CZ + Math.sin(t) * r] as K.Point3;
    });
    return `<path class="screen-dot" d="${face(ring)}"/>`;
  }
  if (kind === "affected_hand" || kind === "sixth_finger") {
    const bw = (S.x1 - S.x0) * 0.34;
    const bh = (S.z1 - S.z0) * 0.4;
    const cls = kind === "sixth_finger" ? "screen-sixth" : "screen-hand";
    return `<path class="${cls}" d="${face([[CX - bw / 2, FY, CZ - bh / 2], [CX + bw / 2, FY, CZ - bh / 2], [CX + bw / 2, FY, CZ + bh / 2], [CX - bw / 2, FY, CZ + bh / 2]])}"/>`;
  }
  return "";
}

/** What the patient's screen shows: "rest", "prepare", or the cue's class name. */
export function PatientScreen({ kind }: { kind: string }) {
  const art = useMemo(() => staticArt(), []);
  const mark = useMemo(() => glyph(kind), [kind]);
  return (
    <svg className="iso-svg patient-screen" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="The patient's screen">
      <g dangerouslySetInnerHTML={{ __html: art }} />
      <g dangerouslySetInnerHTML={{ __html: mark }} />
    </svg>
  );
}
