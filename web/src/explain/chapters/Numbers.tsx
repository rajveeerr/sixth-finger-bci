import { Chapter, FollowUp, More } from "../../components/Chapter";
import { benchRow, data, pct, pct1 } from "../data";
import { BenchLines, BenchTable } from "../figures/Benchmark";
import { LearnTest } from "../figures/LearnTest";
import { SPLITS } from "../findings";

const B = data.benchmark;
const SWITCH = benchRow("T3_sf_vs_rest");
const WHICH = benchRow("T1_ah_vs_sf");
const ALL = benchRow("T2_rest_ah_sf");
const MOST_PRACTICE = data.calibration.scratch[data.calibration.scratch.length - 1].k;
const SURE = (() => {
  const { sure, sure_share, not_chosen } = SWITCH.best;
  if (sure === undefined || sure_share === undefined || not_chosen === undefined) {
    throw new Error("The switch's benchmark row lacks its scores when sure");
  }
  return { acc: sure, share: sure_share, notChosen: not_chosen };
})();

export function Numbers() {
  return (
    <Chapter
      q="numbers"
      answer={
        <>
          Tested fairly on {B.n} patients, the best models are right {pct1(SWITCH.best.mean)} of the time on sixth finger
          or rest and {pct1(WHICH.best.mean)} on hand or sixth finger, where guessing gets {pct(SWITCH.chance)}.
        </>
      }
    >
      <BenchTable />
      <BenchLines />
      <More what="how each was tested, and how the best were chosen">
        <FollowUp ask="How was each tested?">
          <p>
            Every score in the table comes from the same split: for each of the {B.n} patients, runs 1 and 2 of the first
            session to learn from, and runs 3 and 4, recorded after them, to test on. Balanced accuracy is how often each
            choice is read right, averaged over the choices, so a model that always says rest cannot score well; guessing
            gets {pct(SWITCH.chance)} with two choices and {pct(ALL.chance)} with three.
          </p>
          <LearnTest split={SPLITS.bench} />
          <p className="figure-note">
            The lines under the table were each tested their own way. Setting up: a new patient&apos;s model learned
            from 1 to {MOST_PRACTICE} practice trials of each movement in runs 1 and 2. Another day: the model learned
            from all of the first session and was tested on runs 3 and 4 two weeks later. Live: runs 3 and 4 were played
            start to end. The leak: the paper&apos;s own random split of all the trials, which is why its fair score is
            not the table&apos;s {pct1(WHICH.csp_lda)}.
          </p>
        </FollowUp>
        <FollowUp ask="How was the best chosen?">
          <p>
            For sixth finger or rest, the switch was chosen over the other models on runs 1 and 2 alone, before runs 3
            and 4 were scored. A network that first learned from other patients scored a little higher on runs 3 and 4,{" "}
            {pct1(SURE.notChosen)}, but lower on runs 1 and 2, so it was not the one chosen. Acting only when
            sure, with how sure set for each patient on runs 1 and 2, the switch acts on{" "}
            {pct(SURE.share)} of the windows and is right on {pct1(SURE.acc)} of them. For
            hand or sixth finger, the best is the network that first learned from every recording of the other patients;
            for all three, the demo&apos;s own model.
          </p>
        </FollowUp>
      </More>
    </Chapter>
  );
}
