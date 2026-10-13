import { useId, useRef, type ReactNode } from "react";

const EDGE = 12;

/**
 * A word with a small card that opens on hover or keyboard focus: a reference (with its
 * link) or a plain-words definition. On touch screens the card opens on tap.
 */
export function Ref({ href, card, children }: { href?: string; card: ReactNode; children: ReactNode }) {
  const id = useId();
  const box = useRef<HTMLSpanElement>(null);
  // Slide an open card left if it would run past the window's right edge.
  const place = () => {
    const el = box.current?.querySelector<HTMLElement>(".ref-card");
    if (!el) return;
    el.style.setProperty("--ref-shift", "0px");
    el.style.display = "block";
    const r = el.getBoundingClientRect();
    el.style.display = "";
    const over = r.right - (document.documentElement.clientWidth - EDGE);
    el.style.setProperty("--ref-shift", `${-Math.max(0, Math.min(over, r.left - EDGE))}px`);
  };
  return (
    <span className="ref" ref={box} onPointerEnter={place} onFocus={place}>
      {href ? (
        <a href={href} aria-describedby={id}>
          {children}
        </a>
      ) : (
        <span className="ref-term" tabIndex={0} aria-describedby={id}>
          {children}
        </span>
      )}
      <span className="ref-card" role="tooltip" id={id}>
        {card}
      </span>
    </span>
  );
}
