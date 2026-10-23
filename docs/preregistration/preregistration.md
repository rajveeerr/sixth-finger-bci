# Pre-registration (frozen at tag `prereg-v1`)

Status: draft written 2026-10-02; RQ1b, the co-primary T3 outcome and the
pseudo-online metrics added 2026-10-03; decisions M1–M6, S7–S10, N12–N13
([private decision log, entries 25–36]) and the freeze-review fixes
([private decision log, entries 40–46]) adopted 2026-10-03, all before
`prereg-v1`, before any public-dataset download (nothing is under the MOABB
data directory) and before any decoder was trained on a subject other than
the development subjects. What has been observed is listed in full in §1
("Data already observed"). After the tag, changes are deviations and are
listed in [the evaluation protocol] §12 and in the paper.
Frozen 2026-10-03 at the end of P05, after the freeze checklist (§8) passed
and the evaluation code that implements §3 and §5 was committed and tested.

## 1. Study information

- **Title:** Teaching a brain–computer interface a new finger: calibration-efficient decoding of sixth-finger motor imagery in stroke patients.
- **Authors:** Rajveer Singh, Vivek Yadav, Ansh Dahiya (B.Tech ECE, MSIT); guide Dr. Suman Lata (paper co-author). Analysis carried out by Rajveer Singh.
- **Data:** Wang et al., Scientific Data 13, 1109 (2026); figshare 10.6084/m9.figshare.30509165, version 11, CC BY 4.0. Secondary analysis of public, de-identified data.
- **Data already observed:**
  - dataset metadata and integrity checks (duplicates, event counts; `results/audit/`);
  - P04 exploratory analysis of **all subjects and sessions, with class labels**: group and per-subject ERD/ERSP, spectra, time–frequency maps and topomaps (`results/summary/eda_erd_values.csv`, `results/summary/eda_quality_flags.csv`, `docs/figures/eda_*`). No channel, band, window, subject or exclusion was chosen from these figures;
  - decoding only on the development subjects sub-01 and sub-03 (and sub-07 for a transfer smoke test), for pipeline debugging ([private working notes]), and the P05 harness smoke runs on sub-01 and sub-03 with two harness decoders that are not methods of this study (`results/runs/smoke/`). No decoder has been trained or scored on any other subject;
  - the P04 observation that sixth-finger mu ERD at C3 is more negative than hand ERD (17 of 22 subjects, exploratory Wilcoxon p = 0.059) is **not** a hypothesis of this study and is not tested again here.


## 2. Hypotheses

Fixed comparison pairs, chosen before any result and never re-selected:
**confirmatory** `rct_tslr` (transfer) vs `ts_lr` (from scratch);
**secondary** `eegnet_ea_ft` vs `eegnet_scratch`. Comparisons of the best
method of each kind are descriptive only.

