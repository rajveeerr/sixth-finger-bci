import { useEffect, useRef, useState, type ReactNode } from "react";

// Small charts in the page's hand: hairline axes, ink dots, direct labels, nothing filled
// that does not carry a number. They lay themselves out in real pixels, so the type is the
// same size on a phone and on a projector.

/** The width of an element, kept up to date. */
export function useWidth<T extends HTMLElement>(fallback = 600) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      const w = Math.round(entry.contentRect.width);
      if (w > 0) setWidth(w);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** A linear map from a domain to pixels. */
export const scale = (d0: number, d1: number, r0: number, r1: number) => (v: number) =>
  r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);

/** Vertical offsets that keep dots of radius r from overlapping along x (a small beeswarm). */
export function swarm(values: number[], x: (v: number) => number, r: number, maxRows = 3): number[] {
  const placed: { x: number; y: number }[] = [];
  const out = new Array<number>(values.length).fill(0);
  const slots = [0];
  for (let k = 1; k <= maxRows; k++) slots.push(-k, k);
  const order = values.map((v, i) => ({ v, i })).sort((a, b) => a.v - b.v);
  for (const { v, i } of order) {
    const px = x(v);
    const slot = slots.find((s) => placed.every((p) => Math.hypot(p.x - px, p.y - s * r * 1.95) >= r * 1.95)) ?? 0;
    placed.push({ x: px, y: slot * r * 1.95 });
    out[i] = slot * r * 1.95;
  }
  return out;
}

const pct = (v: number) => `${Math.round(v * 100)}%`;

export interface StripRow {
  label?: string;
  values: number[];
  mean: number;
  colour?: string;
}

