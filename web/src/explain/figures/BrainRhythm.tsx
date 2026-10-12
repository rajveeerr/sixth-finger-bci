import { useMemo } from "react";
import { Plate } from "../../components/Plate";
import { data } from "../data";
import * as K from "../iso/kit";

// A sheet of chart paper on a bench with one rhythm drawn across it: steady while the
// patient rests, smaller once they imagine the movement, by the average fall measured
// in the 22 patients. The wave is a drawing of the effect; its size change is real.

const W = 900;
const H = 260;
const TOP = 8;
const BENCH: K.Plan = { x: 0, y: 0, w: 620, d: 150, r: 8 };
const PAPER: K.Plan = { x: 30, y: 24, w: 560, d: 96, r: 2 };
const Z = TOP + 0.8;
const CUE = PAPER.x + PAPER.w * 0.5;

const P = K.fitProjection([...K.boxCorners(BENCH, -6, TOP), [BENCH.w, 0, TOP + 20]], W, H, { pad: 10, azimuth: 70 });
const at = (p: K.Point3) => K.iso(p, P);

function wave(fall: number) {
  const pts: K.Point3[] = [];
  const yc = PAPER.y + PAPER.d / 2;
  const amp = 30;
  for (let x = PAPER.x + 14; x <= PAPER.x + PAPER.w - 14; x += 0.6) {
    const after = 1 / (1 + Math.exp(-(x - CUE) / 6)); // a smooth change at the cue
    const a = amp * (1 - fall * after) * (0.82 + 0.18 * Math.sin(x / 23));
    pts.push([x, yc + a * Math.sin(x / 3.1) + 3 * Math.sin(x / 1.3), Z]);
  }
  return K.pathOf(pts.map(at));
}

/** How the brain signal changes when the patient imagines moving. */
export function BrainRhythm() {
  const fall = -data.erd.sixth_finger.mean / 100;
  const svg = useMemo(() => {
    const out: string[] = [];
    out.push(K.solidSvg(K.slabOf(BENCH, 0, TOP, P, 8, 1), { tone: "mid", halo: true }));
    out.push(K.solidSvg(K.slabOf(PAPER, TOP, 0.8, P), { tone: "lo", flat: true, lit: true }));
    out.push(K.lineSvg(K.planOutline(PAPER, Z, P), { tone: "mid" }));
    // faint chart grid on the paper
    const grid: string[] = [];
    for (let x = PAPER.x + 20; x < PAPER.x + PAPER.w; x += 20) grid.push(K.lineOnTop([x, PAPER.y], [x, PAPER.y + PAPER.d], Z, P));
    for (let y = PAPER.y + 16; y < PAPER.y + PAPER.d; y += 16) grid.push(K.lineOnTop([PAPER.x, y], [PAPER.x + PAPER.w, y], Z, P));
    out.push(K.lineSvg(grid.join(""), { tone: "faint" }));
    out.push(`<path class="cue-line" d="${K.lineOnTop([CUE, PAPER.y - 6], [CUE, PAPER.y + PAPER.d + 6], Z, P)}"/>`);
    out.push(`<path class="rhythm" d="${wave(fall)}"/>`);
    // corner clips that hold the paper
    for (const [x, y] of K.corners(PAPER, 0)) out.push(K.solidSvg(K.cylinder(x, y, 4, TOP, 3, P, 16), { tone: "hi" }));
    return out.join("");
  }, [fall]);
  return (
    <Plate
      fig={6}
      title="What changes in the brain"
      hint="A drawing of the effect; the size of the change is measured"
      readout={`22 of 22 patients, ${Math.round(-data.erd.sixth_finger.mean)}% smaller on average`}
      caption={
        <>
          Over the part of the brain that moves the hand, the EEG has a steady rhythm (8 to 13 waves a second). When
          the patient imagines moving, it gets <strong>about a third smaller</strong>. That drop is what the model
          learns to spot.
        </>
      }
    >
      <svg className="iso-svg rhythm-svg dotted" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="A brain rhythm that gets smaller after the cue">
        <g dangerouslySetInnerHTML={{ __html: svg }} />
      </svg>
      <div className="rhythm-labels">
        <span>Resting</span>
        <span>Imagining the movement</span>
      </div>
    </Plate>
  );
}
