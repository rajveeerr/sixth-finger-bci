import { useMemo, useState } from "react";
import { IsoHand } from "../../hands/IsoHand";
import { headSvg, HEAD_BOUNDS, placeHead, type HeadPose } from "../iso/head";
import * as K from "../iso/kit";

// A brain-computer interface as a loop of three things a reader recognises: a head in an
// EEG cap, a computer running the model, and the hand with its robotic finger; arrows say
// what passes between them, and the way back is the wearer seeing the finger move. A switch
// turns every caption between this demo and a real system, so the two are compared in place.
// Keep this in step with the report section on moving from the demo to a real limb.

const HEAD_W = 300;
const HEAD_H = 300;
const AZ = 40;
const a = (AZ * Math.PI) / 180;
const POSE: HeadPose = {
  origin: [0, 0, 120],
  scale: 1,
  nose: [Math.cos(a) * 0.3 - Math.sin(a) * 0.95, Math.sin(a) * 0.3 + Math.cos(a) * 0.95],
  cutMm: -95,
};
const HEAD_P = K.fitProjection(
  [...K.boxCorners({ x: -55, y: -55, w: 110, d: 110, r: 0 }, 0, 10), ...HEAD_BOUNDS.map(placeHead(POSE).world)],
  HEAD_W,
  HEAD_H,
  { pad: 6, azimuth: AZ },
);

function headArt() {
  const out: string[] = [];
  out.push(K.solidSvg(K.cylinder(0, 0, 55, 0, 10, HEAD_P, 64, 0.8), { tone: "mid", halo: true }));
  const head = headSvg(HEAD_P, POSE);
  const { c, r } = head.neck;
  out.push(K.solidSvg(K.cylinder(c[0], c[1], r * 0.62, 10, c[2] - 6, HEAD_P, 40, 0.6), { tone: "hi" }));
  out.push(head.svg);
  return out.join("");
}

const PC_W = 300;
const PC_H = 260;
const PC_P = K.fitProjection(
  [...K.boxCorners({ x: 0, y: 0, w: 160, d: 110, r: 0 }, 0, 8), [0, 40, 120], [160, 40, 120]],
  PC_W,
  PC_H,
  { pad: 8, azimuth: 62 },
);

