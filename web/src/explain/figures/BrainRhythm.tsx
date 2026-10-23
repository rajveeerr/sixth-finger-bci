import { useEffect, useMemo, useRef, useState } from "react";
import { Plate } from "../../components/Plate";
import { DotStrip } from "../charts";
import { data } from "../data";
import * as K from "../iso/kit";

// A sheet of chart paper on a bench with one rhythm drawn across it. The reader switches
// between resting and imagining, and the rhythm shrinks by the average fall measured in
// the 22 patients. The wave is a drawing of the effect; its size change is real.

const W = 900;
const H = 260;
const TOP = 8;
const BENCH: K.Plan = { x: 0, y: 0, w: 620, d: 150, r: 8 };
const PAPER: K.Plan = { x: 30, y: 24, w: 560, d: 96, r: 2 };
const Z = TOP + 0.8;

const P = K.fitProjection([...K.boxCorners(BENCH, -6, TOP), [BENCH.w, 0, TOP + 20]], W, H, { pad: 10, azimuth: 70 });
const at = (p: K.Point3) => K.iso(p, P);

function wave(scale: number) {
  const pts: K.Point3[] = [];
  const yc = PAPER.y + PAPER.d / 2;
  const amp = 30 * scale;
  for (let x = PAPER.x + 14; x <= PAPER.x + PAPER.w - 14; x += 0.6) {
    const a = amp * (0.82 + 0.18 * Math.sin(x / 23));
    pts.push([x, yc + a * Math.sin(x / 3.1) + 3 * scale * Math.sin(x / 1.3), Z]);
  }
  return K.pathOf(pts.map(at));
}

/** How the brain signal changes when the patient imagines moving. */
export function BrainRhythm() {
  // The measured fall is in power; a wave's height goes with the square root of its power.
  const fall = -data.erd.sixth_finger.mean / 100;
  const sf = data.erd.sixth_finger.values;
  const svg = useMemo(() => {
    const out: string[] = [];
    out.push(K.solidSvg(K.slabOf(BENCH, 0, TOP, P, 8, 1), { tone: "mid", halo: true }));
    out.push(K.solidSvg(K.slabOf(PAPER, TOP, 0.8, P), { tone: "lo", flat: true, lit: true }));
    out.push(K.lineSvg(K.planOutline(PAPER, Z, P), { tone: "mid" }));
    // faint chart grid on the paper
    const grid: string[] = [];
    for (let x = PAPER.x + 20; x < PAPER.x + PAPER.w; x += 20)
      grid.push(K.lineOnTop([x, PAPER.y], [x, PAPER.y + PAPER.d], Z, P));
    for (let y = PAPER.y + 16; y < PAPER.y + PAPER.d; y += 16)
      grid.push(K.lineOnTop([PAPER.x, y], [PAPER.x + PAPER.w, y], Z, P));
    out.push(K.lineSvg(grid.join(""), { tone: "faint" }));
    // corner clips that hold the paper
    for (const [x, y] of K.corners(PAPER, 0)) out.push(K.solidSvg(K.cylinder(x, y, 4, TOP, 3, P, 16), { tone: "hi" }));
    return out.join("");
  }, []);
  const [imagining, setImagining] = useState(false);
  const [scale, setScale] = useState(1);
  const scaleNow = useRef(1);
  const raf = useRef(0);
  useEffect(() => () => cancelAnimationFrame(raf.current), []);
  // The wave eases to its new size in a third of a second, only when the reader switches.
  const show = (on: boolean) => {
    setImagining(on);
    cancelAnimationFrame(raf.current);
    const to = on ? Math.sqrt(1 - fall) : 1;
    const from = scaleNow.current;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      scaleNow.current = to;
      setScale(to);
      return;
    }
    let start = -1;
    const step = (now: number) => {
      if (start < 0) start = now;
      const k = Math.min(1, (now - start) / 320);
      const v = from + (to - from) * (1 - (1 - k) ** 3);
      scaleNow.current = v;
      setScale(v);
      if (k < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
  };
  return (
    <Plate
      title="The rhythm over the hand area"
      hint="A drawing of the effect, 8 to 13 waves a second. Switch between resting and imagining."
      readout={
        imagining
          ? `Imagining: the rhythm's power falls by ${Math.round(fall * 100)}% on average over ${sf.length} patients (grey: its size at rest). This drop is what the model learns to spot.`
          : "Resting: the rhythm at its usual size."
      }
    >
      <div className="toggle rhythm-toggle" role="radiogroup" aria-label="What the patient is doing">
        {[false, true].map((on) => (
          <button key={String(on)} type="button" role="radio" aria-checked={imagining === on} onClick={() => show(on)}>
            {on ? "Imagining the movement" : "Resting"}
          </button>
        ))}
      </div>
      <svg
        className="iso-svg rhythm-svg dotted"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={imagining ? "The rhythm, smaller while imagining" : "The rhythm while resting"}
      >
        <g dangerouslySetInnerHTML={{ __html: svg }} />
        {scale < 0.999 && <path className="rhythm-ghost" d={wave(1)} />}
        <path className="rhythm" d={wave(scale)} />
      </svg>
    </Plate>
  );
}

/** The fall in that rhythm, measured in every patient, for the hand and the sixth finger. */
export function RhythmMeasured() {
  const sf = data.erd.sixth_finger.values;
  const fmt = (v: number) => `${v < 0 ? "−" : v > 0 ? "+" : ""}${Math.abs(Math.round(v * 100))}%`;
  return (
    <Plate
      title="Measured in every patient"
      hint="Each dot is one patient: how much the rhythm's power fell while imagining, compared with the one second just before the instruction. Left of the dashed line means it fell."
      readout={`It fell in ${sf.filter((v) => v < 0).length} of ${sf.length} patients for the sixth finger, by ${Math.round(-data.erd.sixth_finger.mean)}% on average, and by about as much for the hand, which is why the two are hard to tell apart.`}
    >
      <DotStrip
        rows={[
          {
            label: "Imagining the hand",
            values: data.erd.affected_hand.values.map((v) => v / 100),
            mean: data.erd.affected_hand.mean / 100,
            colour: "var(--hand)",
          },
          {
            label: "Imagining the sixth finger",
            values: data.erd.sixth_finger.values.map((v) => v / 100),
            mean: data.erd.sixth_finger.mean / 100,
            colour: "var(--sixth)",
          },
        ]}
        domain={[-0.8, 0.2]}
        ticks={[-0.8, -0.6, -0.4, -0.2, 0, 0.2]}
        format={fmt}
        marker={{ at: 0, text: "no change" }}
        label="How much the rhythm's power fell in each patient while imagining the hand and the sixth finger"
      />
    </Plate>
  );
}
