import { Fragment, useMemo, type CSSProperties, type ReactNode } from "react";
import { data, pct } from "../data";
import { about, AGAIN_K, AGAIN_MIN, FIRST, REACH } from "../findings";
import { journeyArt, type Station } from "../iso/journey";
import { BuiltKey } from "./BuiltKey";

// A patient's visits, left to right, and the real system they would meet, each part drawn once:
// the cap and amplifier, the practice at the laptop with the server beside it, therapy with the
// finger, and a short practice again two weeks later. Arrows say what passes from one part to
// the next; what this project built is drawn solid and what a real system still needs dashed,
// and each step names its parts with the same key. Under the drawings, two lanes show the one
// choice that changes the story, whether the model starts from nothing or has already learned
// from other patients: the practice drawn to scale and the score it reaches, worked out from
// data.json as the setup and another-day answers work them out. Keep the parts in step with the
// report section on moving from the demo to a real limb.

type Lane = "scratch" | "transfer";

const LANES: { key: Lane; name: string }[] = [
  { key: "scratch", name: "Starting from nothing" },
  { key: "transfer", name: "Already learned from other patients" },
];

const L = data.later;
const LONGEST = Math.max(REACH.minutes, FIRST.minutes, AGAIN_MIN);

function Practice({ minutes, k, score, unchanged }: { minutes: number; k: number; score: number; unchanged?: number }) {
  return (
    <>
      <span className="jy-bar" style={{ "--share": minutes / LONGEST } as CSSProperties}>
        <i aria-hidden="true" />
        {about(minutes)}
      </span>
      <span className="jy-score">
        {k} trial{k > 1 ? "s" : ""} of each, then <b>{pct(score)} right</b>
        {unchanged !== undefined && <span className="jy-before">{pct(unchanged)} if not adjusted</span>}
      </span>
    </>
  );
}

interface Step {
  station: Station;
  visit: 1 | 2;
  /** What passes into this step's parts from the step before. */
  into?: string;
  name: string;
  text: string;
  /** The parts in the drawing, and whether this project built each. */
  parts?: { built: boolean; text: string }[];
  /** What else those parts need. */
  note?: string;
  lanes?: Record<Lane, ReactNode>;
}

const STEPS: Step[] = [
  {
    station: "cap",
    visit: 1,
    name: "Cap on",
    text: "The cap picks up the brain's signal, and an amplifier makes it strong enough to send.",
    parts: [{ built: false, text: "Cap and amplifier: needed" }],
  },
  {
    station: "practice",
    visit: 1,
    into: "brain signal, every 80 ms",
    name: "Practice",
    text: "The patient imagines each movement while the screen says which; a small bridge program sends the signal to the server, and the model learns from it.",
    parts: [
      { built: true, text: "This page: built" },
      { built: false, text: "Bridge: needed" },
      { built: true, text: "Server and model: built" },
    ],
    lanes: {
      scratch: <Practice minutes={REACH.minutes} k={REACH.k} score={REACH.mean} />,
      transfer: <Practice minutes={FIRST.minutes} k={FIRST.k} score={FIRST.mean} />,
    },
  },
  {
    station: "therapy",
    visit: 1,
    into: "a command every half second, from the last 4 s",
    name: "Therapy",
    text: "They imagine moving, and a small board turns each command into a turn of the motor that bends the finger.",
    parts: [{ built: false, text: "Board, motor and finger: needed" }],
    note: "Before any test with patients, the motor also needs safety limits and an emergency stop.",
  },
  {
    station: "calendar",
    visit: 2,
    name: "Practice again",
    text: "The cap never sits quite as before, so the first day's model is adjusted to a short practice.",
    lanes: {
      scratch: <Practice minutes={AGAIN_MIN} k={AGAIN_K} score={L.post.re_setup.mean} unchanged={L.post.as_is.mean} />,
      transfer: <span className="jy-none">Not tested</span>,
    },
  },
];

/** What passes from one part to the next: an arrow across on a projector, down when stacked. */
function Link({ to, text }: { to: Station; text: string }) {
  return (
    <p className="jy-link" data-to={to}>
      <span>{text}</span>
      <svg className="jy-arrow-right" viewBox="0 0 100 12" preserveAspectRatio="none" aria-hidden="true">
        <path d="M0 6h96M90 1l7 5-7 5" />
      </svg>
      <svg className="jy-arrow-down" viewBox="0 0 12 36" aria-hidden="true">
        <path d="M6 0v34M1 28l5 7 5-7" />
      </svg>
    </p>
  );
}

function Lanes({ lanes }: { lanes: Record<Lane, ReactNode> }) {
  return (
    <dl className="jy-lanes">
      {LANES.map((l) => (
        <div key={l.key} data-lane={l.key}>
          <dt>{l.name}</dt>
          <dd>{lanes[l.key]}</dd>
        </div>
      ))}
    </dl>
  );
}

const VISITS = ["First visit", "Two weeks later"];

/** The patient's visits, from the first day to two weeks later, and the parts of the system they meet. */
export function Journey() {
  const art = useMemo(() => journeyArt(), []);
  const widest = Math.max(...Object.values(art).map((a) => a.w));
  return (
    <figure
      className="journey bleed"
      id="journey"
      aria-label="A patient's visits, from the first day to two weeks later, with the parts of the system this project built drawn solid and those still needed drawn dashed"
    >
      <div className="jy">
        <BuiltKey />
        {VISITS.map((visit, v) => (
          <div key={visit} className="jy-visit" data-visit={v + 1}>
            <h3>{visit}</h3>
            {STEPS.filter((s) => s.visit === v + 1).map((s) => (
              <Fragment key={s.station}>
                {s.into && <Link to={s.station} text={s.into} />}
                <section className="jy-step" data-station={s.station} aria-label={s.name}>
                  <svg
                    className="iso-svg"
                    viewBox={`0 ${art[s.station].y} ${art[s.station].w} ${art[s.station].h}`}
                    style={{ "--k": art[s.station].w / widest } as CSSProperties}
                    aria-hidden="true"
                  >
                    <g dangerouslySetInnerHTML={{ __html: art[s.station].svg }} />
                  </svg>
                  <div className="jy-words">
                    <p className="jy-name">{s.name}</p>
                    <p className="jy-text">{s.text}</p>
                    {s.parts && (
                      <ul className="jy-parts">
                        {s.parts.map((t) => (
                          <li key={t.text} data-built={t.built ? "" : undefined}>
                            {t.text}
                          </li>
                        ))}
                      </ul>
                    )}
                    {s.note && <p className="jy-note">{s.note}</p>}
                  </div>
                  {s.lanes && <Lanes lanes={s.lanes} />}
                </section>
              </Fragment>
            ))}
          </div>
        ))}
        {LANES.map((l) => (
          <p key={l.key} className="jy-lane" data-lane={l.key} aria-hidden="true">
            {l.name}
          </p>
        ))}
        {LANES.map((l) => (
          <i key={l.key} className="jy-track" data-lane={l.key} aria-hidden="true" />
        ))}
      </div>
      <figcaption className="figure-note">
        Right: how often the model tells rest, hand and sixth finger apart, on trials it never saw; guessing gets{" "}
        {pct(1 / 3)}.
      </figcaption>
    </figure>
  );
}
