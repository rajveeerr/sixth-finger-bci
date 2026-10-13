import { useEffect, useMemo, useRef, useState } from "react";
import { Plate } from "../../components/Plate";
import { PaperRef } from "../refs";
import * as K from "../iso/kit";

// One trial as three monitors on a bench, in the order the patient sees them: a cross
// (rest, 7 s), a grey circle (get ready, 1 s), then the cue to imagine (6 s). The strip
// along the front is the trial to scale, with the two 4 s pieces the model reads. The
// reader can play the trial or drag through it; the screen of the moment stays lit.

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
  [
    ...K.boxCorners(BENCH, -6, TOP),
    [BENCH.w, SCREEN.y, TOP + SCREEN.lift + SCREEN.h + 4],
    [0, SCREEN.y, TOP + SCREEN.lift + SCREEN.h + 4],
  ],
  W,
  H,
  { pad: 12, azimuth: 70 },
);
const at = (p: K.Point3) => K.iso(p, P);
const face = (pts: K.Point3[], closed = true) => K.pathOf(pts.map(at), closed);
const tx = (seconds: number) => X0 + seconds * UNIT;

function art() {
  const out: string[] = [];
  const screens: string[] = [];
  out.push(K.solidSvg(K.slabOf(BENCH, 0, TOP, P, 8, 1), { tone: "mid", halo: true }));
  out.push(K.lineSvg(K.planOutline(K.insetPlan(BENCH, 6), TOP, P), { tone: "faint" }));
  // The trial as a painted strip, one band per screen, with a tick every second.
  for (const s of SEGMENTS) {
    const band: K.Plane[] = [
      [tx(s.from), STRIP_Y],
      [tx(s.to), STRIP_Y],
      [tx(s.to), STRIP_Y + 12],
      [tx(s.from), STRIP_Y + 12],
    ];
    out.push(`<path class="band band-${s.key}" d="${K.onTop(band, TOP + 0.05, P, true)}"/>`);
  }
  const ticks = K.topTicks(tx(0), tx(14), UNIT, 7, STRIP_Y + 12, TOP, [4, 8], P);
  out.push(K.lineSvg(ticks.minor, { tone: "mid" }), K.lineSvg(ticks.major, { tone: "hi" }));
  // The two 4 s pieces the model reads, as brackets behind the strip.
  const bracket = (from: number, to: number) => {
    const y = STRIP_Y - 6;
    return K.lineSvg(
      K.onTop(
        [
          [tx(from), y + 4],
          [tx(from), y],
          [tx(to), y],
          [tx(to), y + 4],
        ],
        TOP,
        P,
      ),
      { tone: "hi" },
    );
  };
  out.push(bracket(1, 5), bracket(9, 13));
  // One monitor over the middle of each stretch.
  for (const s of SEGMENTS) {
    const out: string[] = [];
    const cx = tx((s.from + s.to) / 2);
    const left = cx - SCREEN.w / 2;
    out.push(
      K.solidSvg(K.slabOf({ x: cx - 24, y: SCREEN.y - 8, w: 48, d: 30, r: 4 }, TOP, 3, P, 6, 0.4), { tone: "hi" }),
    );
    out.push(
      K.solidSvg(K.slabOf({ x: cx - 6, y: SCREEN.y - 2, w: 12, d: 8, r: 2 }, TOP + 3, SCREEN.lift - 3, P), {
        tone: "hi",
      }),
    );
    const zb = TOP + SCREEN.lift;
    const zt = zb + SCREEN.h;
    out.push(
      K.solidSvg(
        K.slabOf({ x: left, y: SCREEN.y - SCREEN.d, w: SCREEN.w, d: SCREEN.d, r: 2 }, zb, SCREEN.h, P, 6, 0.6),
        { tone: "hi" },
      ),
    );
    const fy = SCREEN.y + 0.05;
    const sx0 = left + 6;
    const sx1 = left + SCREEN.w - 6;
    const sz0 = zb + 6;
    const sz1 = zt - 6;
    out.push(
      `<path class="screen-glass" d="${face([
        [sx0, fy, sz0],
        [sx1, fy, sz0],
        [sx1, fy, sz1],
        [sx0, fy, sz1],
      ])}"/>`,
    );
    const cz = (sz0 + sz1) / 2;
    const r = (sz1 - sz0) * 0.22;
    if (s.key === "rest") {
      out.push(
        `<path class="screen-mark" d="${face(
          [
            [cx - r, fy, cz],
            [cx + r, fy, cz],
          ],
          false,
        )}${face(
          [
            [cx, fy, cz - r],
            [cx, fy, cz + r],
          ],
          false,
        )}"/>`,
      );
    } else if (s.key === "ready") {
      const ring = Array.from({ length: 28 }, (_, i) => {
        const t = (i / 28) * Math.PI * 2;
        return [cx + Math.cos(t) * r, fy, cz + Math.sin(t) * r] as K.Point3;
      });
      out.push(`<path class="screen-dot" d="${face(ring)}"/>`);
    } else {
      const bw = (sx1 - sx0) * 0.32;
      const bh = (sz1 - sz0) * 0.34;
      out.push(
        `<path class="screen-hand" d="${face([
          [cx - bw - 3, fy, cz - bh / 2],
          [cx - 3, fy, cz - bh / 2],
          [cx - 3, fy, cz + bh / 2],
          [cx - bw - 3, fy, cz + bh / 2],
        ])}"/>`,
      );
      out.push(
        `<path class="screen-sixth" d="${face([
          [cx + 3, fy, cz - bh / 2],
          [cx + bw + 3, fy, cz - bh / 2],
          [cx + bw + 3, fy, cz + bh / 2],
          [cx + 3, fy, cz + bh / 2],
        ])}"/>`,
      );
    }
    screens.push(out.join(""));
  }
  return { base: out.join(""), screens };
}

