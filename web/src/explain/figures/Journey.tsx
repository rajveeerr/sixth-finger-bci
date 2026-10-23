import { useMemo, type CSSProperties, type ReactNode } from "react";
import { data, pct } from "../data";
import { about, AGAIN_K, AGAIN_MIN, FIRST, REACH, timesWord } from "../findings";
import { journeyArt, type Station } from "../iso/journey";
import { BuiltKey } from "./BuiltKey";

// A patient's visits, left to right: the cap, the practice with the model beside it, therapy,
// and a short practice again two weeks later. Under the drawings, two lanes show the one choice
// that changes the story, whether the model starts from nothing or has already learned from
// other patients: the practice drawn to scale and the score it reaches, worked out from
// data.json as the setup and another-day answers work them out. Parts a real system would
// still need are drawn dashed; keep them in step with RealPipeline.

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
  name: string;
  text: string;
  lanes?: Record<Lane, ReactNode>;
  /** Said once for both lanes. */
  across?: ReactNode;
}

const STEPS: Step[] = [
  { station: "cap", visit: 1, name: "Cap on", text: "The cap picks up the brain's signal." },
  {
    station: "practice",
    visit: 1,
    name: "Practice",
    text: "The patient imagines each movement while the screen says which, and the model learns from it.",
    lanes: {
      scratch: <Practice minutes={REACH.minutes} k={REACH.k} score={REACH.mean} />,
      transfer: <Practice minutes={FIRST.minutes} k={FIRST.k} score={FIRST.mean} />,
    },
  },
  {
    station: "therapy",
    visit: 1,
    name: "Therapy",
    text: "They imagine moving, and the finger bends.",
    across: (
      <>
        Played as if live, the demo&apos;s model catches <b>{pct(data.switch.detection)}</b> of imagined movements, and
        switches on by mistake about {timesWord(data.switch.false_per_minute)} a minute of rest.
      </>
    ),
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

/** The patient's visits, from the first day to two weeks later, for both ways the model can start. */
export function Journey() {
  const art = useMemo(() => journeyArt(), []);
  const widest = Math.max(...Object.values(art).map((a) => a.w));
  return (
    <figure
      className="journey bleed"
      id="journey"
      aria-label="A patient's visits, from the first day to two weeks later"
    >
      <div className="jy">
        <BuiltKey />
        {VISITS.map((visit, v) => (
          <div key={visit} className="jy-visit" data-visit={v + 1}>
            <h3>{visit}</h3>
            {STEPS.filter((s) => s.visit === v + 1).map((s) => (
              <section key={s.station} className="jy-step" data-station={s.station} aria-label={s.name}>
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
                </div>
                {s.lanes && <Lanes lanes={s.lanes} />}
                {s.across && <p className="jy-across">{s.across}</p>}
              </section>
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
