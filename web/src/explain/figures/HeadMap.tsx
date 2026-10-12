import { useMemo } from "react";
import { Plate } from "../../components/Plate";
import { data } from "../data";
import * as K from "../iso/kit";

// The 40 sensors on a stepped contour model of the head, nose toward the back left. The
// seven drawn in step 1 are dark pins, and the ones over the motor cortex a shade darker.

const W = 700;
const H = 320;
const C = { x: 80, y: 80 };
const CONTOURS = [64, 60, 54, 46, 35, 21];
const STEP = 7;
const BASE = 10;
const R = CONTOURS[0] - 3;

const P = K.fitProjection(
  [...K.boxCorners({ x: 0, y: 0, w: 160, d: 160, r: 0 }, 0, BASE), [C.x, C.y, BASE + STEP * CONTOURS.length + 10]],
  W,
  H,
  { pad: 10, azimuth: 52 },
);
const at = (p: K.Point3) => K.iso(p, P);

function heightAt(rho: number) {
  let level = 0;
  CONTOURS.forEach((r, i) => {
    if (r > rho + 3) level = i + 1;
  });
  return BASE + level * STEP;
}

function art() {
  const out: string[] = [];
  const base: K.Plan = { x: 0, y: 0, w: 160, d: 160, r: 14 };
  out.push(K.solidSvg(K.slabOf(base, 0, BASE - 2, P, 10, 1), { tone: "mid", halo: true }));
  out.push(K.dotsSvg(K.corners(base, 12).map(([x, y]) => at([x, y, BASE - 2])), { size: 1.4, tone: "mid" }));
  out.push(K.solidSvg(K.cylinder(C.x, C.y, R + 9, BASE - 2, 2, P, 64, 0.5), { tone: "mid" }));
  // nose and ears
  out.push(K.solidSvg(K.slabOf({ x: C.x - R - 16, y: C.y - 7, w: 16, d: 14, r: 4 }, BASE, 4, P), { tone: "hi" }));
  for (const side of [-1, 1]) out.push(K.solidSvg(K.slabOf({ x: C.x - 9, y: C.y + side * (R + 8) - 4, w: 18, d: 8, r: 4 }, BASE, 6, P), { tone: "hi" }));
  CONTOURS.forEach((r, i) => out.push(K.solidSvg(K.cylinder(C.x, C.y, r, BASE + i * STEP, STEP, P, 72), { tone: "hi" })));
  const pins = data.electrodes
    .map((e) => {
      const px = C.x - e.y * R;
      const py = C.y + e.x * R;
      return { ...e, p: [px, py, heightAt(Math.hypot(e.x, e.y) * R)] as K.Point3 };
    })
    .sort((a, b) => K.depthOf(a.p, P) - K.depthOf(b.p, P));
  for (const e of pins) {
    const tall = e.shown ? 4.5 : 1.8;
    const r = e.shown ? 2.9 : 2.1;
    out.push(K.solidSvg(K.cylinder(e.p[0], e.p[1], r, e.p[2], tall, P, 18), { tone: e.shown ? "hi" : "mid", className: e.shown ? "pin-shown" : e.motor ? "pin-motor" : "pin" }));
  }
  return out.join("");
}

/** Where on the head the brain signal is read. */
export function HeadMap() {
  const svg = useMemo(() => art(), []);
  const shown = data.electrodes.filter((e) => e.shown).map((e) => e.name);
  return (
    <Plate
      title="Where the signal is read"
      hint={`40 sensors in a cap, nose to the back left. The dark ones are the seven in step 1: ${shown.join(", ")}.`}
      readout="Each side of the head moves the opposite hand."
      caption={
        <>
          The sensors over the <strong>motor cortex</strong>, the strip across the top of the head that moves the body,
          matter most. The model reads all 40.
        </>
      }
    >
      <svg className="iso-svg head-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="A model of the head with 40 sensors">
        <g dangerouslySetInnerHTML={{ __html: svg }} />
      </svg>
    </Plate>
  );
}
