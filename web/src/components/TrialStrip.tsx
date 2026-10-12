import { useEffect, useRef } from "react";
import { useDemo } from "../store";
import { eegBuffer } from "../stream/eegBuffer";

const CUE_TEXT: Record<string, string> = { affected_hand: "Imagine: affected hand", sixth_finger: "Imagine: sixth finger" };

/**
 * One trial drawn to scale: what the patient saw (rest, get ready, the cue), with a tick
 * every second and a playhead at the newest sample. The playhead moves on animation
 * frames, not React renders. The 4 s pieces the model reads are marked on the chart.
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

  if (!dur) return <div className="strip" data-testid="phase" data-phase="" aria-hidden="true" />;
  const pct = (s: number) => `${(Math.max(0, Math.min(s, dur)) / dur) * 100}%`;
  const span = (a: number, b: number) => ({ left: pct(a), width: `${((Math.min(b, dur) - a) / dur) * 100}%` });
  const prep = Math.max(cue - 1, 0);
  const cueKnown = phase === "imagery" && phaseTruth ? phaseTruth : "";
  const seconds = Array.from({ length: Math.floor(dur) + 1 }, (_, i) => i);
  return (
    <div className="strip" data-testid="phase" data-phase={phase ?? ""}>
      <div className="strip-phases">
        <span className={phase === "rest" ? "on" : ""} style={span(0, prep)}>
          <i className="cross" aria-hidden="true" />
          Rest
        </span>
        <span className={phase === "prepare" ? "on" : ""} style={span(prep, cue)} title="Get ready">
          <i className="ready-dot" aria-label="Get ready" />
        </span>
        <span className={phase === "imagery" ? "on" : ""} data-cue={cueKnown} style={span(cue, dur)}>
          {CUE_TEXT[cueKnown] ?? "Imagine"}
        </span>
      </div>
      <div className="strip-bar">
        <span className="seg" data-seg="rest" style={span(0, prep)} />
        <span className="seg" data-seg="prepare" style={span(prep, cue)} />
        <span className="seg" data-seg="imagery" data-cue={cueKnown} style={span(cue, dur)} />
        {seconds.map((s) => (
          <i key={s} className="tick" data-major={s % 5 === 0 ? "" : undefined} style={{ left: pct(s) }} />
        ))}
        <span className="playhead" ref={head} />
      </div>
    </div>
  );
}
