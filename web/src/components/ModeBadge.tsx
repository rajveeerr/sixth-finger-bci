import type { DemoSource } from "./types";

const LABELS: Record<DemoSource, string> = {
  connecting: "Connecting to the server",
  server: "Decoding on the server",
  "loading-browser": "Loading the model in this browser",
  browser: "Decoding in this browser",
  replay: "Replaying stored decisions",
};

export function ModeBadge({ source }: { source: DemoSource }) {
  return (
    <span className="badge" data-testid="mode-badge" data-source={source}>
      {LABELS[source]}
    </span>
  );
}
