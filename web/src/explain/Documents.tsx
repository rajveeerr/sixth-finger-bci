import { FILES, fileSize, READ_TITLE } from "./siteDocs";

/** A sheet with its corner folded and its format on it, so a download reads as one at a glance. */
function Sheet({ label }: { label: string }) {
  return (
    <svg className="doc-sheet" viewBox="0 0 30 38" aria-hidden="true">
      <path d="M1.5 1.5h19l8 8v27h-27z" />
      <path d="M20.5 1.5v8h8" />
      <text x="15" y="29">
        {label}
      </text>
    </svg>
  );
}

const SHORT: Record<string, string> = { PDF: "PDF", PowerPoint: "PPT" };

/** Only the PDFs open in the browser; anything else downloads under its own name. */
const downloadAs = (f: (typeof FILES)[number]) => (f.format === "PDF" ? undefined : f.file);

/**
 * The paper, the slides and the report, one row each with its format, size and a line on what it
 * is; a page may say that line its own way.
 */
export function DocList({ text = {} }: { text?: Record<string, string> }) {
  return (
    <ul className="docs">
      {FILES.map((f) => (
        <li key={f.file}>
          <Sheet label={SHORT[f.format] ?? f.format} />
          <div>
            <p className="doc-head">
              <a href={f.href} download={downloadAs(f)}>
                <b>{f.name}</b>, {f.format}, {fileSize(f.bytes)}
              </a>
              {f.tag && <span className="doc-tag">{f.tag}</span>}
            </p>
            <p className="doc-text">{text[f.doc] ?? f.text}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

/** The same files as one quiet line of links, for the demo alone on its screen. */
export function DocLinks() {
  return (
    <ul className="doc-links" aria-label={READ_TITLE}>
      {FILES.map((f) => (
        <li key={f.file}>
          <a href={f.href} download={downloadAs(f)}>
            <b>{f.name}</b>, {f.format}, {fileSize(f.bytes)}
          </a>
        </li>
      ))}
    </ul>
  );
}

/** The paper, the slides and the report, at the end of the page and linked from its opening. */
export function Documents() {
  return (
    <section className="read" id="read" aria-labelledby="read-title">
      <h2 id="read-title">{READ_TITLE}</h2>
      <DocList />
    </section>
  );
}
