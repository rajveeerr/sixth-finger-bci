// Explains which layers of the demo are real and how a physical limb would use the same commands.
// Text source: _workspace/research/from-demo-to-real-limb.md (keep the two in sync).

const LAYERS: { id: string; name: string; demo: string; real: string; kind: "real" | "sim" }[] = [
  { id: "L1", name: "Intent", demo: "stroke patients imagining a movement (recorded)", real: "the user, live", kind: "real" },
  { id: "L2", name: "EEG", demo: "real recordings, replayed at real speed", real: "EEG cap and amplifier streaming live", kind: "real" },
  { id: "L3", name: "Processing", demo: "filtering and 4 s windows", real: "the same steps, run online", kind: "real" },
  { id: "L4", name: "Decoder", demo: "the trained model, running live", real: "the same model, calibrated for the user", kind: "real" },
  { id: "L5", name: "Command", demo: "IDLE, HAND_GRASP, SIXTH_FINGER_FLEX", real: "the same commands", kind: "real" },
  { id: "L6", name: "Controller", demo: "animation of the joints", real: "motor controller with limits and an emergency stop", kind: "sim" },
  { id: "L7", name: "Limb", demo: "3D hand with a robotic sixth finger", real: "a robotic finger or prosthetic hand", kind: "sim" },
];

export function RealLimbPanel() {
  return (
    <details className="panel real-limb" data-testid="real-limb">
      <summary>From this demo to a real limb</summary>
      <p>
        This demo moves a 3D hand, not a mechanical one, but everything up to the command is the
        same as in a brain-controlled limb: real EEG, the real trained decoder, and a standard
        command. A physical system would send the same command to a motor controller driving a
        robotic finger, like the one worn by the patients in the original study.
      </p>
      <table>
        <thead>
          <tr><th>Layer</th><th>In this demo</th><th>In a physical system</th></tr>
        </thead>
        <tbody>
          {LAYERS.map((l) => (
            <tr key={l.id} data-kind={l.kind}>
              <td>{l.id} {l.name}</td>
              <td>{l.demo}</td>
              <td>{l.real}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">
        Moving a real limb also needs live EEG acquisition, filters that use only past samples,
        safety checks against false activations, and per-user calibration, which is what this
        project measures.
      </p>
    </details>
  );
}
