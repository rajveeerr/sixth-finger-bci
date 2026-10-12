import { Plate } from "../../components/Plate";
import { scale, useWidth } from "../useWidth";

// The dataset's trial (Wang et al. 2026): 7 s fixation cross, 1 s grey circle, 6 s cue.
const REST = 7;
const READY = 1;
const IMAGINE = 6;
const TOTAL = REST + READY + IMAGINE;
const CUE = REST + READY;

/** Fig. 7: one trial as the patient saw it, and the two 4 s windows the decoder reads. */
export function Trial() {
  const [ref, w] = useWidth<HTMLDivElement>();
  const pad = 14;
  const x = scale(0, TOTAL, pad, w - pad);
  const screenW = Math.min(76, (x(REST) - x(0)) * 0.7);
  const screenH = screenW * 0.64;
  const barY = screenH + 46;
  const h = barY + 112;
  const screens = [
    { at: REST / 2, label: "Rest", sub: `${REST} s`, glyph: "cross" },
    { at: REST + READY / 2, label: "Ready", sub: `${READY} s`, glyph: "dot" },
    { at: CUE + IMAGINE / 2, label: "Imagine", sub: `${IMAGINE} s`, glyph: "cue" },
  ] as const;
  const windows = [
    { from: 1, to: 5, label: "read as rest" },
    { from: CUE + 1, to: CUE + 5, label: "read as imagery" },
  ];
  return (
    <Plate
      fig={7}
      title="One trial"
      hint="Drawn to scale, 14 s"
      readout="20 trials a run, 4 runs a session"
      caption={
        <>
          The patient watches a cross, then a grey circle, then a cue to imagine moving the affected hand or the
          sixth finger. The decoder reads <strong>4 s</strong> from each half: one window as rest, one as imagery.
        </>
      }
    >
      <div ref={ref}>
        <svg className="fig-svg" width={w} height={h} role="img" aria-label="Timeline of one trial">
          {screens.map((s) => {
            const cx = Math.min(Math.max(x(s.at), pad + screenW / 2), w - pad - screenW / 2);
            const sx = cx - screenW / 2;
            const isReady = s.glyph === "dot";
            const sw = isReady ? screenW * 0.62 : screenW;
            const left = cx - sw / 2;
            return (
              <g key={s.label}>
                {/* a small monitor on a stand: what was on the screen */}
                <rect x={left} y={4} width={sw} height={screenH} rx={3} className="screen" />
                <line x1={cx} x2={cx} y1={4 + screenH} y2={screenH + 12} className="fig-line" />
                <line x1={cx - 9} x2={cx + 9} y1={screenH + 12} y2={screenH + 12} className="fig-line" />
                {s.glyph === "cross" && (
                  <path d={`M${cx - 7} ${4 + screenH / 2}h14M${cx} ${4 + screenH / 2 - 7}v14`} className="glyph" />
                )}
                {s.glyph === "dot" && <circle cx={cx} cy={4 + screenH / 2} r={6} fill="#a9a9a9" />}
                {s.glyph === "cue" && (
                  <>
                    <rect x={sx + 8} y={4 + screenH / 2 - 7} width={screenW / 2 - 12} height={14} fill="var(--hand)" />
                    <rect x={cx + 4} y={4 + screenH / 2 - 7} width={screenW / 2 - 12} height={14} fill="var(--sixth)" />
                  </>
                )}
                {/* the line from the screen down to its stretch of the trial */}
                <line x1={x(s.at)} x2={x(s.at)} y1={screenH + 12} y2={barY - 2} className="fig-line" />
                <circle cx={x(s.at)} cy={barY - 2} r={2} className="dot-end" />
              </g>
            );
          })}
          <rect x={x(0)} y={barY} width={x(REST) - x(0)} height={14} className="seg-rest" />
          <rect x={x(REST)} y={barY} width={x(CUE) - x(REST)} height={14} className="seg-ready" />
          <rect x={x(CUE)} y={barY} width={x(TOTAL) - x(CUE)} height={14} className="seg-imagine" />
          {Array.from({ length: TOTAL + 1 }, (_, s) => (
            <line key={s} x1={x(s)} x2={x(s)} y1={barY + 14} y2={barY + (s % 7 === 0 || s === CUE ? 22 : 18)}
              className="fig-line" />
          ))}
          {screens.map((s) => (
            <text key={s.label} x={x(s.at)} y={barY + 36} textAnchor="middle" className={s.glyph === "dot" ? "" : "strong"}>
              {s.glyph === "dot" ? "" : `${s.label}, ${s.sub}`}
            </text>
          ))}
          <text x={x(CUE)} y={barY + 36} textAnchor="middle">
            cue
          </text>
          {windows.map((win) => (
            <g key={win.label}>
              <path
                d={`M${x(win.from)} ${barY + 50}v10H${x(win.to)}v-10`}
                className="fig-line bracket"
              />
              <text x={(x(win.from) + x(win.to)) / 2} y={barY + 78} textAnchor="middle" className="strong">
                4 s window
              </text>
              <text x={(x(win.from) + x(win.to)) / 2} y={barY + 94} textAnchor="middle">
                {win.label}
              </text>
            </g>
          ))}
        </svg>
      </div>
    </Plate>
  );
}
