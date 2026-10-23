import { useMemo, useState, type PointerEvent } from "react";
import { data, pct } from "../data";
import { journeyArt, type Station } from "../iso/journey";

// A patient's whole path through using the system, one step after another: the cap, the
// practice, the model, therapy, and back on the clinic's schedule two weeks and a month later.
// The switch picks how the model starts; practice and scores follow from data.json, worked
// out as answer 2 works them out. Parts a real system would still need are drawn dashed;
// keep them in step with RealPipeline and the report section on moving to a real limb.

type Start = "scratch" | "transfer";

const S = data.calibration.scratch;
const T = data.calibration.transfer;
const L = data.later;
const perTrialPair = T[0].minutes / T[0].k; // one practice trial of each movement, in minutes
const reach = S.find((p) => p.mean >= T[0].mean - 0.005) ?? S[S.length - 1];
const RESETUP_K = 5; // the practice on a later day, as answer 5 tested it

const DAY_ONE: Record<Start, { k: number; minutes: number; score: number }> = {
  scratch: { k: reach.k, minutes: reach.minutes, score: reach.mean },
  transfer: { k: T[0].k, minutes: T[0].minutes, score: T[0].mean },
};

const LONGEST = Math.max(DAY_ONE.scratch.minutes, DAY_ONE.transfer.minutes, RESETUP_K * perTrialPair);

const time = (min: number) =>
  min < 1 ? `about ${Math.round((min * 60) / 10) * 10} s` : `about ${Math.round(min)} min`;
const trials = (k: number) => `${k} trial${k > 1 ? "s" : ""} of each movement`;

interface Step {
  station: Station;
  name: string;
  /** Under the name: how long, or how often it is right ("not tested" where the page has no score). */
  meta?: (start: Start) => { text: string; score?: boolean };
  say: (start: Start) => string;
  /** How much of the practice track the bar fills: the practice against the longest shown. */
  share?: (start: Start) => number;
}

interface Group {
  key: string;
  /** A day's name; the gaps between days have none. */
  day?: string;
  steps: Step[];
}

const CAP: Step = {
  station: "cap",
  name: "Cap on",
  say: () => "A real system needs the headset streaming live, and a bridge to the server. Here, recordings replay.",
};
const THERAPY: Step = {
  station: "therapy",
  name: "Therapy",
  say: () => "The patient imagines moving, the switch turns on, and the finger bends.",
};
const scored = (score: number | null) =>
  score === null ? { text: "not tested" } : { text: `${pct(score)} right`, score: true };

const GROUPS: Group[] = [
  {
    key: "day-1",
    day: "Day 1",
    steps: [
      CAP,
      {
        station: "practice",
        name: "Practice",
        share: (s) => DAY_ONE[s].minutes / LONGEST,
        meta: (s) => ({ text: time(DAY_ONE[s].minutes) }),
        say: (s) => `${trials(DAY_ONE[s].k)}, imagined while the screen says which.`,
      },
      {
        station: "model",
        name: "Model learns",
        meta: (s) => scored(DAY_ONE[s].score),
        say: (s) =>
          s === "scratch"
            ? "The model learns this patient from the practice alone, in seconds."
            : "The model, already taught by other patients, adjusts to this one in seconds.",
      },
      THERAPY,
    ],
  },
  {
    key: "gap-1",
    steps: [
      { station: "calendar", name: "Two weeks later", say: () => "The clinic's schedule brings the patient back." },
    ],
  },
  {
    key: "day-2",
    day: "Day 2",
    steps: [
      { ...CAP, say: () => "The cap never sits quite as before, so the signals look a little different." },
      {
        station: "practice",
        name: "Practice",
        share: () => (RESETUP_K * perTrialPair) / LONGEST,
        meta: () => ({ text: time(RESETUP_K * perTrialPair) }),
        say: () => `A few practice trials: ${trials(RESETUP_K)}.`,
      },
      {
        station: "model",
        name: "Model adjusted",
        meta: (s) => scored(s === "scratch" ? L.post.re_setup.mean : null),
        say: (s) =>
          s === "scratch"
            ? "The first day's model is adjusted to today's practice."
            : "The first day's model is adjusted to today's practice; we tested this only for the model that started from nothing.",
      },
      THERAPY,
    ],
  },
  {
    key: "gap-2",
    steps: [{ station: "calendar", name: "A month later", say: () => "Another visit on the clinic's schedule." }],
  },
  {
    key: "day-3",
    day: "Day 3",
    steps: [
      {
        station: "model",
        name: "Same as day 2",
        meta: (s) => scored(s === "scratch" ? L.follow.re_setup.mean : null),
        say: () => "Cap on, a few practice trials, the model adjusted, then therapy.",
      },
    ],
  },
];

