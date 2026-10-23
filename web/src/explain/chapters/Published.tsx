import { Chapter, FollowUp, More } from "../../components/Chapter";
import { data, pct, pctRange } from "../data";
import { Elsewhere } from "../figures/Elsewhere";
import { LeakSlope } from "../figures/Evidence";
import { LeakDiagram } from "../figures/LeakDiagram";
import { LEAK_RANGE } from "../findings";

const L = data.leak;

export function Published() {
  return (
    <Chapter
      q="published"
      answer={
        <>
          No. The paper&apos;s method had already studied the trials it was tested on; tested fairly, it is right{" "}
          {pct(L.mean_leakfree)} of the time, where guessing gets 50%.
        </>
      }
      dial={{
        value: L.mean_leakfree,
        other: L.mean_replica,
        guess: 0.5,
        reading: (
          <>
            <span>
              <b>{pct(L.mean_leakfree)}</b> tested fairly
            </span>
            <span className="q-reading-other">{pct(L.mean_replica)} the paper&apos;s way, rebuilt</span>
          </>
        ),
      }}
    >
      <LeakDiagram />
      <More
        what={`what ${pct(L.published[0])} means, every patient, how we rebuilt it, and the same mistake in other data`}
      >
        <FollowUp ask={`What does ${pct(L.published[0])} mean?`}>
          <p>
            Out of every 100 times a patient imagined moving the hand or the sixth finger, the paper&apos;s method named
            the right one about {Math.round(L.published[0] * 100)} times. Guessing names it 50 times.
          </p>
        </FollowUp>
        <FollowUp ask="Is it lower for every patient?">
          <p>
            Yes, for all {L.n_positive} of {L.subjects.length}. Our rebuild of the paper&apos;s way gives{" "}
            {pct(L.mean_replica)}, close to its published {pctRange(L.published)}.
          </p>
          <LeakSlope />
          <p className="figure-note">
            Each grey line is one patient, scored the paper&apos;s way (left) and fairly (right); the black line is the
            average.
          </p>
        </FollowUp>
        <FollowUp ask="How did you test it?">
          <p>
            We rebuilt the paper&apos;s method from its published code and scored it twice on the same patients and
            trials: once as the paper did, its first step learning from every trial, and once with that step learning
            only from the trials used for learning. Nothing else changed.
          </p>
        </FollowUp>
        <FollowUp ask="Does the same mistake happen elsewhere?">
          <p>
            Yes. We repeated the check on two public datasets of imagined hand movements and, as an unrelated check, two
            of depression from resting EEG. The mistake raised the score in every one, by {LEAK_RANGE[0]} to{" "}
            {LEAK_RANGE[1]} points.
          </p>
          <Elsewhere />
        </FollowUp>
      </More>
    </Chapter>
  );
}
