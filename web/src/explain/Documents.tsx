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

/** The paper, the slides and the report, at the end of the page and linked from its opening. */
export function Documents() {
  return (
    <section className="read" id="read" aria-labelledby="read-title">
      <h2 id="read-title">{READ_TITLE}</h2>
      <ul className="docs">
        {FILES.map((f) => (
          <li key={f.file}>
            <Sheet label={SHORT[f.format] ?? f.format} />
            <div>
              <p className="doc-head">
                <a href={f.href} download={f.format === "PDF" ? undefined : f.file}>
                  <b>{f.name}</b>, {f.format}, {fileSize(f.bytes)}
                </a>
                {f.tag && <span className="doc-tag">{f.tag}</span>}
              </p>
              <p className="doc-text">{f.text}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