/** One dot per patient on a scale, the mean marked, and where guessing (or no change) sits. */
export function DotStrip({
  rows,
  domain,
  ticks,
  format = pct,
  marker,
  label,
}: {
  rows: StripRow[];
  domain: [number, number];
  ticks: number[];
  format?: (v: number) => string;
  marker?: { at: number; text: string };
  label: string;
}) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<{ row: number; i: number } | null>(null);
  const labelled = rows.some((r) => r.label) && w >= 520;
  const left = labelled ? 190 : 18;
  const right = w - 18;
  // On a narrow screen the row's name goes above its dots, clear of the mean's value.
  const rowH = labelled ? (rows.length > 1 ? 62 : 70) : 84;
  const top = labelled ? 26 : 40;
  const h = top + rowH * rows.length + 26;
  const x = scale(domain[0], domain[1], left, right);
  return (
    <div ref={ref} className="chart">
      <svg width={w} height={h} role="img" aria-label={label}>
        {marker && (
          <g className="chart-marker">
            <line x1={x(marker.at)} x2={x(marker.at)} y1={top - 6} y2={h - 24} />
            <text x={x(marker.at) + 6} y={top - 10} className="chart-italic">
              {marker.text}
            </text>
          </g>
        )}
        {rows.map((row, i) => {
          const y0 = top + rowH * i + rowH / 2;
          const dy = swarm(row.values, x, 4.3);
          return (
            <g key={row.label ?? i}>
              {row.label && (
                <text x={labelled ? 0 : left} y={labelled ? y0 + 4 : y0 - 38} className="chart-row">
                  {row.label}
                </text>
              )}
              {row.values.map((v, j) => (
                <circle
                  key={j}
                  cx={x(v)}
                  cy={y0 + dy[j]}
                  r={hover?.row === i && hover.i === j ? 6 : 4.3}
                  className="chart-dot"
                  style={{ fill: row.colour }}
                  onPointerEnter={() => setHover({ row: i, i: j })}
                  onPointerLeave={() => setHover(null)}
                />
              ))}
              {hover?.row === i && (
                <text x={x(row.values[hover.i])} y={y0 + dy[hover.i] + 22} textAnchor="middle" className="chart-pop">
                  one patient: {format(row.values[hover.i])}
                </text>
              )}
              <line x1={x(row.mean)} x2={x(row.mean)} y1={y0 - 17} y2={y0 + 17} className="chart-mean" />
              <text x={x(row.mean)} y={y0 - 22} textAnchor="middle" className="chart-value">
                {format(row.mean)}
              </text>
            </g>
          );
        })}
        <line x1={left} x2={right} y1={h - 20} y2={h - 20} className="chart-axis" />
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={h - 20} y2={h - 16} className="chart-axis" />
            <text x={x(t)} y={h - 3} textAnchor="middle" className="chart-tick">
              {format(t)}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

/** Each patient scored two ways, one line between the two scores. */
export function Slope({
  a,
  b,
  labels,
  guess,
  band,
  label,
  names,
}: {
  a: number[];
  b: number[];
  labels: [ReactNode, ReactNode];
  guess: number;
  band?: { from: number; to: number; text: string };
  label: string;
  /** Who each line is, named in the readout when the reader points at it. */
  names?: string[];
}) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const h = 220;
  const top = 12;
  const bottom = h - 10;
  const y = scale(0.38, 1, bottom, top);
  const xa = Math.max(90, w * 0.24);
  const xb = Math.min(w - 90, w * 0.76);
  const mean = (v: number[]) => v.reduce((s, x) => s + x, 0) / v.length;
  const ma = mean(a);
  const mb = mean(b);
  return (
    <div ref={ref} className="chart">
      <svg width={w} height={h} role="img" aria-label={label}>
        {[0.4, 0.6, 0.8, 1].map((t) => (
          <g key={t}>
            <line x1={xa} x2={xb} y1={y(t)} y2={y(t)} className="chart-grid" />
            <text x={xb + 12} y={y(t) + 4} className="chart-tick">
              {pct(t)}
            </text>
          </g>
        ))}
        <line x1={xa} x2={xb} y1={y(guess)} y2={y(guess)} className="chart-guess" />
        <text x={(xa + xb) / 2} y={y(guess) + 18} textAnchor="middle" className="chart-italic">
          guessing
        </text>
        {band && (
          <g>
            <line
              x1={xa - 14}
              x2={xa - 4}
              y1={y((band.from + band.to) / 2)}
              y2={y((band.from + band.to) / 2)}
              className="chart-mean"
            />
            <text x={xa - 18} y={y((band.from + band.to) / 2) + 4} textAnchor="end" className="chart-italic">
              {band.text}
            </text>
          </g>
        )}
        {a.map((v, i) => (
          <line
            key={i}
            x1={xa}
            y1={y(v)}
            x2={xb}
            y2={y(b[i])}
            className="chart-slope"
            data-on={hover === i ? "" : undefined}
          />
        ))}
        <line x1={xa} y1={y(ma)} x2={xb} y2={y(mb)} className="chart-slope-mean" />
        <circle cx={xa} cy={y(ma)} r={4} className="chart-end" />
        <circle cx={xb} cy={y(mb)} r={4} className="chart-end" />
        <text x={xa - 12} y={y(ma) + 20} textAnchor="end" className="chart-value">
          {pct(ma)}
        </text>
        <text x={xb - 10} y={y(mb) + 20} textAnchor="end" className="chart-value">
          {pct(mb)}
        </text>
        {hover !== null && (
          <g className="chart-pick">
            <circle cx={xa} cy={y(a[hover])} r={4} />
            <circle cx={xb} cy={y(b[hover])} r={4} />
            <text x={xa - 12} y={y(a[hover]) + 4} textAnchor="end" className="chart-pop">
              {pct(a[hover])}
            </text>
            <text x={xb + 12} y={y(b[hover]) + 4} className="chart-pop">
              {pct(b[hover])}
            </text>
          </g>
        )}
        {a.map((v, i) => (
          <line
            key={i}
            x1={xa}
            y1={y(v)}
            x2={xb}
            y2={y(b[i])}
            className="chart-hit"
            onPointerEnter={() => setHover(i)}
            onPointerLeave={() => setHover(null)}
          />
        ))}
      </svg>

      <div className="chart-columns" style={{ marginLeft: xa - 80, width: xb - xa + 160 }}>
        <span>{labels[0]}</span>
        <span>{labels[1]}</span>
      </div>
      <p className="chart-say" aria-live="polite">
        {hover === null
          ? "Point at a line to see one patient."
          : `${names?.[hover] ?? "One patient"}: ${pct(a[hover])} the published way, ${pct(b[hover])} tested fairly.`}
      </p>
    </div>
  );
}

export interface Series {
  label: string;
  points: { x: number; y: number; lo: number; hi: number }[];
  muted?: boolean;
}

