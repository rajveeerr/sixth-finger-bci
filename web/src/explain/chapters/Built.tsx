import { Chapter } from "../../components/Chapter";
import { RealPipeline } from "../figures/RealPipeline";

export function Built() {
  return (
    <Chapter
      q="built"
      answer={
        <>
          We built the model, the server that runs it and this page; a real system still needs a live headset, a small
          bridge program and the finger itself.
        </>
      }
    >
      <RealPipeline />
      <p className="q-next">
        <b>What comes next</b> Those parts, with safety limits on the motor and an emergency stop, and then a test with
        patients wearing it. The demo&apos;s finger is drawn, not built.
      </p>
    </Chapter>
  );
}