- **H1 (RQ1).** For affected-hand vs sixth-finger imagery (T1), session `pre`, the registry `csp_lda` (bandpower input, protocol §5) has higher balanced accuracy under `paper_replica` than under leakage-free 10×10-fold CV (`cv_leakfree`). The dev-subject preview already showed this direction, so the primary quantity is the size of the inflation in points with a bootstrap CI, reported with the test. `csp_lda_replica` (the authors' ERSP mu feature, 10 filters, no regularisation, as in `Step7`) gives the replication number as a sanity check, not the confirmatory test.
- **H1b (RQ1b).** On two public healthy-subject MI datasets (`BNCI2014_001`, `Cho2017`; left vs right hand), the same registry `csp_lda` has higher balanced accuracy under `paper_replica` than under `cv_leakfree`, on each dataset. `loro` and `chrono` are reported alongside.
- **H2a (RQ2).** In S1 (new user), task T2 (REST/AH/SF), session `pre`: the per-subject area under the learning curve (ALC) over k ∈ {1, 2, 3, 5, 10} differs between `rct_tslr` and `ts_lr` (expected direction: transfer higher).
- **H2b (RQ2).** In S1, task T2, session `pre`: the advantage of `rct_tslr` over `ts_lr` in balanced accuracy is smaller at k = all than at k = 5 (the curves converge).
- **H3 (RQ3).** In S2 (new command), session `pre`, `rct_tslr` beats `ts_lr` on at least one of two co-primary outcomes: (a) ALC over k ∈ {1, 2, 3, 5} of T3 (SF vs REST) balanced accuracy; (b) ALC over k ∈ {1, 2, 3, 5} of T2 (REST/AH/SF) balanced accuracy.
- **H3c (RQ3, own-hand control).** In S2, session `pre`, at k = 2 and at k = 5, `rct_tslr`'s T3 balanced accuracy exceeds that of `ah_proxy` (the target's own AH + REST decoder, scoring "not REST" as SF). This asks whether the SF command adds anything over a detector of any imagery.
- **H4 (RQ4, exploratory, no confirmatory test).** Hemisphere mirroring improves cross-subject transfer; decoders lose accuracy from pre to post/follow-up; 8 electrodes retain most of the 40-electrode accuracy; in pseudo-online replay the SF command is detected in most SF imagery periods at a false-activation rate reported per minute of rest.

## 3. Design

Exactly as [the evaluation protocol] at the tag commit;
the settings that decide a confirmatory result are repeated here so this
document stands alone. If the two ever disagree, this document wins for the
tests of §5.

<!-- confirmatory:start -->

### 3.1 Data

- Preprocessed files as published (5–35 Hz, ICA, common average reference);
  40 channels; windows [1, 5) s after each event (1000 samples); windows that
  overlap a `boundary` event are dropped; `car40` off; `mirror` off.
- **Exclusions** (from the P02 audit, final at the tag): session `sub-02/follow`;
  sessions `sub-21/pre` and `sub-22/pre` (raw runs byte-identical but cue
  sequences differ in all four runs, so one copy's labels do not match its
  signal); run `sub-15/follow/02` (48 s, no imagery cue). sub-21 and sub-22
  are one group in every cross-subject split. After exclusions: 255 runs,
  64 sessions, 22 subjects with a `pre` session
  (`results/audit/audit_report.md`). No subject is excluded for low accuracy.
- **Population.** Confirmatory (`pre`): the 22 subjects sub-01 to sub-24
  except sub-21 and sub-22, all independent. Replication (`post`): all 24
  subjects, 23 independent groups (sub-21 and sub-22 linked).
- **Tasks.** T1 `T1_ah_vs_sf` (AH vs SF), T2 `T2_rest_ah_sf` (REST vs AH vs
  SF), T3 `T3_sf_vs_rest` (SF vs REST).

### 3.2 Within-session protocols (RQ1, H1)

- Per subject and session, task T1, every window of the session.
- `cv_leakfree`: `RepeatedStratifiedKFold(n_splits=10, n_repeats=10,
  random_state=0)` over trials, stratified by class; the whole pipeline is
  fitted inside each training fold.
- `paper_replica`: the same 100 folds; every stage of the method's pipeline
  before the final classifier (for `csp_lda`: the CSP) is fitted once on all
  windows of the session, then only the classifier is fitted inside each
  training fold. The hyperparameters are the method's own (§3.6), identical
  under both protocols, so the difference measures the leak alone.
- `loro`: one fold per run present in the session, testing on that run.
- `chrono`: train on the session's runs 01–02, test on its runs 03–04.
- Sessions with three runs (only `sub-15/follow`, run 02 excluded): `loro` has
  3 folds; `chrono` trains on run 01 alone. This session is not in any
  confirmatory test.
- Per-subject value: mean balanced accuracy over the folds (100 for the CV
  protocols); `chrono` has one value.
