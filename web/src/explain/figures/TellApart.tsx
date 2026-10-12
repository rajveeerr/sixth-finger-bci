import { Plate } from "../../components/Plate";
import { data, pct } from "../data";
import { scale, swarm, useWidth } from "../useWidth";

/** Fig. 8: per-patient accuracy of the demo's kind of decoder on three questions, against chance. */
export function TellApart() {
  const [ref, w] = useWidth<HTMLDivElement>();
  const narrow = w < 460;
  const left = narrow ? 8 : 170;
  const right = w - 18;
  const rowH = narrow ? 104 : 90;
  const top = 10;
  const h = top + rowH * data.tasks.length + 30;
  const x = scale(0.2, 1, left, right);
  const ticks = [0.25, 0.5, 0.75, 1];
  return (
    <Plate
      fig={8}
      title="What it can tell apart"
      hint="Each dot is one patient, 22 in all"
      readout="EEGNet, trained on runs 1 and 2, tested on 3 and 4"
      caption={
        <>
          Telling <strong>rest from imagery</strong> works for most patients. Telling <strong>which</strong>{" "}
          movement was imagined is only a little better than a coin toss, which is why the one-switch view in
          Fig. 3 exists.
        </>
      }
    >
      <div ref={ref}>
        <svg className="fig-svg" width={w} height={h} role="img" aria-label="Accuracy per patient for three tasks">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={top} y2={h - 28} className="grid" />
              <text x={x(t)} y={h - 10} textAnchor="middle">
                {pct(t)}
              </text>
            </g>
          ))}
          {data.tasks.map((task, i) => {
            const y0 = top + rowH * i + (narrow ? 58 : rowH / 2 + 4);
            const dy = swarm(task.values, x, 4.5);
            return (
              <g key={task.key}>
                <text x={narrow ? left : 0} y={narrow ? y0 - 34 : y0 + 4} className="serif strong">
                  {task.label}
                </text>
                <line x1={x(task.chance)} x2={x(task.chance)} y1={y0 - 22} y2={y0 + 22} className="chance" />
                <text x={x(task.chance)} y={y0 + 35} textAnchor="middle" className="note">
                  chance
                </text>
                {task.values.map((v, j) => (
                  <circle key={j} cx={x(v)} cy={y0 + dy[j]} r={4.5} className="dot" />
                ))}
                <line x1={x(task.mean)} x2={x(task.mean)} y1={y0 - 18} y2={y0 + 18} className="mean-mark" />
                <text x={x(task.mean)} y={y0 - 23} textAnchor="middle" className="strong">
                  {pct(task.mean)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </Plate>
  );
}
