import { useEffect, useRef } from "react";
import { decidedKind, isRight } from "../decision";
import { useDemo } from "../store";
import { eegBuffer } from "../stream/eegBuffer";

const CUE_TEXT: Record<string, string> = { affected_hand: "Imagine: affected hand", sixth_finger: "Imagine: sixth finger" };

/**
 * One trial drawn to scale: what the patient saw (rest, get ready, the cue), the two 4 s
 * windows the decoder reads, each with its decision once made, and a playhead at the
 * newest sample. The playhead moves on animation frames, not React renders.
 */
export function TrialStrip() {
  const { trialDuration: dur, cueOnset: cue, window: w, phase, phaseTruth, trialDecisions, view, classes } = useDemo();
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
  const windows = [
    { key: "rest", start: w.start_s, end: w.end_s },
    { key: "imagery", start: cue + w.start_s, end: cue + w.end_s },
  ];
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
      <div className="strip-windows">
        {windows.map((win) => {
          const p = trialDecisions.find((d) => d.window === win.key);
          const kind = p ? decidedKind(p, view, classes) : "";
          const right = p ? isRight(p, view, classes) : null;
          return (
            <span key={win.key} className="win" data-decided={kind} style={span(win.start, win.end)}>
              <span className="win-label">4 s window</span>
              {p && (
                <span className="win-mark" data-right={String(right)} title={right ? "decided right" : "decided wrong"}>
                  {right ? "✓" : "✗"}
                </span>
              )}
            </span>
          );
        })}
      </div>
    </div>
  );
}
