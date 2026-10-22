import { Fragment, useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import { Plate } from "../../components/Plate";
import { useDemo } from "../../store";
import type { Prediction } from "../../stream/types";
import { data, pct } from "../data";
import { buildModel, CHANNELS, LAMPS, SFREQ, STAGES, VIEW_H, VIEW_W, WINDOW_S } from "../iso/model";

const { rhythms, sensors, combine, decide } = STAGES;

interface Step {
  kicker: string;
  title: string;
  note?: string;
  text: string;
}

const STEPS: Step[] = [
  {
    kicker: "In",
    title: `${WINDOW_S} s from ${CHANNELS} sensors`,
    note: `A drawing. The real lines hold ${(WINDOW_S * SFREQ).toLocaleString("en")} readings each.`,
    text: `What the model reads each time: ${WINDOW_S} seconds of signal from all ${CHANNELS} sensors, ${SFREQ} readings a second, so ${(WINDOW_S * SFREQ).toLocaleString("en")} from each. The lines here are drawn; the demo further down plays the real recordings.`,
  },
  {
    kicker: "Step 1",
    title: "Finds rhythms in time",
    note: `${rhythms.filters} patterns, each a quarter second long`,
    text: `It slides ${rhythms.filters} short patterns, each a quarter of a second (${rhythms.kernel} readings) long, along every sensor's line; each responds where the line carries its rhythm, such as the rhythm that fades when someone imagines moving (chapter 3). Out come ${rhythms.filters} copies of the ${CHANNELS} lines, one for each pattern. ${rhythms.learned} of the numbers it learned.`,
  },
  {
    kicker: "Step 2",
    title: "Finds which sensors matter",
    note: `${sensors.outputs} ways to weigh the ${CHANNELS} sensors`,
    text: `For each of those copies it learns ${sensors.perFilter} ways to weigh the ${CHANNELS} sensors and add them up, so some places on the head count for more than others. Out come ${sensors.outputs} lines, each then averaged ${sensors.pool} readings at a time. ${sensors.learned} of the numbers it learned.`,
  },
  {
    kicker: "Step 3",
    title: "Combines them",
    note: `${combine.outputs} short summaries of the ${WINDOW_S} s`,
    text: `It looks along each of the ${combine.outputs} lines for a pattern over another quarter of a second, mixes the ${combine.outputs} with one another and averages again, ${combine.pool} at a time. Out come ${combine.outputs} short summaries of ${combine.steps} numbers each, one for every eighth of a second. ${combine.learned} of the numbers it learned.`,
  },
  {
    kicker: "Step 4",
    title: "Decides",
    text: `It weighs all ${combine.outputs * combine.steps} numbers of those summaries into one score for each of the ${decide.classes} choices and turns the scores into how likely each is, adding up to 100%. The demo adds the hand's and the sixth finger's: together above rest is Move. ${decide.learned.toLocaleString("en")} of the numbers it learned, almost half of them.`,
  },
];

const PULSE_MS = 1500; // the pulse reaches the lamps after crossing the four arrows

const likeliest = (p: Prediction) => p.probs.indexOf(Math.max(...p.probs));

/** The model drawn from the 4 s it reads to the lamp it lights, one step at a time. */
export function ModelDrawing() {
  const art = useMemo(() => buildModel(), []);
  const root = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState<number | null>(null);
  const [shown, setShown] = useState<Prediction | null>(() => useDemo.getState().lastPrediction);
  const [pulse, setPulse] = useState(0);

  // Each new answer from the live demo runs once through the drawing, then lights its lamp;
  // off screen or with reduced motion the lamp just changes.
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    let visible = false;
    let timer = 0;
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
    });
    observer.observe(el);
    const unsubscribe = useDemo.subscribe((s, prev) => {
      const p = s.lastPrediction;
      if (p === prev.lastPrediction) return;
      window.clearTimeout(timer);
      if (!p || !visible || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        setShown(p);
        return;
      }
      setPulse((n) => n + 1);
      timer = window.setTimeout(() => setShown(p), PULSE_MS);
    });
    return () => {
      observer.disconnect();
      unsubscribe();
      window.clearTimeout(timer);
    };
  }, []);

  const lit = shown ? likeliest(shown) : -1;
  const live = shown
    ? ` Lit now: ${LAMPS[lit].label.toLowerCase()} (${pct(shown.probs[lit])}), the live demo's latest answer.`
    : "";
  const step = active === null ? null : STEPS[active];
  const readout = step ? (
    <>
      <b>{step.title}.</b> {step.text}
      {active === 4 && live}
    </>
  ) : (
    "Point at or tap a step to see what it does."
  );
  const d = data.demo;
  const pick = (i: number) => ({
    onPointerEnter: () => setActive(i),
    onPointerLeave: (e: PointerEvent) => e.pointerType === "mouse" && setActive(null),
    onFocus: () => setActive(i),
    onClick: () => setActive(i),
  });
  const station = (i: number, svg: string) => {
    const s = STEPS[i];
    return (
      <div className="mdraw-station" data-on={active === i ? "" : undefined} style={{ "--i": i } as CSSProperties}>
        <button
          type="button"
          className="mdraw-step"
          aria-label={`${s.title}. ${s.text}${i === 4 ? live : ""}`}
          {...pick(i)}
        >
          <span className="mdraw-art">
            {i > 0 && (
              <span className="mdraw-arrow" aria-hidden="true">
                {pulse > 0 && <i key={pulse} className="mdraw-dot" />}
              </span>
            )}
            <svg className="iso-svg" viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} aria-hidden="true">
              <g dangerouslySetInnerHTML={{ __html: svg }} />
            </svg>
          </span>
          <span className="mdraw-say">
            <span className="mdraw-kicker">{s.kicker}</span>
            <b>{s.title}</b>
            {i < 4 ? (
              <small>{s.note}</small>
            ) : (
              <span className="mdraw-lamps">
                {LAMPS.map((l, k) => (
                  <span key={l.name} data-class={l.name} data-on={k === lit ? "" : undefined}>
                    {l.label}
                    {shown && ` ${pct(shown.probs[k])}`}
                  </span>
                ))}
              </span>
            )}
          </span>
        </button>
      </div>
    );
  };
  return (
    <Plate
      title="What the model does with 4 seconds"
      hint="The signal passes through EEGNet's four steps to three lamps. The lines are a drawing; the lamps show the live demo's latest answer."
      readout={readout}
      className="plate-mdraw bleed"
      label="EEGNet drawn as four steps between the 4 s it reads and three lamps"
    >
      <div
        ref={root}
        className="mdraw"
        data-lit={lit >= 0 ? LAMPS[lit].name : undefined}
        data-active={active === null ? undefined : ""}
      >
        {station(0, art.input)}
        <p className="mdraw-net">
          <b>EEGNet</b> {d.parameters.toLocaleString("en")} numbers it learned, {Math.round(d.model_bytes / 1000)} KB
        </p>
        {art.steps.map((svg, k) => (
          <Fragment key={k}>{station(k + 1, svg)}</Fragment>
        ))}
      </div>
    </Plate>
  );
}
