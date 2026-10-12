import { useEffect } from "react";
import { useDemo, type Command } from "../store";

const KEYS: Record<string, Command> = { "1": "IDLE", "2": "HAND_GRASP", "3": "SIXTH_FINGER_FLEX" };

/** Keys 1/2/3 pose the hand directly for checking the animation; Esc returns to the stream. */
export function ManualTestBanner() {
  const manual = useDemo((s) => s.manualMode);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.metaKey || e.ctrlKey || e.altKey) return;
      if (KEYS[e.key]) useDemo.getState().setManualCommand(KEYS[e.key]);
      else if (e.key === "Escape") useDemo.getState().endManual();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  if (!manual) return null;
  return (
    <div className="manual-banner" role="status" data-testid="manual-banner">
      Manual animation test, not decoded EEG. Press Esc to return to the stream.
    </div>
  );
}
