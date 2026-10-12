import type { ReactNode } from "react";

interface PlateProps {
  fig: number;
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
 * A figure plate: the figure number at top left, its title at top right, how to use it at
 * bottom left and what it reads now at bottom right, with the caption under the frame.
 */
export function Plate({ fig, title, hint, readout, caption, className, label, testId, data, children }: PlateProps) {
  return (
    <figure
      className={className ? `plate ${className}` : "plate"}
      aria-label={label ?? title}
      data-testid={testId}
      {...data}
    >
      <div className="plate-frame">
        <div className="plate-head">
          <span className="plate-fig">FIG_{String(fig).padStart(3, "0")}</span>
          <span className="plate-title">{title}</span>
        </div>
        <div className="plate-body">{children}</div>
        {(hint || readout) && (
          <div className="plate-foot">
            <span className="plate-hint">{hint}</span>
            <span className="plate-readout">{readout}</span>
          </div>
        )}
      </div>
      {caption && <figcaption className="plate-caption">{caption}</figcaption>}
    </figure>
  );
}
