import type { ReactNode } from "react";

interface PlateProps {
  title: string;
  hint?: ReactNode;
  readout?: ReactNode;
  caption?: ReactNode;
  className?: string;
  label?: string;
  testId?: string;
  /** data-* attributes for the figure element (state that tests and styles read). */
  data?: Record<`data-${string}`, string>;
  children: ReactNode;
}

/**
 * A figure on the page, unframed: the drawing, then one small note with its name, how to read
 * it and what it shows now, then the caption, when there is one.
 */
export function Plate({ title, hint, readout, caption, className, label, testId, data, children }: PlateProps) {
  return (
    <figure
      className={className ? `plate ${className}` : "plate"}
      aria-label={label ?? title}
      data-testid={testId}
      {...data}
    >
      <div className="plate-art">{children}</div>
      <figcaption className="plate-side">
        <b className="plate-title">{title}</b>
        {hint && <span className="plate-hint">{hint}</span>}
        {readout && <span className="plate-readout">{readout}</span>}
      </figcaption>
      {caption && <p className="plate-caption">{caption}</p>}
    </figure>
  );
}
