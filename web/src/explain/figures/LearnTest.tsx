// What a model learned from and what it was tested on, run by run, drawn like LeakDiagram:
// squares are trials, twenty to a run in the order recorded; orange ones are the trials it was
// tested on, and the bracket marks what it learned from.

export type RunUse = "learn" | "pick" | "test" | "replay";

export interface SplitRow {
  /** Whose recordings, and which session. */
  title: string;
  note?: string;
  /** Many patients' recordings, drawn as a stack. */
  many?: boolean;
  /** Runs 1 to 4: learned from whole, a few trials picked from them, tested on, or replayed unbroken. */
  runs: [RunUse, RunUse, RunUse, RunUse];
  /** How many trials the "pick" runs give, together; an example draw, the real ones were random. */
  picked?: number;
  /** Under the bracket. */
  learns?: string;
  /** Only one of the models compared learned from these: the bracket is dashed. */
  sometimes?: boolean;
  /** Under the orange runs. */
  tested?: string;
}

export interface Split {
  label: string;
  rows: SplitRow[];
  note?: string;
}

const PER_RUN = 20;
// Fixed offsets so the example picks look scattered, as a random draw would, yet never move.
const JITTER = [-1.6, 1.2, -0.4, 1.7, -1.1, 0.6, -1.8, 0.9, -0.2, 1.4];

/** Indices of `n` trials spread over `total`, as one example of a random draw. */
function picks(n: number, total: number): Set<number> {
  const step = total / n;
  return new Set(
    Array.from({ length: n }, (_, i) =>
      Math.min(total - 1, Math.max(0, Math.round((i + 0.5) * step + JITTER[i % JITTER.length]))),
    ),
  );
}

/** The first and last run (1-based) a test matches, for a grid column span. */
function span(runs: RunUse[], test: (u: RunUse) => boolean): string | null {
  const idx = runs.flatMap((u, i) => (test(u) ? [i] : []));
  return idx.length ? `${idx[0] + 1} / ${idx[idx.length - 1] + 2}` : null;
}

const learned = (u: RunUse) => u === "learn" || u === "pick";
const tested = (u: RunUse) => u === "test" || u === "replay";

function Row({ row, head }: { row: SplitRow; head: boolean }) {
  const nPick = row.runs.filter((u) => u === "pick").length * PER_RUN;
  const chosen = row.picked ? picks(row.picked, nPick) : new Set<number>();
  // A trial's place among the picked runs' trials, counted across them in order.
  const pickedBefore = (r: number) => row.runs.slice(0, r).filter((u) => u === "pick").length * PER_RUN;
  const learnSpan = span(row.runs, learned);
  const testSpan = span(row.runs, tested);
  return (
    <div className="split-row" data-many={row.many ? "" : undefined}>
      <p className="split-title">
        <b>{row.title}</b>
        {row.note && <span>{row.note}</span>}
      </p>
      {head && (
        <div className="split-head" aria-hidden="true">
          {row.runs.map((_, r) => (
            <span key={r}>Run {r + 1}</span>
          ))}
        </div>
      )}
      <div className="split-runs" aria-hidden="true">
        {row.runs.map((use, r) => (
          <span key={r} className="split-run" data-use={use}>
            {Array.from({ length: PER_RUN }, (_, t) => {
              const on = use === "pick" && chosen.has(pickedBefore(r) + t);
              return <i key={t} data-on={on ? "" : undefined} />;
            })}
          </span>
        ))}
      </div>
      <div className="split-marks">
        {learnSpan && row.learns && (
          <>
            <i
              className="split-bracket"
              data-sometimes={row.sometimes ? "" : undefined}
              style={{ gridColumn: learnSpan }}
              aria-hidden="true"
            />
            <span className="split-learns" style={{ gridColumn: learnSpan }}>
              {row.learns}
            </span>
          </>
        )}
        {testSpan && row.tested && (
          <span className="split-tested" style={{ gridColumn: testSpan }}>
            {row.tested}
          </span>
        )}
      </div>
    </div>
  );
}

/** What one answer's model learned from and what it was tested on. */
export function LearnTest({ split }: { split: Split }) {
  return (
    <figure className="split" aria-label={split.label}>
      {split.rows.map((row, i) => (
        <Row key={row.title} row={row} head={i === 0} />
      ))}
      {split.note && <figcaption>{split.note}</figcaption>}
    </figure>
  );
}
