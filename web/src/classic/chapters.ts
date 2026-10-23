// The chapter-by-chapter page (/classic): its chapters in order. Each takes its number and title
// from here, so a line that says "chapter 8" stays right when a chapter is added.

import { READ_TITLE } from "../explain/siteDocs";

export const TITLE = "Sixth-Finger BCI, chapter by chapter";
export const DESCRIPTION =
  "A stroke patient imagines moving a robotic sixth finger, and a model reading their EEG moves it: the idea, the recordings, the model, a live demo and what we found, chapter by chapter";

const CHAPTERS = [
  { id: "idea", title: "The idea" },
  { id: "recordings", title: "The recordings" },
  { id: "brain", title: "What changes in the brain" },
  { id: "research", title: "What we set out to find" },
  { id: "data", title: "First, we checked the data" },
  { id: "model", title: "The model" },
  { id: "demo", title: "Watch it work" },
  { id: "found", title: "What we found" },
  { id: "numbers", title: "How good it is, in numbers" },
  { id: "new", title: "What this project adds" },
  { id: "use", title: "What a BCI is, and how a patient would use it" },
  { id: "read", title: READ_TITLE },
  { id: "more", title: "Read more" },
] as const;

export type ChapterId = (typeof CHAPTERS)[number]["id"];

export const chapter = (id: ChapterId) => {
  const i = CHAPTERS.findIndex((c) => c.id === id);
  return { ...CHAPTERS[i], n: i + 1 };
};

/** "chapter 8", for a line that points at another chapter. */
export const chapterName = (id: ChapterId) => `chapter ${chapter(id).n}`;