- Methods (RQ1), all under all four protocols:
  `csp_lda`, `csp_lda_replica`, `csp_svm`, `fbcsp_lda`, `mdm`, `ts_lr`
  (`csp_lda` confirmatory, `csp_lda_replica` the sanity check).
  `csp_lda_replica` takes the `ersp_mu` input, every other method the
  `bandpower` input (the cached windows).

### 3.3 Public datasets (RQ1b, H1b)

- `BNCI2014_001` and `Cho2017` through MOABB 1.7.2 (the pinned `moabb`
  extra), every subject in the dataset's MOABB `subject_list`, paradigm
  `LeftRightImagery(fmin=5, fmax=35, resample=250)`, the dataset's MOABB
  default imagery interval (`dataset.interval`, written into the results
  file), every EEG channel the dataset provides.
- Method `csp_lda`, hyperparameters of §3.6, the four protocols of §3.2 per
  subject and session. Runs are MOABB's `run` column; a session with fewer
  than four runs is cut into four blocks of consecutive trials in recording
  order, which play the role of runs. `chrono` trains on the first half of
  the runs (blocks) and tests on the second half.
- Per-subject value: as §3.2; for `BNCI2014_001` the mean of its two
  sessions.
- Nothing is tuned on these datasets.

### 3.4 Calibration sampling (RQ2, RQ3)

- Per target subject and session: **pool** = runs 01–02, **test** = runs
  03–04 of that session. The test runs are never used for fitting,
  selection, early stopping, normalisation statistics, alignment
  references, hyperparameter choice.
- **Budget** k = trials per budget class drawn from the pool,
  k ∈ {0, 1, 2, 3, 5, 10, all}; `all` is 20 in `configs/protocol.yaml` and
  means every available trial; any k above what a class has is capped and
  the used value is stored as `k_used`. Trials are drawn per class without
  replacement; the REST window of a drawn trial always comes with it.
- **Draws.** For 0 < k < all: 10 random draws with seeds 0–9
  (`numpy.random.default_rng(seed)`) for classical methods, 5 (seeds 0–4) for
  EEGNet methods. k = 0 and k = all: one draw. A draw is made once per
  (subject, session, scenario, k, seed) from the three-class pool and shared
  by every method and both tasks, so all comparisons are paired. The
  chronological draw (first k trials of each class by run and trial order) is
  a sensitivity check and never enters a confirmatory value.
- **Scenarios.** `S1_new_user`: k AH trials and k SF trials, with their 2k
  REST windows. `S2_new_command`: every AH trial of the pool with its REST
  window, plus k SF trials with their k REST windows.
- **Training windows per task.**

  | Scenario | Task | Target windows with labels |
  |----------|------|----------------------------|
  | S1 | T2 | every window of the 2k drawn trials |
  | S1 | T3 | the SF and REST windows of the k drawn SF trials |
  | S2 | T2 | every window S2 provides (all pool AH trials, k drawn SF trials) |
  | S2 | T3 | the SF and REST windows of the k drawn SF trials |

- **Methods.** From scratch `csp_lda`, `mdm`, `ts_lr`, `eegnet_scratch`
  (target windows only). Transfer `pooled_tslr`, `rct_mdm`, `rct_tslr`,
  `eegnet_ea_ft`: the same target windows plus every window of the task's
  classes from all other subjects (all available sessions), never the target
  nor its linked partner. In S2 also `ah_proxy`: `ts_lr` with the §3.6
  settings, trained on the AH and REST windows of every pool AH trial (two
  classes); for T3 its AH probability is scored as SF; for T2 its SF
  probability is 0. It does not depend on k, so it is fitted once per
  subject and session and its value is the same at every k, including 0.
- **Unlabelled target data** (alignment, re-centering): at k > 0 exactly the
  target windows with labels above, used without labels (unlabelled budget =
  labelled budget); at k = 0 the declared fixed set, the REST windows of all
  trials of runs 01–02 (40 fixation periods × 7 s ≈ 4.7 min, counted in the
  calibration minutes).
