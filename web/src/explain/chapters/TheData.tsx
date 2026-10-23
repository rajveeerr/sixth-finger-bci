import { Chapter, FollowUp, More } from "../../components/Chapter";
import { DataChecks } from "../figures/DataChecks";
import { HeadMap } from "../figures/HeadMap";
import { PatientSees } from "../figures/PatientSees";
import { Session } from "../figures/Session";
import { LINKS } from "../links";
import { DatasetRef } from "../refs";

export function TheData() {
  return (
    <Chapter
      q="data"
      answer={
        <>
          No. They come from a public study of 24 stroke patients in Tianjin, China (
          <DatasetRef>Wang et al., 2026</DatasetRef>): each rested, then imagined moving the affected hand or a sixth
          finger, 80 times a visit.
        </>
      }
    >
      <Session />
      <More label="What is in it" what="the 40 sensors, one trial as the patient sees it, and four problems we found">
        <p className="more-lede">
          The recordings are <a href={LINKS.data.url}>free to download</a>, and our{" "}
          <a href={LINKS.card.url}>dataset card</a> sums them up in one page.
        </p>
        <HeadMap />
        <PatientSees />
        <FollowUp ask="Was the data sound?">
          <p>
            Not all of it. Before any test we compared every pair of runs and found three problems in the shared
            recordings, and one in how the paper tested its method, which is the next question.
          </p>
          <DataChecks />
        </FollowUp>
      </More>
    </Chapter>
  );
}
