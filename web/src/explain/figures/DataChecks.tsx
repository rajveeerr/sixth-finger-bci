import { LINKS } from "../links";

// What we found wrong in the published data and analysis, how, and what we did about it.
// Source: results/audit/audit_report.md and the dataset card. Every decision about the
// data was taken before any accuracy was looked at.

const ROWS = [
  {
    what: "Two sessions that are one recording",
    found:
      "Patient 2's \"after therapy\" and \"follow-up\" sessions are the same files, byte for byte, though they are meant to be a month apart.",
    how: "We fingerprinted the raw file of each of the 268 runs and compared the signals of every pair of runs, 35,778 pairs in all.",
    did: "Kept one copy, dropped the other.",
  },
  {
    what: "Two patients with the same recording",
    found:
      "Patients 21 and 22 share identical raw files for their first session, yet the order of their cues differs, so one set of labels does not belong to its signal.",
    how: "The same comparison, then checking the order of the cues in each.",
    did: "Dropped both sessions: we cannot tell which labels are right.",
  },
  {
    what: "A broken run",
    found: "One of patient 15's follow-up runs lasts 48 seconds and has no imagery cue in it.",
    how: "Counting the cues and the length of every run.",
    did: "Dropped that run.",
  },
  {
    what: "Test trials used to build the method",
    found:
      "In the published analysis, the spatial filters (CSP) were fitted on all the trials before some were set aside for testing, so the test was not on unseen data.",
    how: "Reading the authors' analysis code, then rebuilding their method both ways on the same data.",
    did: "Measured the effect. It explains the published 85% (chapter 8).",
    leak: true,
  },
];

/** The problems we found in the data and the published analysis. */
export function DataChecks() {
  return (
    <div className="checks">
      <ol className="checks-list">
        {ROWS.map((r, i) => (
          <li key={r.what} data-leak={r.leak ? "" : undefined}>
            <span className="checks-num">{i + 1}</span>
            <div>
              <h3>{r.what}</h3>
              <p>{r.found}</p>
              <dl>
                <div>
                  <dt>How we found it</dt>
                  <dd>{r.how}</dd>
                </div>
                <div>
                  <dt>What we did</dt>
                  <dd>{r.did}</dd>
                </div>
              </dl>
            </div>
          </li>
        ))}
      </ol>
      <p className="checks-note">
        We decided what to drop before looking at any result, so the choice could not favour one. The full record is in
        our <a href={LINKS.audit.url}>data audit report</a> and <a href={LINKS.card.url}>dataset card</a>.
      </p>
    </div>
  );
}
