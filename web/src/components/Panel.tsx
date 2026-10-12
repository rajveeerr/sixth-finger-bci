import type { ReactNode } from "react";

interface PanelProps {
  step: number;
  title: string;
  note?: ReactNode;
  foot?: ReactNode;
  className?: string;
  testId?: string;
  data?: Record<`data-${string}`, string>;
  children: ReactNode;
}

/** One step of the demo: a plain title ruled to its number, a short note, the live figure. */
export function Panel({ step, title, note, foot, className, testId, data, children }: PanelProps) {
  return (
    <section className={className ? `panel ${className}` : "panel"} aria-label={title} data-testid={testId} {...data}>
      <header className="panel-head">
        <h2 className="panel-title">{title}</h2>
        <span className="panel-rule" aria-hidden="true" />
        <span className="panel-num" aria-hidden="true">
          {String(step).padStart(2, "0")}
        </span>
      </header>
      {note && <p className="panel-note">{note}</p>}
      <div className="panel-body">{children}</div>
      {foot && <footer className="panel-foot">{foot}</footer>}
    </section>
  );
}
