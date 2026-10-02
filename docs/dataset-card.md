# Dataset card

## Source

| | |
|---|---|
| Title | A multi-paradigm and longitudinal EEG dataset including the "sixth-finger" and "affected-hand" motor imagery of stroke patients |
| Article | Wang, Z., Liu, Y., Huang, S. et al., *Scientific Data* 13, 1109 (2026). https://doi.org/10.1038/s41597-026-07787-y |
| Data | figshare, https://doi.org/10.6084/m9.figshare.30509165, version 11 (2026-06-23) |
| Data licence | CC BY 4.0 |
| Recording site | Tianjin Huanhu Hospital; protocol approved by its Medical Ethics Committee (IEC-B-003-V3.0) |
| Consent | Written informed consent, including public sharing of de-identified data |

We use the data as published and do not attempt to re-identify participants.
The demo bundle (`web/public/demo/`) redistributes a small number of held-out,
preprocessed EEG windows; CC BY 4.0 allows this with attribution, which this
card and the demo page give.

## Participants

24 adults after a first-ever stroke (18 male, 6 female; age 34 to 77 years,
mean 55.75), enrolled 3 to 14 months after onset. Fifteen had right
hemiplegia and nine had left hemiplegia (sub-03, 04, 05, 09, 11, 12, 17, 18,
24). Fourteen received two weeks of BCI training with a robotic sixth finger
(BCI group) and ten received conventional therapy of equal dose (Traditional
group).

EEG was recorded at three time points: before the two-week intervention
(`pre`), immediately after it (`post`) and one month later (`follow`).
Follow-up recordings are missing for sub-05, sub-17, sub-18, sub-20 and sub-21.

## Task

Each trial lasted about 15.5 to 16 s in the recordings (14 s in the article's
description). A fixation cross marked rest (event code 1). About 8.6 s later a
picture cue asked the participant to imagine either a grasp with the affected
hand (code 2) or a flexion of a robotic sixth finger worn on the affected
wrist (code 3), kinesthetically and without moving, for at least 6 s. Each run
has 20 trials (10 of each imagery type, in random order) and each session has
4 runs, giving 40 affected-hand trials, 40 sixth-finger trials and 80 rest
periods per session.

## Signals

64-channel Neuracle NeuSen W amplifier, 250 Hz, Ag/AgCl electrodes in the
10-20 system, online 50 Hz notch. The authors' preprocessed files, which we
use, were band-pass filtered (5 to 35 Hz), notch filtered, re-referenced to the
common average, reduced to 43 channels, cleaned of transient artifacts by
manual inspection (with spherical interpolation of bad channels) and cleaned
of eye components with extended Infomax ICA. We further drop Fpz, Fp1 and Fp2,
as the authors did, keeping 40 channels over frontal, central, parietal and
parieto-occipital areas.

Files: `processeddata.zip` (268 MATLAB v7.3 files, 3.6 GB unzipped,
md5 `7a3138c15fa215b0e607287479211169`) and the optional raw recordings in
`sourcedata.zip` (EEGLAB `.set`/`.fdt`, md5
`74dabab47f477e5bc0510b1e2e705c5a`).

## Windows used in this project

| Class | Event | Window after event onset | Samples |
|-------|-------|--------------------------|---------|
| Rest | 1 | 1.0 to 5.0 s | 1000 |
| Affected-hand imagery | 2 | 1.0 to 5.0 s | 1000 |
| Sixth-finger imagery | 3 | 1.0 to 5.0 s | 1000 |

Windows that cross a discontinuity left by artifact rejection are dropped and
counted.

## Known issues

We found the following while auditing the archives. Details and evidence
are in `results/audit/`.

1. The four raw runs of `sub-02/post` and `sub-02/follow` are byte-identical,
   and the preprocessed runs of the two sessions are near-identical after a
   time shift. We exclude `sub-02/follow`.
2. The raw runs of `sub-21/pre` and `sub-22/pre` are byte-identical, but the
   imagery cue sequences in the preprocessed files differ in all four runs, so
   one of the two sessions has labels that do not match its signal. We exclude
   both pre sessions and never place one subject in training while the other
   is tested.
3. The cue timing in the files (imagery cue about 8.57 s after the rest
   marker, next rest marker 6.7 to 7.4 s after the cue) differs from the 7 s +
   1 s + 6 s description in the article. Our windows lie inside the rest and
   imagery periods under either timing.
4. `sub-15/follow` run 02 lasts 48 s and holds no imagery cue; we exclude it. 99 runs have event counts other than 20/10/10, mostly because EEGLAB removed
   events with the segments it cut.

## Audit summary

All 268 runs have 43 channels at 250 Hz and no flat channel. A screen of all
35 778 run pairs (C3, 20 s segments aligned separately) found no shared
recording beyond the two known cases. After exclusions: 255 runs in 64
sessions, with 5027 rest, 2511 affected-hand and 2516 sixth-finger events
(nominal 5100, 2550, 2550). Source: `results/audit/`.
4. The article's classification code fits CSP spatial filters on all trials
   before cross-validation, so the reported 85 to 86 % accuracy includes
   information from the test folds. We report both that protocol and
   leakage-free alternatives.
5. Minor metadata inconsistencies: `task-MotorImagery_eeg.json` lists 60 EEG
   channels, average reference and AFz ground, while the article states 64
   channels, CPz reference and a forehead ground; `participants.json` describes
   a `diagnosis` column that `participants.tsv` does not contain.

## Intended use here

Offline research on motor-imagery decoding and calibration efficiency, and a
replay demonstration of decoded commands on a virtual hand. Not for clinical
decisions.
