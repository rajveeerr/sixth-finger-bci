import { Plate } from "../../components/Plate";
import { data, pct, type CurvePoint } from "../data";
import { scale, useWidth } from "../useWidth";

const LINES = [
  { key: "transfer", label: "Starting from other patients", className: "curve-transfer" },
  { key: "scratch", label: "From scratch", className: "curve-scratch" },
] as const;

/** Fig. 10: three-command accuracy of a new patient against minutes of calibration. */
export function Calibration() {
  const [ref, w] = useWidth<HTMLDivElement>();
  const h = 300;
  const left = 44;
  const right = w - 16;
  const top = 22;
  const bottom = h - 46;
  const x = scale(0, 10, left, right);
  const y = scale(0.3, 0.7, bottom, top);
  const path = (pts: CurvePoint[]) => pts.map((p, i) => `${i ? "L" : "M"}${x(p.minutes)} ${y(p.mean)}`).join("");
  const band = (pts: CurvePoint[]) =>
    `${pts.map((p, i) => `${i ? "L" : "M"}${x(p.minutes)} ${y(p.ci[1])}`).join("")}${[...pts]
      .reverse()
      .map((p) => `L${x(p.minutes)} ${y(p.ci[0])}`)
      .join("")}Z`;
  const start = { t: data.calibration.transfer[0], s: data.calibration.scratch[0] };
  return (
    <Plate
      fig={10}
      title="How much calibration a new patient needs"
      hint="Bands: 95% intervals over 22 patients"
      readout="three commands, chance 33%"
      caption={
        <>
          Starting from a decoder built on other patients, half a minute of a new patient&apos;s trials gives{" "}
          <strong>{pct(start.t.mean)}</strong>, where starting from scratch gives {pct(start.s.mean)} and needs
          about 5 minutes to catch up.
        </>
      }
    >
      <div ref={ref}>
        <svg className="fig-svg" width={w} height={h} role="img" aria-label="Accuracy against calibration minutes">
          {[0.3, 0.4, 0.5, 0.6, 0.7].map((t) => (
            <g key={t}>
              <line x1={left} x2={right} y1={y(t)} y2={y(t)} className="grid" />
              <text x={left - 8} y={y(t) + 4} textAnchor="end">
                {pct(t)}
              </text>
            </g>
          ))}
          <line x1={left} x2={right} y1={y(1 / 3)} y2={y(1 / 3)} className="chance" />
          <text x={right} y={y(1 / 3) - 6} textAnchor="end" className="note">
            chance
          </text>
          {[0, 2, 4, 6, 8, 10].map((m) => (
            <text key={m} x={x(m)} y={bottom + 20} textAnchor="middle">
              {m}
            </text>
          ))}
          <text x={(left + right) / 2} y={bottom + 38} textAnchor="middle">
            minutes of calibration trials
          </text>
          {LINES.map((l) => {
            const pts = data.calibration[l.key];
            const first = pts[0];
            return (
              <g key={l.key} className={l.className}>
                <path d={band(pts)} className="ci" />
                <path d={path(pts)} className="curve" />
                {pts.map((p) => (
                  <circle key={p.k} cx={x(p.minutes)} cy={y(p.mean)} r={3} className="curve-dot" />
                ))}
                <text x={x(first.minutes) + 8} y={y(first.mean) + (l.key === "transfer" ? -12 : 18)}
                  className={l.key === "transfer" ? "strong" : ""}>
                  {l.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </Plate>
  );
}
