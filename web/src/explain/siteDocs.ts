// The paper, the slides and the report as the site serves them from public/docs. Which files
// are there, and their sizes, come from documents.json, written by scripts/copy_site_docs.py
// when it copies them; never edit it by hand.
import raw from "./documents.json";

export interface SiteFile {
  doc: string;
  file: string;
  format: string;
  bytes: number;
}

interface About {
  name: string;
  text: string;
  tag?: string;
}

const ABOUT: Record<string, About> = {
  paper: {
    name: "Paper",
    tag: "Preprint draft",
    text: "Teaching a Brain-Computer Interface a New Finger: Calibrating Sixth-Finger Motor Imagery Decoders in Stroke Patients.",
  },
  slides: {
    name: "Slides",
    text: "The talk for the final evaluation, in the order of the questions on this page, with backup slides.",
  },
  report: { name: "Report", text: "The B.Tech minor project report, in the university's format." },
};

export const FILES = (raw as SiteFile[]).map((f) => {
  const about = ABOUT[f.doc];
  if (!about) throw new Error(`No words for the document ${f.doc}`);
  return { ...f, ...about, href: `${import.meta.env.BASE_URL}docs/${f.file}` };
});

/** A file's size the way a download link gives it: "0.3 MB", or "40 KB" when smaller. */
export function fileSize(bytes: number): string {
  return bytes < 100_000 ? `${Math.max(1, Math.round(bytes / 1000))} KB` : `${(bytes / 1_000_000).toFixed(1)} MB`;
}

/** "the paper", "the paper and the slides", "the paper, the slides and the report". */
export function inWords(docs: string[]): string {
  const names = [...new Set(docs)].map((d) => `the ${ABOUT[d].name.toLowerCase()}`);
  return names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export const READ_TITLE = `Read ${inWords(FILES.map((f) => f.doc))}`;