- **Undefined cells** (written as missing, never as chance, excluded from
  that cell only): every from-scratch method at S1 k = 0; every from-scratch
  method except `ah_proxy` at S2 k = 0 (no SF example); `csp_lda` at k = 1.
  `ts_lr` and `rct_tslr` are defined at every k ≥ 1, so the confirmatory pair
  has no undefined cell in any confirmatory ALC.
- **Test windows.** T2: every REST, AH and SF window of runs 03–04. T3: every
  SF window and every REST window of runs 03–04 (REST of AH trials included).
  T3 decoders also classify the AH windows of runs 03–04 for the SF-vs-AH
  confusion; those predictions never enter T3 balanced accuracy.

### 3.5 Summaries

- Per-subject value at a k: mean balanced accuracy over the random draws of
  that k (one value at k = 0 and k = all).
- **ALC** over a set K of budgets (k ≥ 1, nominal k on the axis):
  x = ln(1 + k), y = (BA − c) / (1 − c) with chance c = 1/2 (T3) and 1/3
  (T2); ALC = trapezoid area of y over x divided by (x_max − x_min). A
  chance-level curve gives 0, a perfect one 1; below chance is negative.
  Implemented by `alc` in `src/sixthfinger/evaluation/stats.py` (P05
  step 4.6).

### 3.6 Hyperparameters (fixed now)

| Method | Settings |
|--------|----------|
| `csp_lda` | CSP 6 components, `reg="ledoit_wolf"`, `log=True`; LDA `solver="lsqr"`, `shrinkage="auto"`; three classes through MNE's multiclass CSP |
| `csp_lda_replica` | ERSP mu input (8–13 Hz power in dB relative to the second before the cue, [1, 5) s); CSP 10 components, `reg=None`, `log=True`; LDA scikit-learn defaults |
| `csp_svm` | CSP as `csp_lda`; linear SVC, C = 1, `probability=True`, `random_state=0` |
| `fbcsp_lda` | bands 8–12, 12–16, 16–20, 20–24, 24–28, 28–32 Hz (4th-order Butterworth, zero phase); CSP 4 components per band as `csp_lda`; `SelectKBest(mutual_info_classif, k=8)`; LDA as `csp_lda` |
| `mdm` | covariances `oas`; MDM, Riemannian metric |
| `ts_lr`, `ah_proxy` | covariances `oas`; tangent space, `metric="riemann"`; logistic regression C = 1, `max_iter=1000` |
| `pooled_tslr` | as `ts_lr` on source + target windows, no alignment |
| `rct_mdm`, `rct_tslr` | pyRiemann `TLCenter` re-centering to identity per subject, then MDM (`rct_mdm`) and tangent space + logistic regression C = 1 (`rct_tslr`); target weight from {1, 5, 20} |
| `eegnet_scratch` | braindecode `EEGNet` defaults; AdamW lr 1e-3, weight decay 1e-3, batch 32, cosine schedule, 150 epochs; input in µV |
| `eegnet_ea_ft` | Euclidean alignment per subject (float64, eigenvalue floor 1e-6 × max); EEGNet pre-trained per target on all source subjects (early stopping, patience 20, at most 150 epochs, 3 validation source subjects), then all layers fine-tuned on the target windows with lr from {1e-4, 3e-4} and epochs from {20, 50} |

- **Choosing the three open values** (target weight; fine-tuning lr and
  epochs), once for the whole study ([private decision log, entry 44]): pseudo-targets
  sub-01 and sub-03, session `pre`, scenario S1, task T2; the pool is run 01
  and the score is balanced accuracy on run 02 (runs 03–04 of no subject are
  touched); k ∈ {2, 5}; seeds 0–9 (EEGNet 0–4); sources as in the main study.
  The value with the highest mean balanced accuracy wins; a tie goes to the
  smaller value. Because only sub-01 and sub-03 shape these values, the
  n = 20 sensitivity analysis (§5) is free of any selection.
