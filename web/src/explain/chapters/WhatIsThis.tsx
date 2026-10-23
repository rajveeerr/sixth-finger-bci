import { Chapter, FollowUp, More } from "../../components/Chapter";
import { BrainRhythm } from "../figures/BrainRhythm";
import { SignalChain } from "../figures/SignalChain";
import { EegTerm, ModelTerm, TherapyTerm } from "../refs";

export function WhatIsThis() {
  return (
    <Chapter
      q="what"
      answer={
        <>
          A brain-computer interface: an <EegTerm /> cap reads the brain, and a <ModelTerm>model</ModelTerm> moves the
          robotic sixth finger when the wearer imagines moving it.
        </>
      }
    >
      <SignalChain />
      <More label="How it works" what="what a BCI is, what else it can do, and what the model looks for">
        <div className="facts">
          <dl>
            <div>
              <dt>What a BCI is</dt>
              <dd>
                A brain-computer interface turns brain signals into commands for a machine, without the body moving.
                Sensors on the scalp, as here, are safe and cheap but blurry; sensors inside the skull are sharper but
                need surgery.
              </dd>
            </div>
            <div>
              <dt>What else it can do</dt>
              <dd>
                Help the brain recover: the patient imagines a movement again and again, and each time the BCI picks it
                up, a robot answers with that movement; 14 patients in this study had{" "}
                <TherapyTerm>two weeks of it</TherapyTerm>. Also typing for people who cannot move or speak, steering a
                wheelchair, moving a prosthetic hand.
              </dd>
            </div>
          </dl>
        </div>
        <FollowUp ask="What does the model look for?">
          <p>
            A rhythm over the part of the brain that moves the hands. When a person imagines moving, it gets smaller.
          </p>
          <BrainRhythm />
        </FollowUp>
      </More>
    </Chapter>
  );
}