const STEPS = GROUPS.flatMap((g) => g.steps.map((step) => ({ group: g.key, step })));
/** Where each group's first step sits in STEPS. */
const FIRST = GROUPS.map((_, gi) => GROUPS.slice(0, gi).reduce((n, g) => n + g.steps.length, 0));

/** The patient's path from the first day to a month later, one step at a time. */
export function Journey() {
  const art = useMemo(() => journeyArt(), []);
  const [start, setStart] = useState<Start>("scratch");
  const [hover, setHover] = useState<number | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const shown = hover ?? picked;
  const said = shown === null ? null : STEPS[shown].step.say(start);
  const shownGroup = shown === null ? null : STEPS[shown].group;
  // Only a mouse hovers; a tap picks, and stays picked until another.
  const enter = (i: number) => (e: PointerEvent) => {
    if (e.pointerType === "mouse") setHover(i);
  };
  const say = (wide: boolean) => (
    <p className={wide ? "journey-say journey-say-wide" : "journey-say journey-say-narrow"} aria-live="polite">
      {said ?? <span className="journey-hint">Point at or tap a step.</span>}
    </p>
  );
  return (
    <figure
      className="journey bleed"
      id="journey"
      data-shown={shown === null ? undefined : ""}
      aria-label="A patient's path through using the system, day by day"
    >
      <div className="journey-top">
        <h3 className="journey-title">A patient&apos;s path, day by day</h3>
        <div className="toggle" role="radiogroup" aria-label="The model starts">
          {(["scratch", "transfer"] as Start[]).map((v) => (
            <button key={v} type="button" role="radio" aria-checked={start === v} onClick={() => setStart(v)}>
              {v === "scratch" ? "Starting from nothing" : "Already learned from other patients"}
            </button>
          ))}
        </div>
        <ul className="journey-key">
          <li data-built="">
            <b>Built in this project</b> the model and its move-or-rest switch, on the server or in the browser, and the
            replay of real recordings
          </li>
          <li>
            <b>Needed in a real system</b> a headset streaming live, the bridge to the server, the finger itself, the
            clinic&apos;s schedule
          </li>
        </ul>
      </div>
      <ol className="journey-days" onPointerLeave={() => setHover(null)}>
        {GROUPS.map((g, gi) => (
          <li key={g.key} className={g.day ? "journey-day" : "journey-gap"} data-group={g.key}>
            {g.day && <h4 className="journey-day-name">{g.day}</h4>}
            <ol className="journey-steps">
              {g.steps.map((step, si) => {
                const i = FIRST[gi] + si;
                const { svg, w, h } = art.draw(step.station, step.share?.(start));
                const meta = step.meta?.(start);
                return (
                  <li key={i} data-station={step.station}>
                    <button
                      type="button"
                      className="journey-step"
                      data-on={shown === i ? "" : undefined}
                      onPointerEnter={enter(i)}
                      onFocus={() => setPicked(i)}
                      onClick={() => setPicked(i)}
                    >
                      <svg className="iso-svg" viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
                        <g dangerouslySetInnerHTML={{ __html: svg }} />
                      </svg>
                      <span className="journey-node" aria-hidden="true" />
                      <span className="journey-name">{step.name}</span>
                      <span className="journey-meta" data-score={meta?.score ? "" : undefined}>
                        {meta?.text ?? ""}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
            {shownGroup === g.key && say(false)}
          </li>
        ))}
      </ol>
      {say(true)}
      <figcaption className="journey-note">
        Scores: how often the model tells rest, hand and sixth finger apart on trials it never saw; guessing gets{" "}
        {pct(1 / 3)}.
      </figcaption>
    </figure>
  );
}
