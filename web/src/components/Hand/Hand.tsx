import type { Command } from "../../store";

export function Hand({ command }: { command: Command }) {
  return (
    <div className="placeholder" data-testid="hand" data-command={command}>
      3D hand ({command})
    </div>
  );
}
