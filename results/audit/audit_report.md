# Data integrity audit

Runs: 268; sessions: 67.

## Runs per session

| session   |   runs |
|:----------|-------:|
| follow    |     76 |
| post      |     96 |
| pre       |     96 |

## Flagged runs

| flag       |   runs |
|:-----------|-------:|
| count      |     99 |
| degenerate |      1 |

| subject   | session   |   run |   duration_s |   n_rest |   n_ah |   n_sf | flag       |
|:----------|:----------|------:|-------------:|---------:|-------:|-------:|:-----------|
| sub-15    | follow    |    02 |        48.34 |        5 |      0 |      0 | degenerate |

## Pairs of runs that share a recording

Screened 35778 pairs; 14 confirmed on every segment.

| run_a                    | run_b                      |   screen_r |   segment_median_r | forced   | verdict                                 |
|:-------------------------|:---------------------------|-----------:|-------------------:|:---------|:----------------------------------------|
| sub-02_B_post_02_eeg.mat | sub-02_B_follow_02_eeg.mat |      0.997 |              0.996 | True     | same recording                          |
| sub-02_B_post_01_eeg.mat | sub-02_B_follow_01_eeg.mat |      0.991 |              0.993 | True     | same recording                          |
| sub-02_B_post_03_eeg.mat | sub-02_B_follow_03_eeg.mat |      0.957 |              0.955 | True     | same recording                          |
| sub-02_B_post_04_eeg.mat | sub-02_B_follow_04_eeg.mat |      0.926 |              0.929 | True     | same recording                          |
| sub-21_T_pre_02_eeg.mat  | sub-22_T_pre_02_eeg.mat    |      0.963 |              0.877 | True     | shared recording, differently processed |
| sub-21_T_pre_04_eeg.mat  | sub-22_T_pre_04_eeg.mat    |      0.901 |              0.785 | True     | shared recording, differently processed |
| sub-21_T_pre_03_eeg.mat  | sub-22_T_pre_03_eeg.mat    |      0.526 |              0.560 | True     | shared recording, differently processed |
| sub-21_T_pre_01_eeg.mat  | sub-22_T_pre_01_eeg.mat    |      0.460 |              0.385 | True     | shared recording, differently processed |

## Byte-identical raw files (sourcedata.zip index)

| crc32    |     size | files                                                                                   |
|:---------|---------:|:----------------------------------------------------------------------------------------|
| dc44f8f5 | 21888000 | sub-02/follow/sub-02_B_follow_01_original.fdt;sub-02/post/sub-02_B_post_01_original.fdt |
| ae93ea3d | 22784000 | sub-02/follow/sub-02_B_follow_02_original.fdt;sub-02/post/sub-02_B_post_02_original.fdt |
| ffac269a | 23552000 | sub-02/follow/sub-02_B_follow_03_original.fdt;sub-02/post/sub-02_B_post_03_original.fdt |
| aee146d5 | 22464000 | sub-02/follow/sub-02_B_follow_04_original.fdt;sub-02/post/sub-02_B_post_04_original.fdt |
| 894ae38b | 22400000 | sub-21/pre/sub-21_T_pre_01_original.fdt;sub-22/pre/sub-22_T_pre_01_original.fdt         |
| 043e228b | 31808000 | sub-21/pre/sub-21_T_pre_02_original.fdt;sub-22/pre/sub-22_T_pre_02_original.fdt         |
| 1863a380 | 22976000 | sub-21/pre/sub-21_T_pre_03_original.fdt;sub-22/pre/sub-22_T_pre_03_original.fdt         |
| 3f0adea3 | 24384000 | sub-21/pre/sub-21_T_pre_04_original.fdt;sub-22/pre/sub-22_T_pre_04_original.fdt         |

## Decisions

Decided 2026-10-03 on integrity evidence only (no accuracy was looked at).

| Item | Evidence | Decision |
|------|----------|----------|
| sub-02 follow | 4 byte-identical raw runs with sub-02 post; preprocessed segment median r 0.929-0.996 | excluded (`configs/data.yaml`) |
| sub-21 pre and sub-22 pre | 4 byte-identical raw runs; preprocessed r 0.385-0.877; the imagery cue sequences differ in all 4 runs | both sessions excluded: one copy's labels do not match its signal and we cannot tell which; subjects stay linked |
| sub-15 follow run 02 | 48 s, 5 rest markers, no imagery cue | excluded as a run (`exclusions.runs`): its rest windows would have no imagery partner (revised 2026-10-03 in P03) |
| 99 runs with `count` flags | fewer events than 20/10/10, from segments EEGLAB cut out with their events | kept; windows are cut from the events present |
| other pairs | 6 confirmed pairs, all within sub-15, r 0.218-0.243 | independent (below 0.30) |

After exclusions: 255 of 268 runs, 64 of 67 sessions, 22 subjects with a pre
session; 5027 rest, 2511 affected-hand and 2516 sixth-finger events.
