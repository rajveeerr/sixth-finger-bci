import { Plate } from "../../components/Plate";
import { data, pct } from "../data";
import { scale, useWidth } from "../useWidth";

/** Fig. 9: the same method scored the published way and leak-free, one line per patient. */
export function Leak() {
  const [ref, w] = useWidth<HTMLDivElement>();
  const L = data.leak;
  const h = 330;
  const top = 34;
  const bottom = h - 42;
  const y = scale(0.3, 1, bottom, top);
  const xa = Math.max(70, w * 0.26);
  const xb = Math.min(w - 70, w * 0.74);
  const ticks = [0.4, 0.6, 0.8, 1];
  return (
    <Plate
      fig={9}
      title="Where the published 85% came from"
      hint="Each line is one patient"
      readout={`${L.n_positive} of ${L.subjects.length} fell, ${L.mean_diff_points} points on average`}
      caption={
        <>
          The dataset&apos;s own analysis fitted its spatial filters on all the data before splitting off a test
          set, so the test trials leaked into training. Rebuilt both ways, the same method (CSP with LDA) falls to{" "}
          <strong>{pct(L.mean_leakfree)}</strong>: near chance for telling the hand from the sixth finger.
        </>
      }
    >
      <div ref={ref}>
        <svg className="fig-svg" width={w} height={h} role="img" aria-label="Accuracy with and without the leak">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={xa} x2={xb} y1={y(t)} y2={y(t)} className="grid" />
              <text x={xb + 8} y={y(t) + 4}>
                {pct(t)}
              </text>
            </g>
          ))}
          <line x1={xa} x2={xb} y1={y(0.5)} y2={y(0.5)} className="chance" />
          <text x={(xa + xb) / 2} y={y(0.5) + 16} textAnchor="middle" className="note">
            chance
          </text>
          {/* the authors' reported range, on the left axis */}
          <rect x={xa - 4} y={y(L.published[1])} width={8} height={Math.max(2, y(L.published[0]) - y(L.published[1]))}
            className="published" />
          <text x={xa - 10} y={(y(L.published[0]) + y(L.published[1])) / 2 + 4} textAnchor="end" className="strong">
            published
          </text>
          {L.replica.map((a, i) => (
            <line key={L.subjects[i]} x1={xa} y1={y(a)} x2={xb} y2={y(L.leakfree[i])} className="slope" />
          ))}
          <line x1={xa} y1={y(L.mean_replica)} x2={xb} y2={y(L.mean_leakfree)} className="slope-mean" />
          <circle cx={xa} cy={y(L.mean_replica)} r={4} className="dot-end strong-end" />
          <circle cx={xb} cy={y(L.mean_leakfree)} r={4} className="dot-end strong-end" />
          <text x={xb - 8} y={y(L.mean_leakfree) + 18} textAnchor="end" className="strong">
            {pct(L.mean_leakfree)}
          </text>
          <text x={xa + 8} y={y(L.mean_replica) - 8} className="strong">
            {pct(L.mean_replica)}
          </text>
          <text x={xa} y={h - 20} textAnchor="middle" className="strong">
            Their protocol
          </text>
          <text x={xa} y={h - 6} textAnchor="middle">
            test seen in fitting
          </text>
          <text x={xb} y={h - 20} textAnchor="middle" className="strong">
            Leak-free
          </text>
          <text x={xb} y={h - 6} textAnchor="middle">
            test kept out
          </text>
        </svg>
      </div>
    </Plate>
  );
}
