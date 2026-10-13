// The demo's keys are global so a presenter can use them without clicking first, but the
// page around the demo also uses Space (scroll, open a row) and the arrows (tabs).

const OWN_KEYS = "input, textarea, select, summary, a, [role=tab], [role=radio], [contenteditable]";

/** Whether a key press may go to the demo: no modifier, and not on something it already drives. */
export function keyForDemo(e: KeyboardEvent): boolean {
  if (e.metaKey || e.ctrlKey || e.altKey) return false;
  return !(e.target instanceof Element && e.target.closest(OWN_KEYS));
}

/** Whether the demo is on screen, so Space and the arrows are meant for it rather than the page. */
export function demoInView(): boolean {
  const demo = document.getElementById("demo");
  if (!demo) return true;
  const r = demo.getBoundingClientRect();
  return r.bottom > 0 && r.top < window.innerHeight;
}
