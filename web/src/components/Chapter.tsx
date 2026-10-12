import type { ReactNode } from "react";

/** A chapter: its title ruled to its number, a short plain lede, then its figures. */
export function Chapter({ id, n, title, lede, children }: { id: string; n: number; title: string; lede?: ReactNode; children?: ReactNode }) {
  return (
    <section className="chapter" id={id} aria-labelledby={`${id}-title`}>
      <header className="chapter-head">
        <h2 id={`${id}-title`}>{title}</h2>
        <span className="chapter-rule" aria-hidden="true" />
        <span className="chapter-num" aria-hidden="true">
          {String(n).padStart(2, "0")}
        </span>
      </header>
      {lede && <div className="chapter-lede">{lede}</div>}
      {children}
    </section>
  );
}
