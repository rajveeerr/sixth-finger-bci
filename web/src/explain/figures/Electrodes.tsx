import { useId } from "react";
import { Plate } from "../../components/Plate";
import { data } from "../data";
import { useWidth } from "../useWidth";

/** Fig. 5: the 40 electrodes seen from above, the seven of Fig. 1 named. */
export function Electrodes() {
  const [ref, w] = useWidth<HTMLDivElement>();
  const h = Math.min(Math.round(w * 0.86), 380);
  const R = h * 0.42;
  const cx = w / 2;
  const cy = h * 0.53;
  const shown = data.electrodes.filter((e) => e.shown);
  const clip = useId();
  return (
    <Plate
      fig={5}
      title="Where the signal is read"
      hint="Seen from above, nose at the top"
      readout="40 electrodes, 7 drawn in Fig. 1"
      caption={
        <>
          The decoder reads all <strong>40 electrodes</strong>. The darker band runs over the motor cortex, where the
          hand is controlled. Each side of it moves the opposite hand.
        </>
      }
    >
      <div ref={ref}>
        <svg className="fig-svg" width={w} height={h} role="img" aria-label="Map of the 40 electrode positions on the head">
          {/* the head, nose and ears */}
          <path
            d={`M${cx - R * 0.13} ${cy - R * 0.99} L${cx} ${cy - R * 1.13} L${cx + R * 0.13} ${cy - R * 0.99}`}
            className="fig-line"
          />
          <ellipse cx={cx - R * 1.03} cy={cy} rx={R * 0.06} ry={R * 0.16} className="fig-line" />
          <ellipse cx={cx + R * 1.03} cy={cy} rx={R * 0.06} ry={R * 0.16} className="fig-line" />
          <circle cx={cx} cy={cy} r={R} className="fig-line fig-head" />
          <text x={cx - R * 1.2} y={cy + 4} textAnchor="end">
            left
          </text>
          <text x={cx + R * 1.2} y={cy + 4}>
            right
          </text>
          {/* the strip over the motor cortex, centred on the C row */}
          <clipPath id={clip}>
            <circle cx={cx} cy={cy} r={R} />
          </clipPath>
          <rect x={cx - R} y={cy - R * 0.3} width={2 * R} height={R * 0.56} className="motor-strip" clipPath={`url(#${clip})`} />
          {data.electrodes.map((e) => (
            <circle
              key={e.name}
              cx={cx + e.x * R}
              cy={cy - e.y * R}
              r={e.shown ? 5.5 : 4}
              className={e.shown ? "el el-shown" : e.motor ? "el el-motor" : "el"}
            />
          ))}
          {shown.map((e) => (
            <text key={e.name} x={cx + e.x * R} y={cy - e.y * R - 10} textAnchor="middle" className="strong">
              {e.name}
            </text>
          ))}
        </svg>
      </div>
    </Plate>
  );
}