- `configs/models/*.yaml`, written in P06–P08, hold exactly these values; a
  difference is a deviation (§7).

<!-- confirmatory:end -->

**Methods in the calibration study (descriptive beyond the fixed pairs).**
From scratch `csp_lda`, `mdm`, `ts_lr`, `eegnet_scratch`; transfer
`pooled_tslr`, `rct_mdm`, `rct_tslr`, `eegnet_ea_ft`; in S2 also `ah_proxy`.

**Compute contingency** (pre-declared, [private risk register]): if the
EEGNet grids use more than 25 GPU hours, the EEGNet methods alone switch to
3 draws (seeds 0–2) and k ∈ {0, 2, 5, 10, all}. The confirmatory pair is
classical and unaffected; the secondary pair's ALCs then use the k of their
ALC range that were run. Triggering it is not a deviation; the date and
reason are logged in §7.

## 4. Outcomes

- **Primary:** balanced accuracy on the test windows (chance 1/3 for T2, 1/2 for T1 and T3), summarised per subject as ALC for H2a and H3.
- **RQ1b:** balanced accuracy, left vs right hand, chance 1/2.
- **Secondary:** per-k balanced accuracy; SF recall (T3 and T2); T3 SF-vs-AH confusion (share of AH test windows that a T3 decoder calls SF, for `rct_tslr`, `ts_lr` and `ah_proxy`); macro-F1, Cohen's κ, SF precision, ROC-AUC for SF; k*₆₀ and k*₇₀; trials saved; calibration minutes (S1: 2k × 14 s; S2: k × 14 s on top of the AH calibration; plus 4.7 min for a k = 0 transfer result that uses the REST set).
- **Pseudo-online (exploratory, protocol §6b):** SF and AH detection rate within the imagery period, false activations per minute during rest, detection latency; ITR (Wolpaw, T3 two-class, one selection per 14 s trial). Defined before any pseudo-online run.

## 5. Analysis plan

<!-- confirmatory:start -->

### 5.1 Confirmatory tests

All tests are Wilcoxon signed-rank tests on per-subject paired values,
`scipy.stats.wilcoxon(zero_method="wilcox", method="auto")` (SciPy as pinned
in `uv.lock`); effect size = matched-pairs rank-biserial correlation.
Population for every row: the 22 `pre` subjects (§3.1). α = 0.05. Each row
is its own multiplicity family; Holm is applied only inside the families
named in the row; there is no correction across rows.

| ID | Data | Per-subject value | Test, sidedness | Family | Supported if |
|----|------|-------------------|-----------------|--------|--------------|
| H1 | T1, `pre`, `csp_lda` | BA(`paper_replica`) − BA(`cv_leakfree`) | Wilcoxon, one-sided, difference > 0 | H1 alone | p < 0.05 |
| H1b | `BNCI2014_001`; `Cho2017`; `csp_lda`; every MOABB subject | BA(`paper_replica`) − BA(`cv_leakfree`) | Wilcoxon, one-sided, difference > 0, per dataset | the 2 datasets, Holm | adjusted p < 0.05 on both datasets |
| H2a | S1, T2, `pre` | ALC over k ∈ {1, 2, 3, 5, 10}: `rct_tslr` − `ts_lr` | Wilcoxon, two-sided | H2a alone | p < 0.05 and median difference > 0 |
| H2b | S1, T2, `pre` | [BA(`rct_tslr`) − BA(`ts_lr`)] at k = 5 minus the same at k = all | Wilcoxon, one-sided, value > 0 | H2b alone | p < 0.05 |
| H3 | S2, `pre`; outcome (a) T3, outcome (b) T2 | ALC over k ∈ {1, 2, 3, 5}: `rct_tslr` − `ts_lr` | Wilcoxon, two-sided, per outcome | outcomes (a), (b), Holm | at least one adjusted p < 0.05 with median difference > 0 |
| H3c | S2, T3, `pre`; k = 2 and k = 5 | BA(`rct_tslr`) − BA(`ah_proxy`) | Wilcoxon, one-sided, difference > 0, per k | k = 2, k = 5, Holm | adjusted p < 0.05 at both k |

