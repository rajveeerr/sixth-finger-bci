import { Chapter } from "../../components/Chapter";
import { data, pct, pctRange } from "../data";
import { LEAK_RANGE, PRACTICE_S, SCRATCH_MIN } from "../findings";

const S = data.sixth;

const ADDS = [
  {
    title: "A fair score for a published result",
    text: `The paper's ${pct(data.leak.published[0])} is ${pct(data.leak.mean_leakfree)} tested fairly, lower for all ${data.leak.subjects.length} patients, and we found why.`,
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
    text: `${PRACTICE_S} s of practice with help from other patients, against ${SCRATCH_MIN} min alone, for a movement the body never had.`,
    href: "#use",
  },
  {
    title: "What the sixth finger can be used as today",
    text: `A switch that says "move now", right ${pct(S.rest.mean)} of the time, not yet a command apart from the hand; also played as if live, and weeks later.`,
    href: "#command",
  },
  {
    title: "A benchmark in healthy people",
    text: `Two grasps of one hand, a week apart, are told apart ${pctRange(S.healthy.pairs)} of the time: hard in anyone.`,
    href: "#command",
  },
  {
    title: "An open demo",
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
          The recordings, the paper&apos;s method and the models were already out there; what is new is a fair test of
          them, and what it shows.
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
