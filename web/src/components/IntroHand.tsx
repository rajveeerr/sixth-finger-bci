import { useEffect, useRef, useState } from "react";
import { IsoHand } from "../hands/IsoHand";
import type { Command } from "../store";

/**
 * The hand with its robotic sixth finger under the headline, so the reader sees what the
 * page is about before reading it. Holding the button bends the finger, the way imagining
 * the movement would; until the reader tries it, the finger bends and straightens slowly
 * while in view (shown bent and still under reduced motion).
 */
export function IntroHand() {
  const [command, setCommand] = useState<Command>("SIXTH_FINGER_FLEX");
  const [held, setHeld] = useState(false);
  const [tried, setTried] = useState(false);
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    if (tried || window.matchMedia("(prefers-reduced-motion: reduce)").matches || !ref.current) return;
    let timer = 0;
    const tick = () => setCommand((c) => (c === "SIXTH_FINGER_FLEX" ? "IDLE" : "SIXTH_FINGER_FLEX"));
    const observer = new IntersectionObserver(([entry]) => {
      window.clearInterval(timer);
      if (entry.isIntersecting) timer = window.setInterval(tick, 1800);
    });
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      window.clearInterval(timer);
    };
  }, [tried]);

  const hold = (on: boolean) => {
    setTried(true);
    setHeld(on);
    setCommand(on ? "SIXTH_FINGER_FLEX" : "IDLE");
  };

  return (
    <figure className="intro-hand" ref={ref}>
      <div className="intro-hand-art">
        <IsoHand command={command} />
      </div>
      <button
        type="button"
        className="imagine"
        aria-pressed={held}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          hold(true);
        }}
        onPointerUp={() => hold(false)}
        onPointerCancel={() => hold(false)}
        onKeyDown={(e) => {
          if ((e.key === " " || e.key === "Enter") && !e.repeat) {
            e.preventDefault();
            hold(true);
          }
        }}
        onKeyUp={(e) => {
          if (e.key === " " || e.key === "Enter") hold(false);
        }}
        onBlur={() => held && hold(false)}
        onContextMenu={(e) => e.preventDefault()}
      >
        {held ? "Imagining: the finger bends" : "Press and hold to imagine the movement"}
      </button>
      <figcaption>
        For a hand left weak by a stroke: worn on a strap at the wrist, the robotic sixth finger bends toward the palm
        to help the hand hold things, and moves when the wearer imagines moving it.
      </figcaption>
    </figure>
  );
}
