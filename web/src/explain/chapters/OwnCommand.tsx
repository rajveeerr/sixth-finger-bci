import { Chapter, FollowUp, More } from "../../components/Chapter";
import { data, pct, pctRange } from "../data";
import { RhythmMeasured } from "../figures/BrainRhythm";
import { EachPatient, WhatSwitchesOn, WhenSure } from "../figures/Evidence";
import { LearnTest } from "../figures/LearnTest";
import { pctFine, SPLITS } from "../findings";
import { StripTerm, WhenSureTerm } from "../refs";

const S = data.sixth;

export function OwnCommand() {
  return (
    <Chapter
      q="command"
      answer={
        <>
          As a switch that says &quot;move now&quot;, yes, right {pct(S.rest.mean)} of the time; as a command apart from
          the hand, not yet, because imagining the hand switches it on too.
        </>
      }
      dial={{
        value: S.rest.mean,
        other: S.which.mean,
        guess: 0.5,
        reading: (
          <>
            <span>
              <b>{pct(S.rest.mean)}</b> sixth finger or rest
            </span>
            <span className="q-reading-other">{pct(S.which.mean)} hand or sixth finger</span>
          </>
        ),
      }}
    >
      <EachPatient />
      <More what="acting only when sure, what switches it on, why the hand and the finger look alike, how it was tested">
        <FollowUp ask="What if it acts only when sure?">
          <p>
            It gets better. With <WhenSureTerm>how sure it must be</WhenSureTerm> set for each patient beforehand, it is
            right on {pct(S.sure.acc)} of the decisions it takes, and takes {pct(S.sure.share)} of them. While the
            patient rests, it moves the finger by mistake {pctFine(S.fires.rest.sure)} of the time.
          </p>
          <WhenSure />
        </FollowUp>
        <FollowUp ask="What switches it on?">
          <p>
            Imagining a movement, not the finger itself. It never learned from an imagined hand movement, yet those
            switch it on {pct(S.fires.hand.all)} of the time, nearly as often as the sixth finger (
            {pct(S.fires.finger.all)}).
          </p>
          <WhatSwitchesOn />
        </FollowUp>
        <FollowUp ask="Why can't it tell the hand from the sixth finger?">
          <p>
            Imagining either one quiets the same rhythm, by about as much. Two movements of one hand are hard to tell
            apart even in healthy people: in {S.healthy.people} of them, two grasps learned on one day were told apart a
            week later {pctRange(S.healthy.pairs)} of the time, about what guessing gets. Our best model for it is right{" "}
            {pct(S.which_sure.acc)} of the time when it is sure, but it is sure on only {pct(S.which_sure.share)} of
            trials.
          </p>
          <RhythmMeasured />
        </FollowUp>
        <FollowUp ask="How was it tested?">
          <LearnTest split={SPLITS.sixth} />
          <p>
            For each patient, a simple model learned sixth finger or rest from runs 1 and 2, reading only <StripTerm />,
            and was tested on runs 3 and 4; all 40 sensors give {pct(S.rest.all_sensors)}. For hand or sixth finger, a
            network first learned from every recording of the other patients, then was adjusted to runs 1 and 2. Every
            method and setting was fixed before runs 3 and 4 were scored. The healthy people come from another public
            recording of imagined grasps, made on two days a week apart.
          </p>
        </FollowUp>
      </More>
    </Chapter>
  );
}