/** Accuracy against setup time, with the 95% interval as a faint band. */
export function Curves({
  series,
  guess,
  label,
  reach,
  at,
}: {
  series: Series[];
  guess: number;
  label: string;
  /** Mark how long the second series takes to reach the first series' first value. */
  reach?: { minutes: number; text: string };
  /** The x the reader picked: a guide line, and each series' point there ringed. */
  at?: number;
}) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const h = 240;
  const left = 78;
  const right = w - 8;
  const top = 14;
  const bottom = h - 42;
  const x = scale(0, 10, left, right);
  const y = scale(0.3, 0.7, bottom, top);
  return (
    <div ref={ref} className="chart">
      <svg width={w} height={h} role="img" aria-label={label}>
        {[0.4, 0.5, 0.6, 0.7].map((t) => (
          <g key={t}>
            <line x1={left} x2={right} y1={y(t)} y2={y(t)} className="chart-grid" />
            <text x={left - 44} y={y(t) + 4} textAnchor="end" className="chart-tick">
              {pct(t)}
            </text>
          </g>
        ))}
        <line x1={left} x2={right} y1={y(guess)} y2={y(guess)} className="chart-guess" />
        <text x={right} y={y(guess) - 6} textAnchor="end" className="chart-italic">
          guessing
        </text>
        <line x1={left} x2={right} y1={bottom} y2={bottom} className="chart-axis" />
        {[0, 2, 4, 6, 8, 10].map((m) => (
          <text key={m} x={x(m)} y={bottom + 17} textAnchor="middle" className="chart-tick">
            {m}
          </text>
        ))}
        <text x={(left + right) / 2} y={bottom + 36} textAnchor="middle" className="chart-tick">
          minutes the new patient spends on practice trials
        </text>
        {reach && series[0] && (
          <g className="chart-reach">
            <line
              x1={x(series[0].points[0].x)}
              x2={x(reach.minutes)}
              y1={y(series[0].points[0].y)}
              y2={y(series[0].points[0].y)}
            />
            <line x1={x(reach.minutes)} x2={x(reach.minutes)} y1={y(series[0].points[0].y)} y2={bottom} />
            <text x={x(reach.minutes) + 6} y={bottom - 8} className="chart-italic">
              {reach.text}
            </text>
          </g>
        )}
        {at !== undefined && <line x1={x(at)} x2={x(at)} y1={top} y2={bottom} className="chart-guide" />}
        {series.map((s) => {
          const band =
            s.points.map((p, i) => `${i ? "L" : "M"}${x(p.x)} ${y(p.hi)}`).join("") +
            [...s.points]
              .reverse()
              .map((p) => `L${x(p.x)} ${y(p.lo)}`)
              .join("") +
            "Z";
          const line = s.points.map((p, i) => `${i ? "L" : "M"}${x(p.x)} ${y(p.y)}`).join("");
          const first = s.points[0];
          return (
            <g key={s.label} className={s.muted ? "chart-series muted" : "chart-series"}>
              <path d={band} className="chart-band" />
              <path d={line} className="chart-line" />
              {s.points.map((p) => (
                <circle key={p.x} cx={x(p.x)} cy={y(p.y)} r={p.x === at ? 5.5 : 3} className="chart-point" />
              ))}
              <text x={x(first.x) - 6} y={y(first.y) + 4} textAnchor="end" className="chart-value">
                {pct(first.y)}
              </text>
              <text x={x(first.x) + 10} y={y(first.y) + (s.muted ? 20 : -12)} className="chart-row">
                {s.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export interface BarRow {
  label: string;
  value: number;
  strong?: boolean;
}

/** A few labelled bars on one scale, with where guessing lands. */
export function Bars({ rows, guess, label }: { rows: BarRow[]; guess?: number; label: string }) {
  return (
    <div className="hbars" role="img" aria-label={label}>
      {rows.map((r) => (
        <div key={r.label} className="hbar" data-strong={r.strong ? "" : undefined}>
          <span className="hbar-label">{r.label}</span>
          <span className="hbar-track">
            <span className="hbar-fill" style={{ width: pct(r.value) }} />
            {guess !== undefined && <span className="hbar-guess" style={{ left: pct(guess) }} />}
          </span>
          <span className="hbar-value">{pct(r.value)}</span>
        </div>
      ))}
      {guess !== undefined && (
        <p className="hbar-note">
          <span className="hbar-guess-key" /> guessing, {pct(guess)}
        </p>
      )}
    </div>
  );
}
