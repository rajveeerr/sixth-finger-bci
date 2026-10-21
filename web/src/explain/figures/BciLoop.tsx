import { useMemo, useState } from "react";
import { IsoHand } from "../../hands/IsoHand";
import { headSvg, HEAD_BOUNDS, placeHead, type HeadPose } from "../iso/head";
import * as K from "../iso/kit";
import { LAPTOP_BOUNDS, laptopSvg } from "../iso/pipeline";
import { RealPipeline } from "./RealPipeline";

// A brain-computer interface as a loop of three things a reader recognises: a head in an
// EEG cap, a computer running the model, and the hand with its robotic finger; arrows say
// what passes between them, and the way back is the wearer seeing the finger move. A switch
// turns the figure to a real system's parts (RealPipeline), so the two are compared in place.
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
const PC_P = K.fitProjection(LAPTOP_BOUNDS, PC_W, PC_H, { pad: 8, azimuth: 62 });

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

const STEPS: { name: string; text: string; drawn?: boolean }[] = [
  { name: "Read", text: "Recorded EEG of a stroke patient, played at real speed." },
  {
    name: "Decide",
    text: "The trained model, on our server or in this browser, turns each 4 s of signal into a command.",
  },
  { name: "Act", text: "The drawn finger bends. Drawn, not built.", drawn: true },
  { name: "See", text: "You watch the finger move." },
];

function Step({ i }: { i: number }) {
  const s = STEPS[i];
  return (
    <p className="loop-say" data-drawn={s.drawn ? "" : undefined}>
      <b>
        {i + 1}. {s.name}
      </b>{" "}
      {s.text}
    </p>
  );
}

/** The loop of a BCI, from the wearer's brain to the finger and back through their eyes. */
export function BciLoop() {
  const head = useMemo(() => headArt(), []);
  const pc = useMemo(() => laptopSvg(PC_P), []);
  const [side, setSide] = useState<Side>("demo");
  return (
    <figure
      className="loop bleed"
      aria-label={
        side === "real"
          ? "A real brain-computer interface, part by part: EEG cap and amplifier, laptop, server, finger board and motor"
          : "A brain-computer interface: brain signal, model, robotic finger, and back"
      }
    >
      <div className="toggle loop-toggle" role="radiogroup" aria-label="Show the loop">
        {(["demo", "real"] as Side[]).map((v) => (
          <button key={v} type="button" role="radio" aria-checked={side === v} onClick={() => setSide(v)}>
            {v === "real" ? "In a real system" : "In this demo"}
          </button>
        ))}
      </div>
      {side === "real" ? (
        <>
          <RealPipeline />
          <p className="loop-note">
            Hatched parts are not built yet. A real system would also need safety limits on the motor, an emergency
            stop, and a short setup for each wearer (<a href="#answer-2">question 2</a>).
          </p>
        </>
      ) : (
        <>
          <div className="loop-row">
            <div className="loop-station">
              <svg className="iso-svg" viewBox={`0 0 ${HEAD_W} ${HEAD_H}`} role="img" aria-label="A head in an EEG cap">
                <g dangerouslySetInnerHTML={{ __html: head }} />
              </svg>
              <Step i={0} />
            </div>
            <Arrow label="brain signal" />
            <div className="loop-station">
              <svg
                className="iso-svg"
                viewBox={`0 0 ${PC_W} ${PC_H}`}
                role="img"
                aria-label="A computer running the model"
              >
                <g dangerouslySetInnerHTML={{ __html: pc }} />
              </svg>
              <Step i={1} />
            </div>
            <Arrow label="command" />
            <div className="loop-station">
              <div className="loop-hand">
                <IsoHand command="SIXTH_FINGER_FLEX" />
              </div>
              <Step i={2} />
            </div>
          </div>
          <div className="loop-back">
            <Arrow label="" back />
            <Step i={3} />
          </div>
          <p className="loop-note">Steps 1 and 2 are real here: real recordings and the real model. Step 3 is drawn.</p>
        </>
      )}
    </figure>
  );
}
