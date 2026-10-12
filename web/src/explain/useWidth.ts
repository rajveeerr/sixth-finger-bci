import { useEffect, useRef, useState } from "react";

/**
 * The width of an element, kept up to date: figures lay themselves out in real pixels so
 * their type stays the same size on a phone and on a projector.
 */
export function useWidth<T extends HTMLElement>(fallback = 560) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      const w = Math.round(entry.contentRect.width);
      if (w > 0) setWidth(w);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** A linear scale from a domain to a pixel range. */
export function scale(d0: number, d1: number, r0: number, r1: number) {
  return (v: number) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
}

/** Vertical offsets that keep dots of radius r from overlapping along x (a small beeswarm). */
export function swarm(values: number[], x: (v: number) => number, r: number, maxRows = 3): number[] {
  const placed: { x: number; y: number }[] = [];
  const order = values.map((v, i) => ({ v, i })).sort((a, b) => a.v - b.v);
  const out = new Array<number>(values.length).fill(0);
  const slots = [0];
  for (let k = 1; k <= maxRows; k++) slots.push(-k, k);
  for (const { v, i } of order) {
    const px = x(v);
    let chosen = slots[0];
    for (const slot of slots) {
      const y = slot * r * 1.9;
      if (placed.every((p) => Math.hypot(p.x - px, p.y - y) >= r * 1.9)) {
        chosen = slot;
        break;
      }
    }
    const y = chosen * r * 1.9;
    placed.push({ x: px, y });
    out[i] = y;
  }
  return out;
}
