import type { DemoSource } from "./types";

const LABELS: Record<DemoSource, string> = {
  connecting: "Connecting",
  server: "Model running on the server",
  "loading-browser": "Loading the model",
  browser: "Model running in this browser",
  replay: "Showing stored decisions",
};

export function ModeBadge({ source }: { source: DemoSource }) {
  return (
    <span className="badge" data-testid="mode-badge" data-source={source}>
      {LABELS[source]}
    </span>
  );
}
