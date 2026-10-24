import { Chapter, FollowUp, More, type Point } from "../../components/Chapter";
import { data, pct, pctRange } from "../data";
import { Elsewhere } from "../figures/Elsewhere";
import { LeakSlope } from "../figures/Evidence";
import { LeakDiagram } from "../figures/LeakDiagram";
import { LEAK_RANGE } from "../findings";

const L = data.leak;
// The arrays and means of `leak` are a standard CSP+LDA; `recipe` is the authors' own, rebuilt.
const R = L.recipe;
const N = L.subjects.length;
const LOWER =
  L.n_positive === N && R.n_positive === N
    ? `every one of the ${N} patients, in both`
    : `${L.n_positive} of the ${N} patients with the standard version`;

/** What the published score means and what inflates it, in four lines; the chapter-by-chapter page says them too. */
export const LEAK_POINTS: Point[] = [
  {
    label: `What ${pct(L.published[0])} means`,
    text: (
      <>
        Shown 4 s of brain signal from one trial, the method had to say &quot;hand&quot; or &quot;sixth
        finger&quot;. It was right about {Math.round(L.published[0] * 100)} times in 100; guessing is right 50
        times.
      </>
    ),
  },
  {
    label: "What inflates it",
    text: "Its first step learned from every trial, the test trials included, before it was tested on them: an exam seen in advance. The bracket below shows it.",
  },
  {
    label: "Without the leak",
    text: `${pct(R.leakfree)} for the authors' own recipe, rebuilt from their code, and ${pct(L.mean_leakfree)} for a standard version, with that step learning only from the learning trials; lower for ${LOWER}.`,
  },
  {
    label: "Why it matters",
    text: `At ${pct(L.published[0])}, it would be a usable two-command device. At ${pctRange([R.leakfree, L.mean_leakfree])}, it is barely above guessing.`,
  },
];

export function Published() {
  return (
    <Chapter
      q="published"
      answer={
        <>
          No. Rebuilt from the authors&apos; code, their recipe scores {pct(R.paper_way)} tested their way, not their{" "}
          {pct(L.published[0])}, and {pct(R.leakfree)} tested leakage-free, barely better than guessing; a standard
          version, shown here, falls from {pct(L.mean_replica)} to {pct(L.mean_leakfree)}.
        </>
      }
      dial={{
        value: L.mean_leakfree,
        other: L.mean_replica,
        guess: 0.5,
        reading: (
          <>
            <span>
              <b>{pct(L.mean_leakfree)}</b> tested leakage-free
            </span>
            <span className="q-reading-other">{pct(L.mean_replica)} tested the paper&apos;s way</span>
          </>
        ),
      }}
      points={LEAK_POINTS}
    >
      <LeakDiagram />
      <More what="every patient, how we rebuilt it, and the same mistake in other data">
        <FollowUp ask="Is it lower for every patient?">
          <p>
            Yes, for all {L.n_positive} of {N} with the standard version, the test we fixed in advance, and for{" "}
            {R.n_positive} of {R.n} with the authors&apos; recipe. Rebuilt, that recipe scores {pct(R.paper_way)} the
            paper&apos;s way, higher than its published {pctRange(L.published)}: we reproduce the leak, not the
            published number.
          </p>
          <LeakSlope />
          <p className="figure-note">
            Each grey line is one patient, the standard version scored the paper&apos;s way (left) and leakage-free
            (right); the black line is the average.
          </p>
        </FollowUp>
        <FollowUp ask="How did you test it?">
          <p>
            We scored two versions of the method twice on the same patients and trials: our rebuild of the
            authors&apos; own recipe, from their published code, and a standard version of CSP with LDA, the one our
            test fixed in advance used. Once as the paper did, the first step learning from every trial, and once
            leakage-free, that step learning only from the trials used for learning. Nothing else changed.
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
