import { Fragment, useMemo, type CSSProperties } from "react";
import { buildPipeline } from "../iso/pipeline";
import { BuiltKey } from "./BuiltKey";

// What a real system would be, part by part, with what passes along each link and which parts
// this project has built: the model, the server and this page. The rest is drawn dashed.
// Keep this in step with the report section on moving from the demo to a real limb.

interface Station {
  name: string;
  text: string;
  art: string;
  /** What passes along the link into this station from the one before. */
  into?: string;
  status: { built: boolean; text: string }[];
}

const STATIONS: Station[] = [
  {
    name: "EEG cap and amplifier",
    text: "Pick up the brain's tiny voltage and make it strong enough to send.",
    art: "A head in an EEG cap, wired to an amplifier",
    status: [{ built: false, text: "Needed" }],
  },
  {
    name: "Laptop",
    text: "A small bridge program passes the signal on; the screen shows this page.",
    art: "A laptop showing the model's three lamps",
    into: "brain signal, every 80 ms",
    status: [
      { built: true, text: "This page: built" },
      { built: false, text: "Bridge: needed" },
    ],
  },
  {
    name: "Server",
    text: "Runs the model, on the laptop itself or online.",
    art: "A small server box running the model",
    into: "4 s windows → a command every half second",
    status: [{ built: true, text: "Built" }],
  },
  {
    name: "Finger board and motor",
    text: "Turn each command into a turn of the motor, and the finger bends.",
    art: "A small circuit board wired to a motor that bends the robotic finger",
    into: "command → motor",
    status: [{ built: false, text: "Needed" }],
  },
];

/** The real system's pipeline, left to right; the stations stack on narrow screens. */
export function RealPipeline() {
  const art = useMemo(() => buildPipeline(), []);
  const cols = art.map((a) => `minmax(0, ${a.w}fr)`).join(" var(--pipe-link) ");
  return (
    <figure
      className="real bleed"
      aria-label="A real brain-computer interface, part by part: EEG cap and amplifier, laptop, server, finger board and motor"
    >
      <BuiltKey />
      <div className="pipe" style={{ "--pipe-cols": cols } as CSSProperties}>
        {STATIONS.map((s, i) => (
          <Fragment key={s.name}>
            {s.into && (
              <p className="pipe-link">
                <span>{s.into}</span>
                <svg className="pipe-across" viewBox="0 0 100 12" preserveAspectRatio="none" aria-hidden="true">
                  <path d="M0 6h96M90 1l7 5-7 5" />
                </svg>
                <svg className="pipe-down" viewBox="0 0 12 36" aria-hidden="true">
                  <path d="M6 0v34M1 28l5 7 5-7" />
                </svg>
              </p>
            )}
            <div className="pipe-station" style={{ "--w": art[i].w } as CSSProperties}>
              <svg className="iso-svg" viewBox={`0 0 ${art[i].w} ${art[i].h}`} role="img" aria-label={s.art}>
                <g dangerouslySetInnerHTML={{ __html: art[i].svg }} />
              </svg>
              <div className="pipe-say">
                <p>
                  <b>{s.name}</b> {s.text}
                </p>
                <p className="pipe-tags">
                  {s.status.map((t) => (
                    <span key={t.text} className="pipe-tag" data-built={t.built ? "" : undefined}>
                      {t.text}
                    </span>
                  ))}
                </p>
              </div>
            </div>
          </Fragment>
        ))}
      </div>
    </figure>
  );
}
