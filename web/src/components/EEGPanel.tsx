export function EEGPanel({ channels }: { channels: string[] }) {
  return (
    <section className="panel placeholder" data-testid="eeg-panel">
      EEG: {channels.join(", ") || "waiting for stream"}
    </section>
  );
}
