import { Plate } from "../../components/Plate";

// Which layers of the demo are real and how a physical limb would use the same commands.
// Keep this in step with the report section on moving from the demo to a real limb.
const LAYERS: { id: string; name: string; demo: string; real: string; sim?: boolean }[] = [
  { id: "1", name: "Intent", demo: "a stroke patient imagining a movement, recorded", real: "the user, live" },
  { id: "2", name: "Brain signal", demo: "real EEG recordings, played at real speed", real: "an EEG cap and amplifier, live" },
  { id: "3", name: "Processing", demo: "cut into 4 s pieces", real: "the same, as the signal arrives" },
  { id: "4", name: "Model", demo: "the trained model, running now", real: "the same model, set up for each user" },
  { id: "5", name: "Command", demo: "IDLE, HAND_GRASP, SIXTH_FINGER_FLEX", real: "the same commands" },
  { id: "6", name: "Motor", demo: "moves the drawing in step 2", real: "a motor controller with limits and an emergency stop", sim: true },
  { id: "7", name: "Finger", demo: "the drawn hand and sixth finger", real: "a robotic finger worn on the hand", sim: true },
];

/** Fig. 8: the demo's seven steps, the same as a real system's up to the command. */
export function RealLimb() {
  return (
    <Plate
      title="Seven steps, five of them real"
      hint="Hatched: drawn, not built"
      readout="steps 1 to 5 are real"
      testId="real-limb"
      caption={
        <>
          A real system would send the same command to a motor driving a robotic finger. It would also need the
          EEG live, safety checks against false starts, and a short setup for each user.
        </>
      }
    >
      <ol className="layers">
        <li className="layers-head" aria-hidden="true">
          <span />
          <span>In this demo</span>
          <span>In a real system</span>
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
