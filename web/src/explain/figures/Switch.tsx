import { Plate } from "../../components/Plate";
import { data, pct } from "../data";

/** Fig. 11: the one switch replayed as if live, over 22 patients. */
export function Switch() {
  const s = data.switch;
  const readings = [
    {
      value: pct(s.detection),
      unit: "",
      text: "of imagery periods switched the finger on",
      note: `${pct(s.detection_ci[0])} to ${pct(s.detection_ci[1])}`,
    },
    { value: s.false_per_minute.toFixed(1), unit: "a min", text: "false switches while resting", note: "" },
    { value: s.latency_s.toFixed(1), unit: "s", text: "from the cue to the switch", note: "" },
  ];
  return (
    <Plate
      fig={11}
      title="One switch, replayed as if live"
      hint="EEGNet, every 0.5 s, smoothed as in the demo"
      readout="mean of 22 patients"
      caption={
        <>
          Played back continuously, with the same smoothing and hold the demo uses, any imagined movement works
          as one switch: <strong>about two thirds</strong> of the time, with roughly one false start a minute.
        </>
      }
    >
      <dl className="readings">
        {readings.map((r) => (
          <div key={r.text} className="reading">
            <dt>
              {r.value}
              {r.unit && <small> {r.unit}</small>}
            </dt>
            <dd>
              {r.text}
              {r.note && <span className="muted"> ({r.note})</span>}
            </dd>
          </div>
        ))}
      </dl>
    </Plate>
  );
}
