import { Chapter } from "../../components/Chapter";
import { data, pct, pctRange } from "../data";
import { LEAK_RANGE, PRACTICE_S, SCRATCH_MIN } from "../findings";

const S = data.sixth;
const R = data.leak.recipe;

const ADDS = [
  {
    title: "A leakage-free score for a published result",
    text: `The paper's ${pct(data.leak.published[0])} was tested with a leak. Rebuilt, its recipe scores ${pct(R.paper_way)} that way and ${pct(R.leakfree)} leakage-free, lower for all ${R.n} patients.`,
    href: "#published",
  },
  {
    title: "The same mistake, measured in other data",
    text: `In other public datasets, of imagined movement and of depression, the same mistake raised the score by ${LEAK_RANGE[0]} to ${LEAK_RANGE[1]} points.`,
    href: "#published",
  },
  {
    title: "A check of the shared recordings",
    text: "Three problems in the public data, found by comparing every pair of runs and dealt with before any test.",
    href: "#data",
  },
  {
    title: "How fast a new patient can start",
    text: `${PRACTICE_S} s of practice with help from other patients, the one way we tried, against ${SCRATCH_MIN} min alone, for a movement the body never had.`,
    href: "#use",
  },
  {
    title: "What the sixth finger can be used as today",
    text: `A candidate switch that says "move now", tested offline: right ${pct(S.rest.mean)} of the time on 4 s pieces, but catching ${pct(S.continuous.finger_on)} of sixth-finger periods played continuously; not yet a command apart from the hand.`,
    href: "#command",
  },
  {
    title: "A benchmark in healthy people",
    text: `Two grasps of one hand, a week apart, are told apart ${pctRange(S.healthy.pairs)} of the time: hard in anyone.`,
    href: "#command",
  },
  {
    title: "A demo anyone can run in the browser",
    text: "The model runs on trials it never saw, on our server or in your browser.",
    href: "#demo",
  },
];

export function Added() {
  return (
    <Chapter
      q="added"
      answer={
        <>
          The recordings, the paper&apos;s method and the models were already out there; what is new is a leakage-free
          test of them, and what it shows.
        </>
      }
    >
      <ol className="adds">
        {ADDS.map((a) => (
          <li key={a.title}>
            <a href={a.href}>{a.title}</a>
            <p>{a.text}</p>
          </li>
        ))}
      </ol>
    </Chapter>
  );
}