function computerArt() {
  const out: string[] = [];
  const pad: K.Plan = { x: 0, y: 0, w: 160, d: 110, r: 10 };
  out.push(K.solidSvg(K.slabOf(pad, 0, 6, PC_P, 8, 0.8), { tone: "mid", halo: true }));
  // the laptop's base, keyboard rows and the screen standing behind it
  const base: K.Plan = { x: 12, y: 40, w: 136, d: 62, r: 5 };
  out.push(K.solidSvg(K.slabOf(base, 6, 5, PC_P, 6, 0.6), { tone: "hi" }));
  for (let row = 0; row < 4; row++) {
    const y = base.y + 10 + row * 9;
    out.push(K.lineSvg(K.lineOnTop([base.x + 14, y], [base.x + base.w - 14, y], 11, PC_P), { tone: "faint" }));
  }
  out.push(K.solidSvg(K.slabOf({ x: 12, y: 32, w: 136, d: 8, r: 3 }, 6, 100, PC_P, 6, 0.6), { tone: "hi" }));
  const fy = 40.05;
  const face = (pts: K.Point3[]) =>
    K.pathOf(
      pts.map((p) => K.iso(p, PC_P)),
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
  // the model's three lamps on the screen, the sixth finger's lit
  [
    { x: 50, cls: "pc-lamp" },
    { x: 80, cls: "pc-lamp" },
    { x: 110, cls: "pc-lamp pc-lamp-on" },
  ].forEach((l) => {
    const ring = Array.from({ length: 24 }, (_, i) => {
      const t = (i / 24) * Math.PI * 2;
      return [l.x + Math.cos(t) * 9, fy, 56 + Math.sin(t) * 9] as K.Point3;
    });
    out.push(`<path class="${l.cls}" d="${face(ring)}"/>`);
  });
  return out.join("");
}

function Arrow({ label, back = false }: { label: string; back?: boolean }) {
  return (
    <div className={back ? "loop-arrow loop-arrow-back" : "loop-arrow"} aria-hidden="true">
      <span>{label}</span>
      <svg viewBox="0 0 100 12" preserveAspectRatio="none">
        <path d={back ? "M100 6H4M10 1L3 6l7 5" : "M0 6h96M90 1l7 5-7 5"} />
      </svg>
    </div>
  );
}

type Side = "demo" | "real";

const STEPS: { name: string; demo: string; real: string; drawn?: boolean }[] = [
  {
    name: "Read",
    demo: "Recorded EEG of a stroke patient, played at real speed.",
    real: "An EEG cap and amplifier on the wearer, live.",
  },
  {
    name: "Decide",
    demo: "The trained model, running in this browser, turns each 4 s of signal into a command.",
    real: "The same model, set up for each wearer with a short practice.",
  },
  {
    name: "Act",
    demo: "The drawn finger bends. Drawn, not built.",
    real: "A motor bends the robotic finger, with limits and an emergency stop.",
    drawn: true,
  },
  {
    name: "See",
    demo: "You watch the finger move.",
    real: "The wearer sees and feels the finger move, and learns to control it better.",
  },
];

function Step({ i, side }: { i: number; side: Side }) {
  const s = STEPS[i];
  return (
    <p className="loop-say" data-drawn={side === "demo" && s.drawn ? "" : undefined}>
      <b>
        {i + 1}. {s.name}
      </b>{" "}
      {s[side]}
    </p>
  );
}

/** The loop of a BCI, from the wearer's brain to the finger and back through their eyes. */
export function BciLoop() {
  const head = useMemo(() => headArt(), []);
  const pc = useMemo(() => computerArt(), []);
  const [side, setSide] = useState<Side>("real");
  return (
    <figure
      className="loop bleed"
      aria-label="A brain-computer interface: brain signal, model, robotic finger, and back"
    >
      <div className="toggle loop-toggle" role="radiogroup" aria-label="Show the loop">
        {(["real", "demo"] as Side[]).map((v) => (
          <button key={v} type="button" role="radio" aria-checked={side === v} onClick={() => setSide(v)}>
            {v === "real" ? "In a real system" : "In this demo"}
          </button>
        ))}
      </div>
      <div className="loop-row">
        <div className="loop-station">
          <svg className="iso-svg" viewBox={`0 0 ${HEAD_W} ${HEAD_H}`} role="img" aria-label="A head in an EEG cap">
            <g dangerouslySetInnerHTML={{ __html: head }} />
          </svg>
          <Step i={0} side={side} />
        </div>
        <Arrow label="brain signal" />
        <div className="loop-station">
          <svg className="iso-svg" viewBox={`0 0 ${PC_W} ${PC_H}`} role="img" aria-label="A computer running the model">
            <g dangerouslySetInnerHTML={{ __html: pc }} />
          </svg>
          <Step i={1} side={side} />
        </div>
        <Arrow label="command" />
        <div className="loop-station">
          <div className="loop-hand">
            <IsoHand command="SIXTH_FINGER_FLEX" />
          </div>
          <Step i={2} side={side} />
        </div>
      </div>
      <div className="loop-back">
        <Arrow label="" back />
        <Step i={3} side={side} />
      </div>
      <p className="loop-note">
        {side === "real" ? (
          <>
            Steps 1 and 3 are what this project did not build. A real system would also need safety checks against false
            starts and a short setup for each wearer (<a href="#answer-2">question 2</a>).
          </>
        ) : (
          <>Steps 1 and 2 are real here: real recordings and the real model. Step 3 is drawn.</>
        )}
      </p>
    </figure>
  );
}
