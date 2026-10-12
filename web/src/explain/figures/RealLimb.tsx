import { Plate } from "../../components/Plate";

// Which layers of the demo are real and how a physical limb would use the same commands.
// Keep this in step with the report section on moving from the demo to a real limb.
const LAYERS: { id: string; name: string; demo: string; real: string; sim?: boolean }[] = [
  { id: "L1", name: "Intent", demo: "stroke patients imagining a movement, recorded", real: "the user, live" },
  { id: "L2", name: "EEG", demo: "real recordings, replayed at real speed", real: "EEG cap and amplifier, streaming" },
  { id: "L3", name: "Processing", demo: "filtering and 4 s windows", real: "the same steps, online" },
  { id: "L4", name: "Decoder", demo: "the trained model, running live", real: "the same model, calibrated for the user" },
  { id: "L5", name: "Command", demo: "IDLE, HAND_GRASP, SIXTH_FINGER_FLEX", real: "the same commands" },
  { id: "L6", name: "Controller", demo: "the joints of Fig. 2, animated", real: "motor controller with limits and an emergency stop", sim: true },
  { id: "L7", name: "Limb", demo: "3D hand with a robotic sixth finger", real: "a robotic finger or prosthetic hand", sim: true },
];

/** Fig. 12: the demo's layers, the same as a physical system's up to the command. */
export function RealLimb() {
  return (
    <Plate
      fig={12}
      title="From this demo to a real limb"
      hint="Hatched: simulated here"
      readout="7 layers, 5 real"
      testId="real-limb"
      caption={
        <>
          Everything up to the command is the same as in a brain-controlled limb. A physical system would send the
          same command to a motor controller driving a robotic finger, like the one the patients in the study
          wore. It would also need live acquisition, filters that use only past samples, safety checks against
          false activations and calibration for each user.
        </>
      }
    >
      <ol className="layers">
        <li className="layers-head" aria-hidden="true">
          <span />
          <span>In this demo</span>
          <span>In a physical system</span>
        </li>
        {LAYERS.map((l) => (
          <li key={l.id} data-sim={l.sim ? "" : undefined}>
            <span className="layer-name">
              <b>{l.id}</b> {l.name}
            </span>
            <span>{l.demo}</span>
            <span>{l.real}</span>
          </li>
        ))}
      </ol>
    </Plate>
  );
}
