import { Fragment, useId, useMemo, type CSSProperties } from "react";
import { buildPipeline } from "../iso/pipeline";

// What a real system would be, part by part, with what passes along each link and which
// parts this project has built: the model, the server and this page. The rest is hatched.
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
    text: "The cap's sensors pick up the brain's tiny voltage, and the amplifier makes it strong enough to send.",
    art: "A head in an EEG cap, wired to an amplifier",
    status: [{ built: false, text: "Not built yet" }],
  },
  {
    name: "Laptop",
    text: "A small bridge program passes the signal on, and the screen shows this page.",
    art: "A laptop showing the model's three lamps",
    into: "brain signal, every 80 ms",
    status: [
      { built: true, text: "This page: built" },
      { built: false, text: "Bridge: not built yet" },
    ],
  },
  {
    name: "Server",
    text: "Runs the model. It can run on the laptop itself or online.",
    art: "A small server box running the model",
    into: "4 s windows → a command every half second",
    status: [{ built: true, text: "Built" }],
  },
  {
    name: "Finger board and motor",
    text: "A small microcontroller board turns each command into a turn of the motor, and the robotic finger bends.",
    art: "A small circuit board wired to a motor that bends the robotic finger",
    into: "command → motor",
    status: [{ built: false, text: "Not built yet" }],
  },
];

/** The real system's pipeline, left to right; the stations stack on narrow screens. */
export function RealPipeline() {
  const hatch = `pipe-hatch-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const art = useMemo(() => buildPipeline(`url(#${hatch})`), [hatch]);
  const cols = art.map((a) => `minmax(0, ${a.w}fr)`).join(" var(--pipe-link) ");
  return (
    <div className="pipe" style={{ "--pipe-cols": cols } as CSSProperties}>
      <svg className="pipe-defs" width="0" height="0" aria-hidden="true">
        <defs>
          <pattern id={hatch} patternUnits="userSpaceOnUse" width="4" height="4" patternTransform="rotate(45)">
            <path d="M0 0V4" />
          </pattern>
        </defs>
      </svg>
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
  );
}
