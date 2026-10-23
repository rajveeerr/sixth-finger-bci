import { Chapter, FollowUp, More } from "../../components/Chapter";
import { DemoStage } from "../../components/DemoStage";
import type { DemoStreamControls } from "../../stream/useDemoStream";
import { ModelFacts } from "../figures/ModelFacts";
import { EegnetRef } from "../refs";

export function SeeItWork({ stream }: { stream: DemoStreamControls }) {
  return (
    <Chapter
      q="demo"
      answer={
        <>
          Yes. Here a patient&apos;s recording that the model never learned from plays at real speed; when they imagine
          moving, the finger should bend.
        </>
      }
    >
      <DemoStage stream={stream} />
      <More
        label="How the model works"
        what="EEGNet, CSP and LDA in a line each, the model step by step, and why this patient"
      >
        <FollowUp ask="What are EEGNet, CSP and LDA?">
          <div className="facts facts-terms">
            <dl>
              <div>
                <dt>
                  <EegnetRef />
                </dt>
                <dd>
                  A small neural network built for EEG. It learns from examples which sensors and which rhythms tell the
                  choices apart. The demo runs it.
                </dd>
              </div>
              <div>
                <dt>CSP</dt>
                <dd>
                  Common spatial patterns: learns how to mix the 40 sensors so that two movements differ as much as
                  possible. The paper&apos;s method starts with it.
                </dd>
              </div>
              <div>
                <dt>LDA</dt>
                <dd>
                  Linear discriminant analysis: draws a straight line between the two movements in what CSP gives it.
                </dd>
              </div>
            </dl>
          </div>
        </FollowUp>
        <ModelFacts />
      </More>
    </Chapter>
  );
}
