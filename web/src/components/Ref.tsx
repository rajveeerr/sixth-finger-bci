import { useEffect, useId, useRef, useState, type ReactNode } from "react";

const EDGE = 12;

/**
 * A word with a small card that opens on hover or keyboard focus: a reference (with its
 * link) or a plain-words definition. On a touch screen the first tap opens the card and,
 * for a reference, a second tap follows the link.
 */
export function Ref({ href, card, children }: { href?: string; card: ReactNode; children: ReactNode }) {
  const id = useId();
  const box = useRef<HTMLSpanElement>(null);
  const touch = useRef(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const close = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

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
  const onPointerDown = (e: React.PointerEvent) => {
    touch.current = e.pointerType !== "mouse";
  };
  const onClick = (e: React.MouseEvent) => {
    if (!touch.current || open) return;
    e.preventDefault();
    place();
    setOpen(true);
  };
  return (
    <span
      className="ref"
      ref={box}
      data-open={open ? "" : undefined}
      onPointerEnter={place}
      onFocus={place}
      onPointerDown={onPointerDown}
      onClick={onClick}
    >
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
