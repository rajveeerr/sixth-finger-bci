import type { DemoSource } from "./types";

const LABELS: Record<DemoSource, string> = {
  connecting: "connecting",
  server: "server",
  "loading-browser": "loading in-browser model",
  browser: "in-browser",
  replay: "replay",
};

export function ModeBadge({ source }: { source: DemoSource }) {
  return (
    <span className="badge" data-testid="mode-badge" data-source={source}>
      {LABELS[source]}
    </span>
  );
}