Outcome categories, the same for every row:

- **Supported:** the row's rule holds.
- **Contrary** (two-sided rows only): p < 0.05 (Holm-adjusted inside H3) with
  the median difference < 0.
- **Partial:** H1b with one dataset significant; H3c with one k significant.
  Reported as such; the claim is limited to the dataset (H1b) and the k
  (H3c) that passed.
- **Mixed** (H3 only): one outcome supported and the other contrary;
  reported as such.
- **Inconclusive:** anything else. Reported with the 95 % CI, never as
  evidence of no effect.

Reported with every row: n, median and mean difference, W, exact p (and
Holm-adjusted p where a family has two members), rank-biserial r, and the
95 % percentile bootstrap CI of the mean difference (10 000 resamples of
subjects, seed 12345). For H1 and H1b the mean inflation in points with this
CI is the primary quantity.

### 5.2 Sensitivity and replication

- **Without the development subjects:** every row of §5.1 again without
  sub-01 and sub-03 (n = 20). A row whose category changes is reported.
- **Chronological draw:** H2a, H2b, H3, H3c again with the chronological
  draw in place of the mean over random draws; descriptive.
- **Replication on `post`:** every calibration row (H2a, H2b, H3, H3c) and H1
  on session `post`, n = 24, with the same tests; a second version averages
  sub-21 and sub-22 into one value (n = 23). Replicated if the category is
  the same as on `pre`.
- **Missing values:** a subject whose per-subject value cannot be computed in
  a row (a failed fit) is left out of that row only; n is reported.

<!-- confirmatory:end -->

### 5.3 Secondary and descriptive analyses

- **H2a per k:** a two-sided Wilcoxon at each of the five k, Holm across the 5.
- **H3:** SF recall of T3 and of T2, same pair, descriptive.
- **H3c:** the T3 SF-vs-AH confusion for `rct_tslr`, `ts_lr`, `ah_proxy`.
- **Secondary pair:** `eegnet_ea_ft` vs `eegnet_scratch`, the tests of H2a, H2b, H3 (5 draws), reported as secondary; no claim rests on it alone.
- **H1 context:** `loro` and `chrono` for `csp_lda`, paired descriptive Wilcoxon tests `cv_leakfree` vs `loro` and `loro` vs `chrono`; `csp_lda_replica` under all four protocols; all RQ1 methods on `post` and `follow`.
- **Power:** with n = 22, a paired Wilcoxon has about 80 % power at dz ≈ 0.62 (α = .05) and ≈ 0.68 (α = .025); smaller effects are reported as inconclusive with confidence intervals, not as absence of an effect.
- **Pseudo-online:** descriptive only, per-subject values and bootstrap CIs; values for sub-01 and sub-03 are flagged (protocol §6b, gate provenance).
- **All methods:** Friedman test and Nemenyi critical-difference diagram per scenario at k ∈ {2, 5, 10, all}, descriptive; best-of comparisons are descriptive only. A mixed-effects model is optional and exploratory.
- **Uncertainty:** group means with 95 % percentile bootstrap CIs (10 000 resamples of subjects, seed 12345).
- **Exact p-values** are always reported, never only stars.

## 6. Inference criteria and what we will say

