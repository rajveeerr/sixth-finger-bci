import { useEffect } from "react";

// The page is drawn after the browser looks for the address's #target, so go to it once it
// exists; and a link to something inside a closed fold opens the fold first.
export function useLandOnLink() {
  useEffect(() => {
    const land = (always: boolean) => {
      const id = decodeURIComponent(window.location.hash.slice(1));
      const target = id ? document.getElementById(id) : null;
      if (!target) return;
      const fold = target.closest("details");
      if (fold && !fold.open) fold.open = true;
      else if (!always) return;
      target.scrollIntoView();
    };
    land(true);
    const onHash = () => land(false);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
}
