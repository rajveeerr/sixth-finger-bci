import { Plate } from "../../components/Plate";
import { data } from "../data";
import { scale, swarm, useWidth } from "../useWidth";

const ROWS = [
  { key: "affected_hand", label: "Affected hand", colour: "var(--hand)" },
  { key: "sixth_finger", label: "Sixth finger", colour: "var(--sixth)" },
] as const;

/** Fig. 6: how far the mu rhythm fell in each patient while they imagined each movement. */
export function Rhythm() {
  const [ref, w] = useWidth<HTMLDivElement>();
  const narrow = w < 460;
  const left = narrow ? 8 : 118;
  const right = w - 16;
  const rowH = narrow ? 92 : 78;
  const top = 18;
  const h = top + rowH * ROWS.length + 34;
  const x = scale(-80, 20, left, right);
  const ticks = [-80, -60, -40, -20, 0, 20];
  return (
    <Plate
      fig={6}
      title="What the decoder looks for"
      hint="Each dot is one patient"
      readout="mu rhythm, 8 to 13 Hz, at C3"
      caption={
        <>
          Imagining a movement quiets the brain&apos;s <strong>mu rhythm</strong> over the hand area. While these
          patients imagined, it fell by about a third against the second before the cue, in 22 of 22 for the
          sixth finger.
        </>
      }
    >
      <div ref={ref}>
        <svg className="fig-svg" width={w} height={h} role="img" aria-label="Fall in mu power per patient">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={top - 6} y2={h - 30} className={t === 0 ? "axis-zero" : "grid"} />
              <text x={x(t)} y={h - 12} textAnchor="middle">
                {t > 0 ? `+${t}%` : t < 0 ? `−${-t}%` : "0"}
              </text>
            </g>
          ))}
          {ROWS.map((row, i) => {
            const d = data.erd[row.key];
            const y0 = top + rowH * i + (narrow ? 50 : rowH / 2);
            const dy = swarm(d.values, x, 4.5);
            return (
              <g key={row.key}>
                <text x={narrow ? left : 0} y={narrow ? y0 - 32 : y0 + 4} className="serif strong">
                  {row.label}
                </text>
                {d.values.map((v, j) => (
                  <circle key={j} cx={x(v)} cy={y0 + dy[j]} r={4.5} fill={row.colour} fillOpacity={0.55}
                    stroke={row.colour} strokeWidth={1} />
                ))}
                <line x1={x(d.mean)} x2={x(d.mean)} y1={y0 - 20} y2={y0 + 20} className="mean-mark" />
                <text x={x(d.mean)} y={y0 - 25} textAnchor="middle" className="strong">
                  −{Math.round(-d.mean)}%
                </text>
              </g>
            );
          })}
          <text x={x(0) + 6} y={top + 4} className="note">
            no change
          </text>
        </svg>
      </div>
    </Plate>
  );
}
