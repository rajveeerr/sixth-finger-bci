import type { ReactNode } from "react";
import { Gauge } from "../explain/figures/Gauge";
import { question } from "../explain/questions";

interface Dial {
  value: number;
  other?: number;
  guess?: number;
  /** What the two needles read, in a few words each. */
  reading: ReactNode;
}

/**
 * A chapter is one question: its title is the question, then the answer in one sentence (beside
 * its dial, when it has a score), then the figure that shows it and anything folded under it.
 */
export function Chapter({
  q,
  answer,
  dial,
  children,
}: {
  q: string;
  answer: ReactNode;
  dial?: Dial;
  children?: ReactNode;
}) {
  const { id, n, ask } = question(q);
  return (
    <section className="q" id={id} aria-labelledby={`${id}-title`}>
      <header className="q-head">
        <span className="q-num" aria-hidden="true">
          {n}
        </span>
        <h2 id={`${id}-title`}>{ask}</h2>
      </header>
      <div className="q-answer" data-dial={dial ? "" : undefined}>
        <p className="q-say">{answer}</p>
        {dial && (
          <div className="q-dial">
            <Gauge value={dial.value} other={dial.other} guess={dial.guess} />
            <p className="q-reading">{dial.reading}</p>
          </div>
        )}
      </div>
      {children}
    </section>
  );
}

/** What the reader opens for the evidence: a label, then in a few words what is inside. */
export function More({ label = "How we know", what, children }: { label?: string; what: string; children: ReactNode }) {
  return (
    <details className="more">
      <summary>
        <span className="more-label">{label}</span>
        <span className="more-what">{what}</span>
      </summary>
      <div className="more-body">{children}</div>
    </details>
  );
}

/** A question the examiner may ask next, inside a fold: its short answer, then what shows it. */
export function FollowUp({ ask, children }: { ask: string; children: ReactNode }) {
  return (
    <section className="follow">
      <h3>{ask}</h3>
      {children}
    </section>
  );
}
