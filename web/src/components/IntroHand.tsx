import { useEffect, useRef, useState } from "react";
import { IsoHand } from "../hands/IsoHand";
import type { Command } from "../store";

/**
 * The hand with its robotic sixth finger, next to the first paragraph, so the reader sees
 * what the page is about before reading it. The finger bends and straightens slowly while
 * the drawing is on screen; under reduced motion it is shown bent and still.
 */
export function IntroHand() {
  const [command, setCommand] = useState<Command>("SIXTH_FINGER_FLEX");
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !ref.current) return;
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
  }, []);

  return (
    <figure className="intro-hand" ref={ref}>
      <div className="intro-hand-art">
        <IsoHand command={command} />
      </div>
      <figcaption>
        <b>The sixth finger</b> is the robotic one on the right, worn on a strap at the wrist. It bends toward the palm
        to help the hand hold things.
      </figcaption>
    </figure>
  );
}
