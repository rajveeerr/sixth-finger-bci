# Pre-registration and deviation log

The plan of the stroke study and the record of every later change to it were kept in the
project's working notes, which are not part of the code. They are copied here so that both can
be read next to the paper and the report.

| File | What it is | Copied from |
|------|------------|-------------|
| `preregistration.md` | The pre-registration as frozen: hypotheses, design, outcomes, analysis plan, inference criteria and the limitations declared in advance | the working notes' `preregistration.md` at working-branch commit `caea954` (committed 2026-10-03 18:25 +0530), the commit that the annotated tag `prereg-v1` points to; the tag itself was created on 2026-10-08 at 23:43 +0530 |
| `deviations.md` | The deviation log: every change after the tag, each with its date, its reason and whether it was made before or after the confirmatory results; 33 entries, from 2026-10-09 to 2026-10-23 | section 12 of the working notes' evaluation protocol at commit `fe88a67` (2026-10-23 16:09 +0530), the last commit that changed it |

The frozen pre-registration's own deviation table (its section 7) is empty, as it was at the
tag. The protocol's log is the working record, and from 2026-10-11 every row was also copied
into section 7 of the working copy (the log's entry of that date says so).

## Verbatim, except for paths to private files

Both copies are verbatim, with one kind of change. A line that named a file of the working
notes by its path now gives a short description in square brackets instead, for example
`[private decision log, entry 44]` or `[the evaluation protocol]`, because those paths do not
exist outside the working notes. No other word was changed and no line was removed. The changed
lines are:

- `preregistration.md`: lines 5, 6, 11, 23, 44, 190, 206 and 318 (a path in the text), and
  lines 332 to 352 (the commands of the freeze checklist in section 8, whose file paths are
  replaced, so they show what was checked but no longer run as written);
- `deviations.md`: lines 5, 8, 9, 20, 26 and 35.

Both copies were checked for anything else private, such as paths into the working notes,
enrolment numbers or the names of writing tools. None was found besides the paths above.

## What the dates are worth

The dates above are git's own. A commit date and a tag date are written by whoever makes the
commit or the tag, and nothing outside this repository records them. The pre-registration was
not deposited with an independent registry, such as OSF, before the study began, so its timing
rests on the repository's history alone. The repository is private; the pre-registration, the
deviation log and the history behind them are available from the authors on request.

Section 1 of the pre-registration lists what had been seen before it was frozen: the integrity
audit, a labelled exploratory analysis of every patient and session, and decoding on the two
development patients. The deviation log discloses the results that were already known before
the calibration study (its entry "Results already known before P08").
