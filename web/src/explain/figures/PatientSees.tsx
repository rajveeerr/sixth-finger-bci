import { useMemo } from "react";
import { Plate } from "../../components/Plate";
import * as K from "../iso/kit";

// One trial as three monitors on a bench, in the order the patient sees them: a cross
// (rest, 7 s), a grey circle (get ready, 1 s), then the cue to imagine (6 s). The strip
// along the front is the trial to scale, with the two 4 s pieces the model reads.

const W = 900;
const H = 300;
const TOP = 10;
const UNIT = 40; // bench units per second
const X0 = 30; // where the trial starts on the bench
const BENCH: K.Plan = { x: 0, y: 0, w: 14 * UNIT + 2 * X0, d: 120, r: 8 };
const SCREEN = { w: 104, h: 70, d: 9, y: 26, lift: 30 };
const SEGMENTS = [
  { key: "rest", from: 0, to: 7 },
  { key: "ready", from: 7, to: 8 },
  { key: "cue", from: 8, to: 14 },
] as const;
const STRIP_Y = BENCH.d - 30; // the time strip along the front of the bench

const P = K.fitProjection(
  [...K.boxCorners(BENCH, -6, TOP), [BENCH.w, SCREEN.y, TOP + SCREEN.lift + SCREEN.h + 4], [0, SCREEN.y, TOP + SCREEN.lift + SCREEN.h + 4]],
  W,
  H,
  { pad: 12, azimuth: 70 },
);
const at = (p: K.Point3) => K.iso(p, P);
const face = (pts: K.Point3[], closed = true) => K.pathOf(pts.map(at), closed);
const tx = (seconds: number) => X0 + seconds * UNIT;

function art() {
  const out: string[] = [];
  out.push(K.solidSvg(K.slabOf(BENCH, 0, TOP, P, 8, 1), { tone: "mid", halo: true }));
  out.push(K.lineSvg(K.planOutline(K.insetPlan(BENCH, 6), TOP, P), { tone: "faint" }));
  // The trial as a painted strip, one band per screen, with a tick every second.
  for (const s of SEGMENTS) {
    const band: K.Plane[] = [[tx(s.from), STRIP_Y], [tx(s.to), STRIP_Y], [tx(s.to), STRIP_Y + 12], [tx(s.from), STRIP_Y + 12]];
    out.push(`<path class="band band-${s.key}" d="${K.onTop(band, TOP + 0.05, P, true)}"/>`);
  }
  const ticks = K.topTicks(tx(0), tx(14), UNIT, 7, STRIP_Y + 12, TOP, [4, 8], P);
  out.push(K.lineSvg(ticks.minor, { tone: "mid" }), K.lineSvg(ticks.major, { tone: "hi" }));
  // The two 4 s pieces the model reads, as brackets behind the strip.
  const bracket = (from: number, to: number) => {
    const y = STRIP_Y - 6;
    return K.lineSvg(K.onTop([[tx(from), y + 4], [tx(from), y], [tx(to), y], [tx(to), y + 4]], TOP, P), { tone: "hi" });
  };
  out.push(bracket(1, 5), bracket(9, 13));
  // One monitor over the middle of each stretch.
  for (const s of SEGMENTS) {
    const cx = tx((s.from + s.to) / 2);
    const left = cx - SCREEN.w / 2;
    out.push(K.solidSvg(K.slabOf({ x: cx - 24, y: SCREEN.y - 8, w: 48, d: 30, r: 4 }, TOP, 3, P, 6, 0.4), { tone: "hi" }));
    out.push(K.solidSvg(K.slabOf({ x: cx - 6, y: SCREEN.y - 2, w: 12, d: 8, r: 2 }, TOP + 3, SCREEN.lift - 3, P), { tone: "hi" }));
    const zb = TOP + SCREEN.lift;
    const zt = zb + SCREEN.h;
    out.push(K.solidSvg(K.slabOf({ x: left, y: SCREEN.y - SCREEN.d, w: SCREEN.w, d: SCREEN.d, r: 2 }, zb, SCREEN.h, P, 6, 0.6), { tone: "hi" }));
    const fy = SCREEN.y + 0.05;
    const sx0 = left + 6;
    const sx1 = left + SCREEN.w - 6;
    const sz0 = zb + 6;
    const sz1 = zt - 6;
    out.push(`<path class="screen-glass" d="${face([[sx0, fy, sz0], [sx1, fy, sz0], [sx1, fy, sz1], [sx0, fy, sz1]])}"/>`);
    const cz = (sz0 + sz1) / 2;
    const r = (sz1 - sz0) * 0.22;
    if (s.key === "rest") {
      out.push(`<path class="screen-mark" d="${face([[cx - r, fy, cz], [cx + r, fy, cz]], false)}${face([[cx, fy, cz - r], [cx, fy, cz + r]], false)}"/>`);
    } else if (s.key === "ready") {
      const ring = Array.from({ length: 28 }, (_, i) => {
        const t = (i / 28) * Math.PI * 2;
        return [cx + Math.cos(t) * r, fy, cz + Math.sin(t) * r] as K.Point3;
      });
      out.push(`<path class="screen-dot" d="${face(ring)}"/>`);
    } else {
      const bw = (sx1 - sx0) * 0.32;
      const bh = (sz1 - sz0) * 0.34;
      out.push(`<path class="screen-hand" d="${face([[cx - bw - 3, fy, cz - bh / 2], [cx - 3, fy, cz - bh / 2], [cx - 3, fy, cz + bh / 2], [cx - bw - 3, fy, cz + bh / 2]])}"/>`);
      out.push(`<path class="screen-sixth" d="${face([[cx + 3, fy, cz - bh / 2], [cx + bw + 3, fy, cz - bh / 2], [cx + bw + 3, fy, cz + bh / 2], [cx + 3, fy, cz + bh / 2]])}"/>`);
    }
  }
  return out.join("");
}

const LABELS = [
  { title: "Rest", text: "a cross, 7 s" },
  { title: "Get ready", text: "a grey circle, 1 s" },
  { title: "Imagine", text: "hand or sixth finger, 6 s" },
];

/** What the patient sees in one trial, and the two 4 s pieces the model reads. */
export function PatientSees() {
  const svg = useMemo(() => art(), []);
  return (
    <Plate
      title="One trial, as the patient sees it"
      hint="14 seconds, drawn to scale along the strip."
      caption={
        <>
          A cross means rest. A grey circle means get ready. Then the screen asks the patient to imagine moving the
          <strong> hand</strong> or the <strong>sixth finger</strong>. The model reads two 4 s pieces of each trial,
          the brackets on the strip: one while resting, one while imagining.
        </>
      }
    >
      <svg className="iso-svg sees dotted" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Three screens: a cross, a grey circle, then the cue">
        <g dangerouslySetInnerHTML={{ __html: svg }} />
      </svg>
      <ol className="sees-labels">
        {LABELS.map((l) => (
          <li key={l.title}>
            <b>{l.title}</b> {l.text}
          </li>
        ))}
      </ol>
    </Plate>
  );
}
