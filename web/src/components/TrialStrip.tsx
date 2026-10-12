import { useEffect, useRef } from "react";
import { useDemo } from "../store";
import { eegBuffer } from "../stream/eegBuffer";

/**
 * One trial as a timer: rest, get ready, imagine, drawn to scale, with a marker at the
 * newest sample. The marker moves on animation frames, not React renders.
 */
export function TrialStrip() {
  const { trialDuration: dur, cueOnset: cue, phase, phaseTruth } = useDemo();
  const head = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!dur) return;
    let raf = 0;
    let shown = -1;
    const frame = () => {
      raf = requestAnimationFrame(frame);
      const t = Math.min(eegBuffer.trialT, dur);
      if (Math.abs(t - shown) < 0.01 || !head.current) return;
      shown = t;
      head.current.style.left = `${(t / dur) * 100}%`;
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [dur]);

  if (!dur) return <div className="timer" data-testid="phase" data-phase="" aria-hidden="true" />;
  const pct = (s: number) => (Math.max(0, Math.min(s, dur)) / dur) * 100;
  const prep = Math.max(cue - 1, 0);
  const cueKnown = phase === "imagery" && phaseTruth ? phaseTruth : "";
  const segs = [
    { key: "rest", from: 0, to: prep, text: "rest" },
    { key: "prepare", from: prep, to: cue, text: "" },
    { key: "imagery", from: cue, to: dur, text: "imagine" },
  ];
  return (
    <div className="timer" data-testid="phase" data-phase={phase ?? ""} aria-hidden="true">
      <div className="timer-bar">
        {segs.map((s) => (
          <span
            key={s.key}
            className="timer-seg"
            data-seg={s.key}
            data-on={phase === s.key ? "" : undefined}
            data-cue={s.key === "imagery" ? cueKnown : undefined}
            style={{ left: `${pct(s.from)}%`, width: `${pct(s.to) - pct(s.from)}%` }}
          />
        ))}
        <span className="timer-head" ref={head} />
      </div>
      <div className="timer-labels">
        {segs.map((s) => (
          <span key={s.key} style={{ left: `${pct(s.from)}%` }} data-on={phase === s.key ? "" : undefined}>
            {s.text}
          </span>
        ))}
        <span className="timer-end">{Math.round(dur)} s</span>
      </div>
    </div>
  );
}
