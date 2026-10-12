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

/** One step of the demo: a numbered plain title, a short note, the live figure. */
export function Panel({ step, title, note, foot, className, testId, data, children }: PanelProps) {
  return (
    <section className={className ? `panel ${className}` : "panel"} aria-label={title} data-testid={testId} {...data}>
      <header className="panel-head">
        <span className="panel-step" aria-hidden="true">
          {step}
        </span>
        <h2 className="panel-title">{title}</h2>
        {note && <span className="panel-note">{note}</span>}
      </header>
      <div className="panel-body">{children}</div>
      {foot && <footer className="panel-foot">{foot}</footer>}
    </section>
  );
}
