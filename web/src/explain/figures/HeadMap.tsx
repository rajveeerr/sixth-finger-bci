import { useMemo } from "react";
import { Plate } from "../../components/Plate";
import { data } from "../data";
import { HEAD_BOUNDS, headSvg, placeHead, type HeadPose } from "../iso/head";
import * as K from "../iso/kit";

// A real head (MNE's template) in an EEG cap on a turned stand, three-quarter view from
// the front left, with the 40 electrodes where the cap puts them; the seven drawn in the
// demo are white.

const W = 560;
const H = 480;
const AZ = 40;
const PLINTH = 70;
const a = (AZ * Math.PI) / 180;
// Mostly to the screen's left and a little toward the viewer: the face, an ear and the top.
const POSE: HeadPose = {
  origin: [0, 10, 150],
  scale: 1,
  nose: [Math.cos(a) * 0.3 - Math.sin(a) * 0.95, Math.sin(a) * 0.3 + Math.cos(a) * 0.95],
  cutMm: -95,
};
const place = placeHead(POSE);
const P = K.fitProjection(
  [...K.boxCorners({ x: -PLINTH, y: -PLINTH, w: 2 * PLINTH, d: 2 * PLINTH, r: 0 }, 0, 14), ...HEAD_BOUNDS.map(place.world)],
  W,
  H,
  { pad: 8, azimuth: AZ },
);

function art() {
  const out: string[] = [];
  out.push(K.solidSvg(K.cylinder(0, 0, PLINTH, 0, 12, P, 72, 1), { tone: "mid", halo: true }));
  const ticks = K.radialTicks(0, 0, PLINTH - 4, 72, 6, 12, [3, 7], P);
  out.push(K.lineSvg(ticks.minor, { tone: "lo" }), K.lineSvg(ticks.major, { tone: "mid" }));
  const head = headSvg(P, POSE);
  const { c, r } = head.neck;
  out.push(K.solidSvg(K.cylinder(c[0], c[1], r * 0.62, 12, c[2] - 12 + 4, P, 40, 0.6), { tone: "hi" }));
  out.push(head.svg);
  return out.join("");
}

/** Where on the head the brain signal is read. */
export function HeadMap() {
  const svg = useMemo(() => art(), []);
  const shown = data.electrodes.filter((e) => e.shown).map((e) => e.name);
  return (
    <Plate
      title="The 40 sensors we use"
      hint={`The cap records more; the study's analysis and ours use these 40. Each picks up the voltage under it. The seven white ones (${shown.join(", ")}) sit over the strip of brain that moves the body; the demo shows three of them. In the names, F is toward the front, C the centre, P toward the back; odd numbers are on the left, even on the right, z on the middle line.`}
      readout="The left side of the brain moves the right hand, and the right side the left."
    >
      <svg className="iso-svg head-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="A head wearing an EEG cap with 40 sensors">
        <g dangerouslySetInnerHTML={{ __html: svg }} />
      </svg>
    </Plate>
  );
}