const playhead = (t: number) =>
  face(
    [
      [tx(t), STRIP_Y - 10, TOP + 0.1],
      [tx(t), STRIP_Y + 16, TOP + 0.1],
    ],
    false,
  );

/** What the screen shows at second t, and whether the model reads that moment. */
function moment(t: number) {
  if (t < 7)
    return t >= 1 && t < 5
      ? "Rest: a cross. The model reads these 4 seconds as resting."
      : "Rest: a cross on the screen.";
  if (t < 8) return "Get ready: a grey circle.";
  return t >= 9 && t < 13
    ? "Imagine: the model reads these 4 seconds as the movement shown."
    : "Imagine: the screen shows the hand or the sixth finger, and the patient imagines moving it.";
}

const LABELS = [
  { title: "Rest", text: "a cross, 7 s" },
  { title: "Get ready", text: "a grey circle, 1 s" },
  { title: "Imagine", text: "hand or sixth finger, 6 s" },
];

/** What the patient sees in one trial, and the two 4 s pieces the model reads. */
export function PatientSees() {
  const { base, screens } = useMemo(() => art(), []);
  const [t, setT] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const from = useRef(0);

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const start = performance.now() - from.current * 1000;
    const step = (now: number) => {
      const next = (now - start) / 1000;
      if (next >= 14) {
        setT(14);
        setPlaying(false);
        return;
      }
      setT(next);
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const active = t === null ? null : SEGMENTS.findIndex((s) => t < s.to || s.key === "cue");
  return (
    <Plate
      title="One trial, as the patient sees it"
      hint={
        <>
          Drawn to scale as <PaperRef /> describes it: 7 s rest, 1 s get ready, 6 s imagining, 14 s in all. The brackets
          are the 4 seconds the model reads: one from the rest, one from the imagining.
        </>
      }
      className="plate-sees"
    >
      <svg
        className="iso-svg sees dotted"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Three screens: a cross, a grey circle, then the cue"
        data-scrub={t === null ? undefined : ""}
      >
        <g dangerouslySetInnerHTML={{ __html: base }} />
        {screens.map((html, i) => (
          <g
            key={i}
            className="sees-screen"
            data-on={active === i ? "" : undefined}
            dangerouslySetInnerHTML={{ __html: html }}
          />
        ))}
        {t !== null && <path className="sees-playhead" d={playhead(t)} />}
      </svg>
      <ol className="sees-labels">
        {LABELS.map((l, i) => (
          <li key={l.title} data-on={active === i ? "" : undefined}>
            <b>{l.title}</b> {l.text}
          </li>
        ))}
      </ol>
      <div className="scrub">
        <button
          type="button"
          className="scrub-play"
          onClick={() => {
            from.current = t === null || t >= 14 ? 0 : t;
            setPlaying((p) => !p);
          }}
        >
          {playing ? "Pause" : "Play the trial"}
        </button>
        <input
          type="range"
          min={0}
          max={14}
          step={0.1}
          value={t ?? 0}
          aria-label="Second of the trial"
          onChange={(e) => {
            setPlaying(false);
            setT(Number(e.target.value));
          }}
        />
        <span className="scrub-time">{(t ?? 0).toFixed(1)} s</span>
      </div>
      <p className="scrub-say" aria-live="polite">
        {t === null ? "Play the trial, or drag through it." : moment(t)}
      </p>
      <details className="aside">
        <summary>Why the demo&apos;s trials run about 15 s, not 14</summary>
        <p>
          In the recorded files the instruction to imagine comes about 8.6 s after the rest begins, not 8, and each
          trial starts about 15.5 s after the one before: every trial was started by a key press, and that pause is not
          in the paper&apos;s description. The model&apos;s 4 s pieces are cut from the times marked in the files, so
          the difference changes no result.
        </p>
      </details>
    </Plate>
  );
}
