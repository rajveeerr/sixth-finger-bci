import { anyImagery, type View } from "./store";
import type { ClassInfo, Prediction } from "./stream/types";

/** What a window was decided as in the chosen view: a class name, or "imagery" in the one switch. */
export function decidedKind(p: Prediction, view: View, classes: ClassInfo[]): string {
  if (view === "three") return p.label;
  return anyImagery(p) ? "imagery" : (classes[0]?.name ?? "rest");
}

/** Whether that decision matches the cue (null for a window with no cue). */
export function isRight(p: Prediction, view: View, classes: ClassInfo[]): boolean | null {
  if (p.truth === null) return null;
  if (view === "three") return p.correct;
  return anyImagery(p) === (p.truth !== classes[0]?.name);
}

export function labelOf(classes: ClassInfo[], name: string | null): string {
  if (name === "imagery") return "Movement imagined";
  return classes.find((c) => c.name === name)?.label ?? name ?? "";
}
