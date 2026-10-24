
// What we found wrong in the published data and analysis, how, and what we did about it,
// one line each until the reader opens one. Source: results/audit/audit_report.md and the
// dataset card. Every decision about the data was taken before any accuracy was looked at.

import { data, pct } from "../data";

const R = data.leak.recipe;

const ROWS = [
  {
    what: "Two sessions that are one recording",
    found:
      'Patient 2\'s "after therapy" and "follow-up" sessions are exactly the same files, though they are meant to be a month apart.',
    how: "We gave the raw file of each of the 268 runs a checksum (a short code that changes if any part of the file changes) and compared the signals of every pair of runs, 35,778 pairs in all.",
    did: "Kept one copy",
  },
  {
    what: "Two patients with the same recording",
    found:
      "Patients 21 and 22 share identical raw files for their first session, yet the lists of which movement was asked for, and when, differ. One list cannot belong to that signal.",
    how: "The same comparison, then reading each session's list of instructions.",
    did: "Dropped both: we cannot tell whose labels are right",
  },
  {
    what: "A broken run",
    found: "One of patient 15's follow-up runs lasts 48 seconds and has no instruction to imagine in it.",
    how: "Counting the instructions in every run and measuring its length.",
    did: "Dropped that run",
  },
  {
    what: "Test trials used to build the method",
    found:
      "In the published analysis, the method's first step (CSP, which learns how best to combine the sensors) learned from every trial, including the ones later used to test it. So the test was not on unseen data.",
    how: "Reading the authors' analysis code, then rebuilding their method both ways on the same data.",
    did: `Measured it: rebuilt, it lifts ${pct(R.leakfree)} to ${pct(R.paper_way)}`,
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
            <details>
              <summary>
                <span className="checks-num">{i + 1}</span>
                <span className="checks-what">{r.what}</span>
                <span className="checks-did">{r.did}</span>
              </summary>
              <div className="checks-body">
                <p>{r.found}</p>
                <p>
                  <b>How we found it.</b> {r.how}
                </p>
              </div>
            </details>
          </li>
        ))}
      </ol>
      <p className="checks-note">
        Open a row for what was wrong and how we found it. We decided what to drop before looking at any result, so the
        choice could not push any result up. The full record is in the report (chapter 3, the integrity audit).
      </p>
    </div>
  );
}