| Result | We will say |
|--------|-------------|
| H1 supported | the published accuracy is inflated by fitting CSP before splitting; we report the size of the inflation |
| H1 inconclusive | we found no evidence that the leak inflates accuracy on this dataset; we give the CI of the inflation |
| H1b supported | fitting CSP before splitting inflates MI accuracy in general, by the reported amount per dataset |
| H1b partial / inconclusive | the inflation is not shown on every dataset; we report the size per dataset with its CI and say when it matters |
| H2a supported | re-centred transfer reduces calibration; we quantify trials and minutes saved |
| H2a inconclusive | no evidence that re-centred transfer reduces calibration here; we give the CI and discuss why (stroke heterogeneity, small n) |
| H2a / H3 contrary | from-scratch calibration beat re-centred transfer here; reported with the same prominence |
| H2b supported | the transfer advantage shrinks once the full pool is available |
| H3 supported / inconclusive | same as H2a for the novel command, naming whether detection (T3) or the three-class task (T2) carried it |
| H3c supported | the SF command carries information beyond any-imagery detection, at k = 2 and 5 |
| H3c partial / inconclusive | SF detection may be detection of any imagery; we do not claim a distinct sixth-finger command |

Negative results are reported with the same prominence as positive ones.

**Limitations declared in advance:**

- REST windows come from the fixation period between trials and may contain
  post-imagery beta rebound, so T2 and T3 accuracies are upper bounds for
  self-paced rest.
- The SF−AH ERD difference is spatially diffuse (P04), so SF decodability may
  reflect imagery intensity rather than a distinct motor map.

## 7. Deviations

Any change after the tag is logged here and in
[the evaluation protocol] §12 with date, reason and whether
it was made before or after seeing confirmatory results, and the paper lists
every one.

| Date | Change | Reason | Before/after confirmatory results |
|------|--------|--------|-----------------------------------|
| | | | |

## 8. Freeze checklist (P05 step 4.10)

Run from the repository root; each command must print what its comment says.

```sh
# 1. no open marker, no "or" and no "e.g." in the confirmatory blocks (prints nothing)
sed '/^## 8\. Freeze checklist/,$d' [this file] | grep -n "⟨decide⟩"
awk '/^<!-- confirmatory:start -->$/,/^<!-- confirmatory:end -->$/' [this file] | grep -nwE "or|TBD|e\.g\.|i\.e\."
# 2. the k grid is the same everywhere (each prints 1 or more)
grep -c "k ∈ {0, 1, 2, 3, 5, 10, all}" [this file] [the evaluation protocol]
grep -c "0, 1, 2, 3, 5, 10, all" [the spec sheet]
grep -c "k_grid: \[0, 1, 2, 3, 5, 10, 20\]" configs/protocol.yaml
# 3. draws and seeds (each prints 1 or more)
grep -c "draws_classical: 10" configs/protocol.yaml; grep -c "draws_deep: 5" configs/protocol.yaml
grep -c "seeds 0–9" [this file] [the evaluation protocol]
# 4. the calibration method list is word for word the same (each prints 1 or more)
for f in [this file] [the evaluation protocol] [the spec sheet]; do
  grep -c "\`csp_lda\`, \`mdm\`, \`ts_lr\`, \`eegnet_scratch\`" "$f"
  grep -c "\`pooled_tslr\`, \`rct_mdm\`, \`rct_tslr\`, \`eegnet_ea_ft\`" "$f"
  grep -c "\`csp_lda\`, \`csp_lda_replica\`, \`csp_svm\`, \`fbcsp_lda\`, \`mdm\`, \`ts_lr\`" "$f"
done
# 5. ALC ranges and population (each prints 1 or more)
grep -c "k ∈ {1, 2, 3, 5, 10}" [this file] [the evaluation protocol] [the spec sheet]
grep -c "k ∈ {1, 2, 3, 5}" [this file] [the evaluation protocol] [the spec sheet]
grep -c "n = 22" [this file] [the evaluation protocol]
# 6. the documents are consistent with the repository (0 errors)
[the working notes' consistency check]
```

- [x] the commands above print what their comments say (2026-10-03)
- [x] `git commit` of this file, the protocol and the configs
- [ ] `git tag -a prereg-v1 -m "..."`
