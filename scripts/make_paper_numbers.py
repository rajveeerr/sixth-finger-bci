"""Write paper/generated/numbers.tex and its index from results/summary/ and results/audit/.

uv run python scripts/make_paper_numbers.py
uv run python scripts/make_paper_numbers.py --out /tmp/numbers.tex --index /tmp/numbers-index.md

It selects and formats only. Every macro is one of three kinds, and the index says which:
a cell, one value of a results file, formatted (a share times 100, rounding, bytes to KB, a
stated difference with its sign turned where the name says so); a range, the smallest or
largest of named cells, so still a cell; a count, rows of an audit file or the total of its
count columns. Means, medians, tests and new differences are never computed here: a number
no results file states is left out, and the paper prints it as a TBD until one does.

Macro names are letters only (LaTeX forbids digits), camelCase, read left to right as
<prefix><dimensions><statistic>:

    n        dataset counts                    rqFour   RQ4: Mirror, Later (other days),
    audit    integrity audit                            Replay (pseudo-online), Switch,
    eda      data-quality views                         Cue (visual-cue check)
    rqOne    RQ1 (stroke), RQ1b (Bnci, Cho)    rqFive   RQ5, depression datasets
    dl       deep-learning baselines           exOne    transfer for AH vs SF
    rqTwo    RQ2, a new user (scenario S1)     exTwo    raw recordings, slow waves
    rqThree  RQ3, a new command (S2)           exThree  grasp pre-training, healthy benchmark
    demo     the demo model, choice, timing    exFour   the sixth finger as its own command
    runtime  fit times                         exFive   the central switch played as if live
    repo, code   repository and code DOI, filled in P15 (TBD until then)

Dimensions are the code's names in CamelCase, in this order: task (AhSf, RestAhSf, SfRest),
session, population, method (CspLda, TsLr, RctTslr, EegnetEaFt, ...), protocol
(PaperReplica, CvLeakfree, Loro, Chrono), budget (KZero, KOne, ..., KTen, KAll for the whole
pool). A dimension at its default is left out: session pre (else Post, Follow), all patients
(else NoDev without sub-01 and sub-03, Linked with sub-21 and sub-22 averaged), the random
draw (else Chrono), and in RQ1 the task AH vs SF. Follow-up arms carry the names of the
results chapter (ArmB, ArmGp, Move, Finger, ...). Classes are Rest, Ah and Sf; ERD values carry
the band and channel (Mu, Beta; CThree, Cz, CFour); one patient's value carries the patient
(SubOne), and Patient marks the extreme over patients. Statistics: Mean, Median, CiLo and CiHi
(95 % bootstrap CI), N, Diff (points unless the index says otherwise), P (two significant
digits), PHolm, W, R (rank-biserial), Better, Worse, Tied (patients), Min and Max (ranges, or
one cell where the results file states the extreme itself), NBelowChance (patients whose mean
is under the task's chance level). A test its file states as a fraction of balanced accuracy
also gets its difference in points, with Points before the statistic (\rqTwoHTwoBPointsDiff);
minutes at the recorded trial length carry Recorded (\rqTwoMinutesRecordedKAll).

Percentages print without the sign: write \\rqOneCspLdaCvLeakfreeMean\\,\\% for 58.5 %.
paper/generated/numbers-index.md lists every macro with its value, meaning and source. Macros
of this scheme that the paper or report use but this script does not make print as red TBDs
and are listed when it runs; P14's gate needs that list empty.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from sixthfinger.paths import get_paths

# EEGNet's layers as braindecode names them, and the macro suffix of each.
EEGNET_LAYERS = {
    "conv_temporal": "ConvTemporal",
    "bnorm_temporal": "BnormTemporal",
    "conv_spatial": "ConvSpatial",
    "bnorm_1": "BnormOne",
    "conv_separable_depth": "ConvSeparableDepth",
    "conv_separable_point": "ConvSeparablePoint",
    "bnorm_2": "BnormTwo",
    "final_layer.conv_classifier": "Classifier",
}
TBD = r"\newcommand{\TBD}[1]{\textcolor{red}{\textbf{TBD(#1)}}}"
TOPICS = {
    "n": "Dataset counts",
    "audit": "Integrity audit",
    "eda": "Neurophysiology and data-quality views",
    "rqOne": "RQ1 and RQ1b: leakage in the published protocol",
    "dl": "Deep-learning baselines and pre-training",
    "rqTwo": "RQ2: calibration for a new user (S1)",
    "rqThree": "RQ3: adding the sixth-finger command (S2)",
    "rqFour": "RQ4: mirroring, other days, live replay, visual cue",
    "rqFive": "RQ5: depression datasets",
    "exOne": "Follow-up 1: more data per decision for AH vs SF",
    "exTwo": "Follow-up 2: raw recordings and slow waves",
    "exThree": "Follow-up 3: grasp pre-training and the healthy benchmark",
    "exFour": "Follow-up 4: the sixth finger as its own command",
    "exFive": "Follow-up 5: the central switch played as if live",
    "demo": "The demo model",
    "runtime": "Fit times",
    "repo": "Repository (P15)",
    "code": "Code DOI (P15)",
}
OWNED = re.compile(r"\\((?:" + "|".join(TOPICS) + r")[A-Z][A-Za-z]*)")
# amssymb's negated arrows look like dataset counts.
NOT_OURS = frozenset({"nLeftarrow", "nRightarrow", "nLeftrightarrow", "nVdash", "nVDash"})
# Filled when release-v1 is published (P15); printed as TBD(P15) until then.
PENDING = {"repoURL": "P15", "repoTag": "P15", "codeDOI": "P15"}
NAME = re.compile(r"[A-Za-z]+")
MINUS = "\N{MINUS SIGN}"

TASK = {"T1_ah_vs_sf": "AhSf", "T2_rest_ah_sf": "RestAhSf", "T3_sf_vs_rest": "SfRest"}
TASK_LABEL = {
    "T1_ah_vs_sf": "AH vs SF",
    "T2_rest_ah_sf": "REST vs AH vs SF",
    "T3_sf_vs_rest": "SF vs REST",
}
METHOD = {
    "csp_lda": "CspLda",
    "csp_lda_replica": "CspLdaReplica",
    "csp_svm": "CspSvm",
    "fbcsp_lda": "FbcspLda",
    "mdm": "Mdm",
    "ts_lr": "TsLr",
    "rct_tslr": "RctTslr",
    "rct_mdm": "RctMdm",
    "pooled_tslr": "PooledTslr",
    "eegnet_scratch": "EegnetScratch",
    "eegnet_ea_ft": "EegnetEaFt",
    "ah_proxy": "AhProxy",
}
PROTOCOL = {
    "paper_replica": "PaperReplica",
    "cv_leakfree": "CvLeakfree",
    "loro": "Loro",
    "chrono": "Chrono",
}
SESSION = {"pre": "", "post": "Post", "follow": "Follow"}
POP = {"all": "", "without_dev": "NoDev", "linked_merged": "Linked", "unflagged": "Unflagged"}
POP_LABEL = {
    "all": "all patients",
    "without_dev": "without sub-01, sub-03",
    "linked_merged": "sub-21/22 averaged",
    "unflagged": "without the flagged patients",
}
GROUP = {"all": "", "B": "GroupB", "T": "GroupT"}
K = {0: "KZero", 1: "KOne", 2: "KTwo", 3: "KThree", 5: "KFive", 10: "KTen", 20: "KAll"}
K_LABEL = {k: f"k = {k}" for k in K} | {20: "k = all"}
SCENARIO = {"S1_new_user": "rqTwo", "S2_new_command": "rqThree"}
SPELL = {
    1: "One",
    5: "Five",
    10: "Ten",
    20: "Twenty",
    30: "Thirty",
    40: "Forty",
    50: "Fifty",
    60: "Sixty",
    70: "Seventy",
    80: "Eighty",
    90: "Ninety",
    100: "Hundred",
}
FIVE_METHODS = ("csp_lda", "csp_svm", "fbcsp_lda", "mdm", "ts_lr")
# The calibration methods the text quotes with intervals; the others get their means.
CALIB_MAIN = ("rct_tslr", "ts_lr", "ah_proxy", "eegnet_ea_ft", "eegnet_scratch")
CLASS_NAME = {"rest": "Rest", "affected_hand": "Ah", "sixth_finger": "Sf"}
CLASS_LABEL = {"rest": "REST", "affected_hand": "AH", "sixth_finger": "SF"}
SUBJECT = {"sub-01": "SubOne", "sub-02": "SubTwo", "sub-03": "SubThree"}


@dataclass(frozen=True)
class Value:
    tex: str
    plain: str


@dataclass(frozen=True)
class Entry:
    tex: str
    plain: str
    meaning: str
    source: str
    kind: str


def _missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _signed(text: str) -> Value:
    if text.startswith("-"):
        return Value(rf"\ensuremath{{-{text[1:]}}}", MINUS + text[1:])
    return Value(text, text)


def fixed(x, digits: int = 1) -> Value | None:
    return None if _missing(x) else _signed(f"{float(x):.{digits}f}")


def fixed2(x) -> Value | None:
    return fixed(x, 2)


def fixed3(x) -> Value | None:
    return fixed(x, 3)


def pct(x, digits: int = 1) -> Value | None:
    return None if _missing(x) else fixed(100 * float(x), digits)


def integer(x) -> Value | None:
    if _missing(x):
        return None
    if float(x) != int(x):
        raise SystemExit(f"{x} is not a whole number")
    if abs(int(x)) < 10_000:
        return _signed(str(int(x)))
    # Five digits and more are grouped in threes, as the text writes 35 778.
    grouped = f"{int(x):,}"
    return Value(grouped.replace(",", r"\,"), grouped.replace(",", " "))


def whole_or(x) -> Value | None:
    """W statistics and medians of counts: whole when they are, else one decimal."""
    if _missing(x):
        return None
    return integer(x) if float(x) == int(x) else fixed(x)


def sig(x, digits: int = 2) -> Value | None:
    """Two significant digits, below 0.001 as a power of ten (p-values, tiny differences)."""
    if _missing(x):
        return None
    x = float(x)
    if x != 0 and abs(x) < 1e-3:
        mantissa, exponent = f"{x:.{digits - 1}e}".split("e")
        power = int(exponent)
        return Value(rf"\ensuremath{{{mantissa}\times10^{{{power}}}}}", f"{mantissa} × 10^{power}")
    return _signed(f"{x:#.{digits}g}".rstrip("."))


def seconds(x) -> Value | None:
    """Fit times: two significant digits, never as a power of ten."""
    if _missing(x):
        return None
    decimals = max(0, 1 - math.floor(math.log10(abs(float(x)))))
    return fixed(x, decimals)


def general(x) -> Value | None:
    return None if _missing(x) else _signed(f"{float(x):g}")


def word(text: str) -> Value:
    return Value(str(text).replace("_", r"\_"), str(text))


def one(df: pd.DataFrame, **where) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for column, value in where.items():
        mask &= df[column] == value
    rows = df[mask]
    if len(rows) != 1:
        raise SystemExit(f"expected exactly one row for {where}, got {len(rows)}")
    return rows.iloc[0]


def single(values: pd.Series):
    """The one value a column holds in every row (e.g. every run's sampling rate)."""
    distinct = pd.unique(values.dropna())
    if len(distinct) != 1:
        raise SystemExit(f"expected one value in {values.name}, got {list(distinct)}")
    return distinct[0]


class Numbers:
    """The macros, in the order they are made, each with its value, meaning and source."""

    def __init__(self, root: Path):
        self.root = root
        self.entries: dict[str, Entry] = {}
        self._files: dict[str, object] = {}

    def csv(self, name: str) -> pd.DataFrame:
        if name not in self._files:
            self._files[name] = pd.read_csv(self.root / "results" / name)
        return self._files[name]

    def json(self, name: str):
        if name not in self._files:
            self._files[name] = json.loads((self.root / "results" / name).read_text())
        return self._files[name]

    def text(self, name: str) -> str:
        if name not in self._files:
            self._files[name] = (self.root / "results" / name).read_text()
        return self._files[name]

    def add(
        self,
        name: str,
        value: Value | None,
        source: str,
        meaning: str,
        kind: str = "cell",
        optional: bool = False,
    ) -> None:
        if value is None:
            if optional:
                return
            raise SystemExit(f"\\{name}: {source} has no value for {meaning}")
        if not NAME.fullmatch(name) or not OWNED.fullmatch("\\" + name):
            raise SystemExit(f"\\{name} does not follow this script's naming scheme")
        if name in self.entries:
            raise SystemExit(f"\\{name} is generated twice")
        self.entries[name] = Entry(value.tex, value.plain, meaning, source, kind)

    def mean_ci(self, stem, row, src, what, fmt=pct, unit="%", ci=True) -> None:
        self.add(stem + "Mean", fmt(row["mean"]), src, f"{what} ({unit})")
        if ci:
            self.add(stem + "CiLo", fmt(row.ci_lo), src, "CI lower", optional=True)
            self.add(stem + "CiHi", fmt(row.ci_hi), src, "CI upper", optional=True)

    def span(self, stem, values: pd.Series, src, what, fmt=pct) -> None:
        self.add(stem + "Min", fmt(values.min()), src, f"{what}: smallest", "range")
        self.add(stem + "Max", fmt(values.max()), src, "largest", "range")

    def test(
        self,
        stem: str,
        row: pd.Series,
        src: str,
        what: str,
        *,
        fmt: Callable = fixed,
        unit: str = "points",
        sign: int = 1,
        full: bool = True,
    ) -> None:
        """A paired test as its file states it; sign=-1 names the comparison the other way.

        full=False keeps the difference, its CI and the p-values (descriptive tests)."""
        lo, hi = (row.ci_lo, row.ci_hi) if sign > 0 else (row.ci_hi, row.ci_lo)
        diff = sign * row.mean_diff
        self.add(stem + "Diff", fmt(diff), src, f"{what}: mean difference ({unit})")
        self.add(stem + "DiffCiLo", fmt(sign * lo), src, "CI lower", optional=True)
        self.add(stem + "DiffCiHi", fmt(sign * hi), src, "CI upper", optional=True)
        self.add(stem + "P", sig(row.p), src, "p", optional=True)
        if "p_holm" in row:
            self.add(stem + "PHolm", sig(row.p_holm), src, "Holm-adjusted p", optional=True)
        if "category" in row and isinstance(row.category, str):
            self.add(stem + "Category", word(row.category), src, "category")
        if not full:
            return
        median = fmt(sign * row.median_diff)
        self.add(stem + "MedianDiff", median, src, f"median difference ({unit})")
        self.add(stem + "W", whole_or(row.W), src, "Wilcoxon W", optional=True)
        self.add(stem + "R", fixed2(sign * row.r_rb), src, "rank-biserial r")
        self.add(stem + "N", integer(row.n), src, "patients")
        if "n_nonzero" in row:
            nonzero = integer(row.n_nonzero)
            self.add(stem + "NNonzero", nonzero, src, "patients with a non-zero difference")
        if "min_diff" in row:
            low, high = (row.min_diff, row.max_diff) if sign > 0 else (-row.max_diff, -row.min_diff)
            self.add(stem + "DiffMin", fmt(low), src, f"smallest per-patient difference ({unit})")
            self.add(stem + "DiffMax", fmt(high), src, f"largest per-patient difference ({unit})")
            up, down = (row.n_positive, row.n_negative)[:: 1 if sign > 0 else -1]
            self.add(stem + "Positive", integer(up), src, "patients with a positive difference")
            self.add(stem + "Negative", integer(down), src, "patients with a negative difference")

    def paired(self, stem, row, src, what, means=True, nodev=True) -> None:
        """A row of the follow-ups' paired files (ex1, ex3, ex4): arm, baseline, difference."""
        if means:
            self.add(stem + "ArmMean", pct(row.arm_mean), src, f"{what}: the arm (%)")
            self.add(stem + "ArmCiLo", pct(row.arm_ci_lo), src, "the arm, CI lower")
            self.add(stem + "ArmCiHi", pct(row.arm_ci_hi), src, "the arm, CI upper")
            self.add(stem + "BaseMean", pct(row.base_mean), src, "the baseline (%)")
            what = "arm minus baseline"
        self.add(stem + "Diff", fixed(row.diff_points), src, f"{what}: difference (points)")
        self.add(stem + "DiffCiLo", fixed(row.diff_ci_lo), src, "CI lower")
        self.add(stem + "DiffCiHi", fixed(row.diff_ci_hi), src, "CI upper")
        self.add(stem + "P", sig(row.p_wilcoxon), src, "two-sided Wilcoxon p")
        self.add(stem + "N", integer(row.n), src, "patients")
        for column in ("better", "worse", "tied"):
            self.add(stem + column.capitalize(), integer(row[column]), src, f"patients {column}")
        if not nodev:
            return
        nodev_diff = fixed(row.diff_points_without_dev)
        self.add(stem + "DiffNoDev", nodev_diff, src, "difference without sub-01, sub-03")
        self.add(stem + "DiffNoDevCiLo", fixed(row.diff_ci_lo_without_dev), src, "CI lower")
        self.add(stem + "DiffNoDevCiHi", fixed(row.diff_ci_hi_without_dev), src, "CI upper")


def dataset(nums: Numbers) -> None:
    src = "audit/inventory.csv"
    inventory = nums.csv(src)
    sessions = len(inventory[["subject", "session"]].drop_duplicates())
    nums.add("nSubjects", integer(inventory.subject.nunique()), src, "patients", "count")
    nums.add("nRuns", integer(len(inventory)), src, "preprocessed runs", "count")
    nums.add("nSessions", integer(sessions), src, "recording sessions", "count")
    nums.add("nChannelsFile", integer(single(inventory.n_channels)), src, "channels in every file")
    nums.add("nSamplingRate", integer(single(inventory.sfreq)), src, "sampling rate (Hz)")

    src = "audit/audit_report.md"
    report = " ".join(nums.text(src).split())
    kept = re.search(
        r"After exclusions: (\d+) of (\d+) runs, (\d+) of (\d+) sessions, (\d+) subjects with a "
        r"pre session; (\d+) rest, (\d+) affected-hand and (\d+) sixth-finger events",
        report,
    )
    if kept is None or (int(kept[2]), int(kept[4])) != (len(inventory), sessions):
        raise SystemExit(f"{src} no longer states the data after exclusions as expected")
    runs, _, kept_sessions, _, pre, rest, hand, finger = (int(x) for x in kept.groups())
    nums.add("nRunsKept", integer(runs), src, "runs after the exclusions")
    nums.add("nSessionsKept", integer(kept_sessions), src, "sessions after the exclusions")
    nums.add("nEventsRest", integer(rest), src, "rest markers in the kept runs")
    nums.add("nEventsHand", integer(hand), src, "affected-hand cues in the kept runs")
    nums.add("nEventsFinger", integer(finger), src, "sixth-finger cues in the kept runs")
    events = rest + hand + finger
    nums.add("nEvents", integer(events), src, "markers in the kept runs", "count")

    src = "audit/epoch_counts.csv"
    counts = nums.csv(src)
    classes = {"rest": "Rest", "affected_hand": "Hand", "sixth_finger": "Finger"}
    class_label = {"rest": "rest", "affected_hand": "AH", "sixth_finger": "SF"}
    per_file = counts[list(classes)].sum(axis=1)
    for session, token in (("all", ""), ("pre", "Pre"), ("post", "Post"), ("follow", "Follow")):
        part = counts if session == "all" else counts[counts.session == session]
        label = "all sessions" if session == "all" else session
        total = per_file[part.index]
        nums.add(f"nWindows{token}", integer(total.sum()), src, f"windows, {label}", "count")
        for column, cls in classes.items():
            count = integer(part[column].sum())
            what = f"{class_label[column]} windows, {label}"
            nums.add(f"nWindows{token}{cls}", count, src, what, "count")
        files = integer(len(part))
        nums.add(f"nWindowFiles{token}", files, src, f"window files, {label}", "count")
        nums.span(f"nWindowsPerFile{token}", total, src, f"windows per file, {label}", integer)

    src = "audit/epoch_drops.csv"
    by_reason = nums.csv(src).groupby("reason").windows.sum()
    dropped = int(by_reason.sum())
    if int(per_file.sum()) + dropped != events:
        raise SystemExit("kept and dropped windows no longer add up to the markers")
    nums.add("nWindowsDropped", integer(dropped), src, "windows dropped", "count")
    share = pct(dropped / events)
    nums.add("nWindowsDroppedPct", share, src, "windows dropped, % of the markers", "count")
    inside = integer(by_reason["boundary_inside"])
    nums.add("nWindowsDroppedBoundary", inside, src, "dropped: a cut inside the window", "count")
    end = integer(by_reason["past_end"])
    nums.add("nWindowsDroppedEnd", end, src, "dropped: past the run's end", "count")

    src = "summary/rq1_replica_check.csv"
    groups = nums.csv(src)
    for _, row in groups[groups.method == "csp_lda"].iterrows():
        who = "all patients" if row.group == "all" else f"group {row.group}"
        what = f"patients with a usable {row.session} session, {who}"
        nums.add(f"n{row.session.capitalize()}{GROUP[row.group]}", integer(row.n), src, what)
    if nums.entries["nPre"].plain != str(pre):
        raise SystemExit("the audit report and the RQ1 analyses disagree on the pre patients")

    # The public copy of the deviation log, whose dated rows the paper counts.
    src = "../docs/preregistration/deviations.md"
    log = (nums.root / "docs" / "preregistration" / "deviations.md").read_text().splitlines()
    rows = integer(sum(re.match(r"\| \d{4}-\d{2}-\d{2} \|", line) is not None for line in log))
    nums.add("nDeviations", rows, src, "dated entries of the deviation log", "count")

    src = "audit/epoch_trials.csv"
    trials = nums.csv(src)
    if int(trials.trials.sum()) != int(per_file.sum()) - int(
        trials[["rest_and_affected_hand", "rest_and_sixth_finger"]].to_numpy().sum()
    ):
        raise SystemExit(f"{src} no longer adds up to the windows")
    nums.add("nTrials", integer(trials.trials.sum()), src, "trials the windows form", "count")
    for column, token, label in (
        ("rest_and_affected_hand", "RestAh", "a rest and an AH window"),
        ("rest_and_sixth_finger", "RestSf", "a rest and an SF window"),
        ("rest_only", "RestOnly", "only a rest window"),
        ("affected_hand_only", "AhOnly", "only an AH window"),
        ("sixth_finger_only", "SfOnly", "only an SF window"),
    ):
        nums.add(
            f"nTrials{token}", integer(trials[column].sum()), src, f"trials with {label}", "count"
        )


def audit(nums: Numbers) -> None:
    src = "audit/audit_report.md"
    report = " ".join(nums.text(src).split())
    pairs = re.search(r"Screened (\d+) pairs; (\d+) re-scored on every segment, (\d+) of", report)
    if pairs is None:
        raise SystemExit(f"{src} no longer states the screened pairs")
    nums.add("auditPairsScreened", integer(pairs[1]), src, "pairs of runs screened")

    src = "audit/near_duplicates.csv"
    near = nums.csv(src)
    if (len(near), int(near.forced.sum())) != (int(pairs[2]), int(pairs[3])):
        raise SystemExit(f"{src} disagrees with the audit report")
    nums.add("auditPairsRescored", integer(len(near)), src, "pairs re-scored", "count")
    nums.add(
        "auditPairsShared", integer(near.forced.sum()), src, "pairs sharing a recording", "count"
    )
    r = near.segment_median_r
    copy = r[near.run_a.str.startswith("sub-02_")]
    nums.span("auditFollowCopyCorr", copy, src, "sub-02 post vs follow, segment median r", fixed3)
    shared = r[near.run_a.str.startswith("sub-21_")]
    nums.span("auditSharedPreCorr", shared, src, "sub-21 vs sub-22 pre, segment median r", fixed3)
    nums.add(
        "auditIndependentPairs",
        integer((~near.forced).sum()),
        src,
        "pairs found independent",
        "count",
    )
    nums.span(
        "auditIndependentCorr", r[~near.forced], src, "independent pairs, segment median r", fixed3
    )

    src = "audit/raw_crc_duplicates.csv"
    groups = integer(len(nums.csv(src)))
    nums.add("auditRawDuplicateGroups", groups, src, "groups of byte-identical raw files", "count")

    src = "audit/event_flags.csv"
    flags = nums.csv(src)
    fewer = integer((flags.flag == "count").sum())
    nums.add("auditFewerEventsRuns", fewer, src, "runs with fewer events than 20/10/10", "count")
    degenerate = integer((flags.flag == "degenerate").sum())
    nums.add("auditDegenerateRuns", degenerate, src, "degenerate runs", "count")
    bad = one(flags, flag="degenerate")
    what = f"{bad.subject} {bad.session} run {bad.run}"
    nums.add("auditDegenerateSeconds", fixed2(bad.duration_s), src, f"{what}: length (s)")
    nums.add("auditDegenerateRestMarkers", integer(bad.n_rest), src, f"{what}: rest markers")
    src = "audit/inventory.csv"
    flat = integer(nums.csv(src).flat_channels.sum())
    nums.add("auditFlatChannels", flat, src, "flat channels in all runs", "count")

    src = "audit/calib_sanity_refit.csv"
    refit = nums.csv(src)
    both = (refit.s1_reproduces_p08 & refit.pool_reproduces_p06).sum()
    nums.add(
        "auditRefitCases", integer(len(refit)), src, "P08 sanity check: cases refitted", "count"
    )
    nums.add("auditRefitReproduced", integer(both), src, "refits reproducing P08 and P06", "count")
    nums.span("auditOrphanRest", refit.n_orphan_rest, src, "orphan rest windows a session", integer)

    src = "summary/eda_quality_flags.csv"
    quality = nums.csv(src)
    row = one(quality, kind="c3_window_outliers")
    what = f"{row.subject}: outlying C3 windows ({row.note})"
    nums.add("edaOutlierWindows", integer(row.value), src, what)
    row = one(quality, kind="channel_std")
    what = f"{row.subject} {row['item']}: {row.note}"
    nums.add("edaChannelStdRatio", fixed2(row.value), src, what)


def erd(nums: Numbers) -> None:
    src = "summary/eda_erd_summary.csv"
    channel_tok = {"C3": "CThree", "Cz": "Cz", "C4": "CFour"}
    for _, row in nums.csv(src).query("session == 'pre'").iterrows():
        stem = f"edaErd{row.band.capitalize()}{channel_tok[row.channel]}"
        what = f"{row.band} ERD at {row.channel} (mirrored), pre, 1-5 s"
        nums.add(stem + "AhMean", fixed(row.mean_affected_hand), src, f"{what}: AH, mean (%)")
        nums.add(stem + "SfMean", fixed(row.mean_sixth_finger), src, "SF, mean (%)")
        nums.add(
            stem + "AhNegative",
            integer(row.n_negative_affected_hand),
            src,
            "patients with AH ERD below 0",
        )
        nums.add(
            stem + "SfNegative",
            integer(row.n_negative_sixth_finger),
            src,
            "patients with SF ERD below 0",
        )
        nums.add(stem + "N", integer(row.n_paired), src, "patients with both")
        nums.add(
            stem + "SfMoreNegative",
            integer(row.n_sf_more_negative),
            src,
            "patients whose SF ERD is the more negative",
        )
        diff = f"{what}: SF minus AH, exploratory two-sided Wilcoxon"
        nums.add(stem + "SfMinusAhDiff", fixed(row.sf_minus_ah_mean), src, f"{diff} (points)")
        nums.add(stem + "SfMinusAhDiffCiLo", fixed(row.sf_minus_ah_ci_lo), src, "CI lower")
        nums.add(stem + "SfMinusAhDiffCiHi", fixed(row.sf_minus_ah_ci_hi), src, "CI upper")
        nums.add(stem + "SfMinusAhW", whole_or(row.W), src, "Wilcoxon W")
        nums.add(stem + "SfMinusAhP", sig(row.p), src, "p")


def rq_one(nums: Numbers) -> None:
    src = "summary/rq1_table.csv"
    table = nums.csv(src)
    task_tok = {k: ("" if k == "T1_ah_vs_sf" else v) for k, v in TASK.items()}
    for _, row in table.iterrows():
        # The context tasks are quoted for pre only; sensitivity populations by their means.
        main = row.population == "all" and (row.task == "T1_ah_vs_sf" or row.session == "pre")
        sensitivity = row.task == "T1_ah_vs_sf" and row.population != "all"
        if pd.isna(row["mean"]) or not (main or sensitivity):
            continue
        stem = "rqOne" + task_tok[row.task] + SESSION[row.session] + POP[row.population]
        stem += METHOD[row.method] + PROTOCOL[row.protocol]
        what = (
            f"{TASK_LABEL[row.task]}, {row.session}, {POP_LABEL[row.population]}, "
            f"{row.method}, {row.protocol}: balanced accuracy"
        )
        nums.mean_ci(stem, row, src, what, ci=main)
        above = integer(row.n_above_chance)
        nums.add(stem + "NAbove", above, src, "patients above chance", optional=True)
        if main:
            nums.add(stem + "Min", pct(row.min_bal_acc), src, "lowest patient (%)")
            nums.add(stem + "Max", pct(row.max_bal_acc), src, "highest patient (%)")
            below = integer(row.n_below_chance_level)
            nums.add(stem + "NBelowChance", below, src, "patients below the chance level")
    for (task, session, population), part in table.groupby(["task", "session", "population"]):
        name = "rqOne" + task_tok[task] + SESSION[session] + POP[population] + "N"
        what = f"{TASK_LABEL[task]}, {session}, {POP_LABEL[population]}: patients"
        if task == "T1_ah_vs_sf" or (session == "pre" and population == "all"):
            nums.add(name, integer(single(part.n)), src, what)

    pre = table[(table.session == "pre") & (table.population == "all")]
    classical = pre[pre.method.isin(FIVE_METHODS)]
    for task, token in task_tok.items():
        for protocols, label in (
            (["cv_leakfree"], "CvLeakfree"),
            (["loro"], "Loro"),
            (["chrono"], "Chrono"),
            (["loro", "chrono"], "HeldOutRuns"),
        ):
            part = classical[(classical.task == task) & classical.protocol.isin(protocols)]
            if part.empty:
                continue
            what = f"{TASK_LABEL[task]}, pre, {' or '.join(protocols)}, five classical methods"
            nums.span(f"rqOne{token}{label}Mean", part["mean"], src, f"{what}: mean (%)")
            nums.span(f"rqOne{token}{label}Median", part["median"], src, f"{what}: median (%)")
    recipe = pre[(pre.method == "csp_lda_replica") & (pre.protocol != "paper_replica")]
    what = "authors' recipe, AH vs SF, pre, the three leak-free protocols: mean (%)"
    nums.span("rqOneCspLdaReplicaFairMean", recipe["mean"], src, what)

    src = "summary/rq1_stats.csv"
    stats = nums.csv(src)
    for test_id, token in (
        ("H1", ""),
        ("H1_without_dev", "NoDev"),
        ("H1_post_all", "Post"),
        ("H1_post_linked_merged", "PostLinked"),
        ("H1_follow", "Follow"),
    ):
        row = one(stats, test_id=test_id)
        what = f"{test_id}, CSP+LDA, AH vs SF, paper_replica minus cv_leakfree"
        nums.test(f"rqOneHOne{token}", row, src, what)
    comparisons = {
        "paper_replica - cv_leakfree": ("Leak", 1),
        "cv_leakfree - loro": ("LoroMinusCvLeakfree", -1),
        "loro - chrono": ("LoroMinusChrono", 1),
    }
    descriptive = stats[(stats.test_id == "descriptive") & (stats.session == "pre")]
    for _, row in descriptive.iterrows():
        token, sign = comparisons[row.comparison]
        shown = row.comparison if sign > 0 else "loro - cv_leakfree"
        what = f"{row.method}, AH vs SF, pre, {shown} (descriptive, Holm over 18)"
        nums.test("rqOne" + METHOD[row.method] + token, row, src, what, sign=sign, full=False)
    src = "summary/rq1_runwise_gap.csv"
    gaps = nums.csv(src)
    for _, row in gaps[
        (gaps.session == "pre") & (gaps.comparison != "paper_replica - cv_leakfree")
    ].iterrows():
        split = row.comparison.split(" - ")[1]
        stem = f"rqOneCspLdaPaperReplicaMinus{PROTOCOL[split]}"
        what = f"csp_lda, AH vs SF, pre, paper_replica minus {split} (descriptive, no test)"
        nums.add(stem + "Diff", fixed(row["mean"]), src, f"{what}: mean difference (points)")
        nums.add(stem + "DiffCiLo", fixed(row.ci_lo), src, "CI lower")
        nums.add(stem + "DiffCiHi", fixed(row.ci_hi), src, "CI upper")
        nums.add(
            stem + "Negative", integer(row.n_negative), src, "patients with a negative difference"
        )
    csp = ["csp_lda", "csp_lda_replica", "csp_svm", "fbcsp_lda"]
    leak = descriptive[
        descriptive.method.isin(csp) & (descriptive.comparison.str.startswith("paper"))
    ]
    nums.span("rqOneLeakCspPHolm", leak.p_holm, src, "leak of the four CSP methods: Holm p", sig)

    # The development patients, whose CSP patterns the results chapter shows.
    src = "summary/rq1_subject_values.csv"
    values = nums.csv(src)
    for subject, token in (("sub-01", "SubOne"), ("sub-03", "SubThree")):
        for protocol, label in PROTOCOL.items():
            cell = one(
                values,
                subject=subject,
                task="T1_ah_vs_sf",
                method="csp_lda",
                feature="bandpower",
                protocol=protocol,
                session="pre",
            )
            what = f"{subject}, AH vs SF, pre, csp_lda, {protocol}: balanced accuracy (%)"
            nums.add(f"rqOne{token}CspLda{label}", pct(cell.bal_acc), src, what)

    src = "summary/rq1_replica_check.csv"
    check = nums.csv(src)
    for _, row in check.iterrows():
        stem = "rqOne" + SESSION[row.session] + METHOD[row.method] + GROUP[row.group]
        what = f"{row.method}, paper_replica, {row.session}, group {row.group}"
        nums.add(stem + "Acc", fixed(row.mean_acc_pct), src, f"{what}: plain accuracy (%)")
        if row.group != "all":
            balanced = fixed(row.mean_bal_acc_pct)
            nums.add(stem + "BalAcc", balanced, src, f"{what}: balanced accuracy (%)")
    for (session, group), part in check[check.group != "all"].groupby(["session", "group"]):
        for column, method in (
            ("published_csp_lda_acc_pct", "CspLda"),
            ("published_csp_svm_acc_pct", "CspSvm"),
        ):
            name = f"rqOnePublished{SESSION[session]}{GROUP[group]}{method}"
            what = f"dataset paper's {method} accuracy, {session}, group {group} (%)"
            nums.add(name, fixed2(single(part[column])), src, what)

    src = "summary/rq1_runtime.csv"
    runtime = nums.csv(src)
    for experiment, name in (("rq1_benchmark", "rqOneFits"), ("rq1_context", "rqOneContextFits")):
        fits = runtime[runtime.experiment == experiment].n_fits.sum()
        nums.add(name, integer(fits), src, f"{experiment}: fold results", "count")
    for _, row in runtime[runtime.experiment == "rq1_benchmark"].iterrows():
        stem = "runtime" + METHOD[row.method] + PROTOCOL[row.protocol]
        what = f"RQ1 {row.method}, {row.protocol}"
        nums.add(stem + "FitSeconds", seconds(row.mean_fit_seconds), src, f"{what}: s per fit")
        nums.add(stem + "Fits", integer(row.n_fits), src, f"{what}: fits")


def rq_one_b(nums: Numbers) -> None:
    dataset_tok = {"BNCI2014_001": "Bnci", "Cho2017": "Cho"}
    src = "summary/rq1b_table.csv"
    for _, row in nums.csv(src).iterrows():
        # Cho2017's leave-run-out and chronological splits hold one class per block.
        if row.dataset == "Cho2017" and row.protocol in ("loro", "chrono"):
            continue
        stem = "rqOne" + dataset_tok[row.dataset] + PROTOCOL[row.protocol]
        what = f"{row.dataset}, CSP+LDA, {row.protocol}"
        nums.mean_ci(stem, row, src, f"{what}: balanced accuracy")
        nums.add(stem + "N", integer(row.n), src, "participants")
        nums.add(stem + "Sessions", integer(row.n_sessions), src, "sessions")
        above = integer(row.n_sessions_above_chance)
        nums.add(stem + "SessionsAbove", above, src, "sessions above chance")
    src = "summary/rq1b_stats.csv"
    stats = nums.csv(src)
    for _, row in stats[stats.test_id == "H1b"].iterrows():
        what = f"H1b, {row.dataset}, paper_replica minus cv_leakfree"
        nums.test(f"rqOne{dataset_tok[row.dataset]}HOneB", row, src, what)
    bnci = stats[(stats.test_id == "descriptive") & (stats.dataset == "BNCI2014_001")]
    for _, row in bnci.iterrows():
        token, sign = {
            "cv_leakfree - loro": ("LoroMinusCvLeakfree", -1),
            "loro - chrono": ("LoroMinusChrono", 1),
        }[row.comparison]
        what = f"BNCI2014_001, {token} (descriptive)"
        nums.test(f"rqOneBnci{token}", row, src, what, sign=sign, full=False)
    src = "summary/rq1b_download_sizes.csv"
    for _, row in nums.csv(src).iterrows():
        stem = "rqOne" + dataset_tok[row.dataset]
        nums.add(stem + "Files", integer(row.n_files), src, f"{row.dataset}: files")
        nums.add(stem + "DownloadGb", fixed(row.download_gb), src, f"{row.dataset}: download (GB)")
    src = "summary/rq1b_subject_values.csv"
    for name, part in nums.csv(src).groupby("dataset"):
        fits = integer(part.n_fits.sum())
        nums.add(f"rqOne{dataset_tok[name]}Fits", fits, src, f"{name}: fold results", "count")


def deep(nums: Numbers) -> None:
    src = "summary/dl_baselines_table.csv"
    table = nums.csv(src)
    for _, row in table.iterrows():
        stem = "dl" + TASK[row.task] + PROTOCOL[row.protocol]
        what = f"{TASK_LABEL[row.task]}, pre, {row.protocol}, {row.method}: balanced accuracy"
        nums.mean_ci(stem + METHOD[row.method], row, src, what)
        if row.method == "eegnet_scratch":
            spread = pct(row.mean_seed_sd)
            nums.add(stem + "EegnetScratchSeedSd", spread, src, "mean SD over seeds (points)")
            continue
        vs = f"{stem}EegnetScratchVs{METHOD[row.method]}"
        what = f"{TASK_LABEL[row.task]}, {row.protocol}, eegnet_scratch minus {row.method}"
        nums.add(vs + "Diff", fixed(row.eegnet_minus_points), src, f"{what}: difference (points)")
        nums.add(vs + "DiffCiLo", fixed(row.diff_ci_lo_points), src, "CI lower")
        nums.add(vs + "DiffCiHi", fixed(row.diff_ci_hi_points), src, "CI upper")
        nums.add(vs + "P", sig(row.paired_p_two_sided), src, "two-sided Wilcoxon p")
    nums.add("dlN", integer(single(table.n)), src, "patients in the deep-learning baselines")

    src = "summary/eegnet_weights.json"
    weights = nums.json(src)["study_model"]
    what = "EEGNet as the study builds it (40 channels, 3 classes, 4 s): trainable weights"
    nums.add("dlEegnetWeights", integer(weights["trainable"]), src, what)
    for layer, name in EEGNET_LAYERS.items():
        what = f"EEGNet as the study builds it: trainable weights of {layer}"
        nums.add("dlEegnetWeights" + name, integer(weights["per_layer"][layer]), src, what)

    src = "summary/dl_zeroshot_table.csv"
    for _, row in nums.csv(src).iterrows():
        what = f"zero-shot EEGNet, {TASK_LABEL[row.task]}, runs 03-04: balanced accuracy"
        nums.mean_ci("dlZeroShot" + TASK[row.task], row, src, what)
    src = "summary/dl_zeroshot_paired.csv"
    for _, row in nums.csv(src).iterrows():
        stem = f"dlZeroShot{TASK[row.task]}Vs{METHOD[row.versus]}"
        what = f"{TASK_LABEL[row.task]}, zero-shot minus {row.versus} ({row.protocol})"
        diff = fixed(row.zero_shot_minus_points)
        nums.add(stem + "Diff", diff, src, f"{what}: difference (points)")
        nums.add(stem + "DiffCiLo", fixed(row.diff_ci_lo_points), src, "CI lower")
        nums.add(stem + "DiffCiHi", fixed(row.diff_ci_hi_points), src, "CI upper")
        nums.add(stem + "P", sig(row.paired_p_two_sided), src, "two-sided Wilcoxon p")
    src = "summary/dl_zeroshot_subject_values.csv"
    reference = nums.csv(src).n_reference
    what = "rest windows a zero-shot model is aligned with, per patient"
    nums.span("dlZeroShotReferenceWindows", reference, src, what, integer)

    src = "summary/dl_pretrain_table.csv"
    pretrain = nums.csv(src)
    nums.add("dlPretrainModels", integer(len(pretrain)), src, "pre-trained models", "count")
    for column, token, fmt, label in (
        ("n_train_windows", "Windows", integer, "training windows"),
        ("n_valid_windows", "ValidWindows", integer, "validation windows"),
        ("epochs_run", "Epochs", integer, "epochs before early stopping"),
        ("best_epoch", "BestEpoch", integer, "epoch whose weights were kept"),
        ("best_valid_loss", "Loss", fixed3, "best validation loss"),
        ("seconds", "Seconds", fixed, "training seconds"),
    ):
        nums.span(f"dlPretrain{token}", pretrain[column], src, f"pre-training, {label}", fmt)
    src = "audit/pretrain_manifest.json"
    manifest = nums.json(src)
    sources = pd.Series([len(manifest[f]["train_subjects"]) for f in pretrain.file])
    nums.span("dlPretrainSources", sources, src, "source patients of a pre-trained model", integer)

    src = "summary/dl_summary.json"
    group = nums.json(src)
    seeds = group["seed SD per patient, task and protocol (points)"]
    what = "EEGNet on one patient: SD over 3 seeds, every patient, task and protocol (points)"
    nums.add("dlEegnetScratchSeedSdMean", fixed(seeds["mean"]), src, f"{what}, mean")
    nums.add("dlEegnetScratchSeedSdMedian", fixed(seeds["median"]), src, "median")
    nums.add("dlEegnetScratchSeedSdMax", fixed(seeds["max"]), src, "largest")
    nums.add("dlEegnetScratchSeedSdN", integer(seeds["rows"]), src, "patient, task and protocol")
    pre = group["pre-training"]
    minutes = fixed(pre["training minutes, sum over the models"])
    nums.add("dlPretrainMinutes", minutes, src, "pre-training: minutes, sum over the 24 models")
    job = fixed(pre["job minutes (Kaggle job, wall clock)"])
    nums.add("dlPretrainJobMinutes", job, src, "pre-training: the Kaggle job's wall-clock minutes")
    median = fixed(pre["training seconds per model, median"])
    nums.add("dlPretrainSecondsMedian", median, src, "pre-training: seconds per model, median")
    epoch = whole_or(pre["best epoch, median"])
    nums.add("dlPretrainBestEpochMedian", epoch, src, "pre-training: best epoch, median")
    device = word(pre["device name (Kaggle job)"])
    nums.add("dlPretrainDevice", device, src, "pre-training: the GPU (Kaggle job record)")
    reference = group["zero-shot alignment, rest windows per patient"]
    what = "rest windows a zero-shot model is aligned with, median over patients"
    nums.add("dlZeroShotReferenceWindowsMedian", whole_or(reference["median"]), src, what)

    src = "summary/dl_class_recall.csv"
    recall = nums.csv(src)
    for _, row in recall.iterrows():
        stem = "dl" + TASK[row.task] + PROTOCOL[row.protocol] + METHOD[row.method]
        what = (
            f"{TASK_LABEL[row.task]}, pre, {row.protocol}, {row.method}: "
            f"recall of {CLASS_LABEL[row['class']]} (%)"
        )
        nums.add(f"{stem}Recall{CLASS_NAME[row['class']]}", pct(row.mean_recall), src, what)
    classical = recall[recall.method != "eegnet_scratch"]
    for (task, protocol, cls), part in classical.groupby(["task", "protocol", "class"]):
        stem = f"dl{TASK[task]}{PROTOCOL[protocol]}ClassicalRecall{CLASS_NAME[cls]}"
        what = f"{TASK_LABEL[task]}, pre, {protocol}, five classical methods: {cls} recall (%)"
        nums.span(stem, part.mean_recall, src, what)


def calibration(nums: Numbers) -> None:
    src = "summary/calib_curves.csv"
    curves = nums.csv(src)
    rows = curves[(curves.population == "all") & curves["mean"].notna()]
    rows = rows.sort_values("session", key=lambda s: s != "pre", kind="stable")
    for _, row in rows.iterrows():
        # The own-hand control ignores the budget: one value per task and session.
        if row.method == "ah_proxy" and row.k != 0:
            continue
        budget = "" if row.method == "ah_proxy" else K[row.k]
        stem = SCENARIO[row.scenario] + TASK[row.task] + SESSION[row.session]
        stem += METHOD[row.method] + budget
        when = "" if row.method == "ah_proxy" else f", {K_LABEL[row.k]}"
        what = f"{row.scenario}, {TASK_LABEL[row.task]}, {row.session}, {row.method}{when}"
        ci = row.session == "pre" and row.method in CALIB_MAIN
        nums.mean_ci(stem, row, src, f"{what}: balanced accuracy", ci=ci)
        recall = row.method in ("rct_tslr", "ts_lr", "ah_proxy") and row.session == "pre"
        if row.scenario == "S2_new_command" and recall:
            nums.add(stem + "SfRecall", pct(row.sf_recall), src, f"{what}: SF recall (%)")
    for scenario, prefix in SCENARIO.items():
        labelled = rows[(rows.scenario == scenario) & (rows.k > 0) & (rows.method != "ah_proxy")]
        for k, part in labelled.groupby("k"):
            what = f"{scenario}: labelled calibration at {K_LABEL[k]} (minutes)"
            nums.add(f"{prefix}Minutes{K[k]}", fixed(single(part.minutes)), src, what)
    rest = rows[(rows.k == 0) & rows.method.isin(["rct_tslr", "rct_mdm", "eegnet_ea_ft"])]
    what = "unlabelled rest the transfer methods use at k = 0 (minutes)"
    nums.add("rqTwoRestMinutes", fixed(single(rest.minutes)), src, what)
    scratch = rows[
        (rows.scenario == "S2_new_command") & (rows.task == "T2_rest_ah_sf")
        & (rows.session == "pre") & (rows.method == "ts_lr") & rows.k.isin([1, 2, 3, 5])
    ]  # fmt: skip
    what = "S2_new_command, REST vs AH vs SF, pre, ts_lr, k = 1 to 5: SF recall (%)"
    nums.span("rqThreeRestAhSfTsLrSfRecall", scratch.sf_recall, src, what)

    src = "summary/calib_minutes.csv"
    recorded = nums.csv(src)
    recorded = recorded[recorded.session == "pre"]
    for scenario, prefix in SCENARIO.items():
        for _, row in recorded[(recorded.scenario == scenario) & (recorded.k > 0)].iterrows():
            nominal = nums.entries.get(f"{prefix}Minutes{K[row.k]}")
            if nominal is not None and nominal.plain != fixed(row.minutes).plain:
                raise SystemExit(f"{src} and calib_curves.csv disagree on the nominal minutes")
            what = (
                f"{scenario}: labelled calibration at {K_LABEL[row.k]}, recorded length (minutes)"
            )
            nums.add(f"{prefix}MinutesRecorded{K[row.k]}", fixed(row.minutes_recorded), src, what)
    what = "pre, runs 01-02: a run's recorded length over its trials, median (s)"
    nums.add("rqTwoTrialSecondsRecorded", fixed(single(recorded.trial_s_recorded)), src, what)
    what = "pre, runs 01-02: rest marker to the cue, median of the runs' medians (s)"
    nums.add("rqTwoRestSecondsRecorded", fixed(single(recorded.rest_s_recorded)), src, what)
    what = "unlabelled rest at k = 0 at the recorded rest length (minutes)"
    rest_min = fixed(single(recorded.rest_set_minutes_recorded))
    nums.add("rqTwoRestMinutesRecorded", rest_min, src, what)

    src = "summary/calib_confirmatory.csv"
    hypotheses = {
        "H2a": ("rqTwo", "HTwoA"),
        "H2b": ("rqTwo", "HTwoB"),
        "H3a": ("rqThree", "HThreeA"),
        "H3b": ("rqThree", "HThreeB"),
        "H3c_k2": ("rqThree", "HThreeCKTwo"),
        "H3c_k5": ("rqThree", "HThreeCKFive"),
    }
    confirmatory = nums.csv(src)
    main = (
        (confirmatory.session == "pre")
        & (confirmatory.population == "all")
        & (confirmatory.draw_basis == "random")
    )
    # The pre-registered population first, then its replications and sensitivity checks.
    for index in [*confirmatory.index[main], *confirmatory.index[~main]]:
        row, is_main = confirmatory.loc[index], bool(main[index])
        prefix, hyp = hypotheses[row.hypothesis]
        basis = "Chrono" if row.draw_basis == "chrono" else ""
        stem = prefix + ("Eegnet" if row.role == "secondary" else "") + hyp
        stem += SESSION[row.session] + POP[row.population] + basis
        what = (
            f"{row.hypothesis} ({row.role}), {row.pair.replace(' - ', ' minus ')}, "
            f"{row.quantity}, {row.session}, {POP_LABEL[row.population]}, {row.draw_basis} draw"
        )
        units = "ALC" if row.quantity == "ALC" else "balanced accuracy, fraction"
        nums.test(stem, row, src, what, fmt=fixed3, unit=units, full=is_main)
        if not is_main:
            median = fixed3(row.median_diff)
            nums.add(stem + "MedianDiff", median, src, f"median difference ({units})")
        if row.quantity != "ALC":
            for token, column, label in (
                ("PointsDiff", "mean_diff", "mean difference (points)"),
                ("PointsDiffCiLo", "ci_lo", "CI lower (points)"),
                ("PointsDiffCiHi", "ci_hi", "CI upper (points)"),
                ("PointsMedianDiff", "median_diff", "median difference (points)"),
            ):
                nums.add(stem + token, pct(row[column]), src, label)

    src = "summary/calib_h2a_per_k.csv"
    for _, row in nums.csv(src).iterrows():
        what = f"S1, three classes, rct_tslr minus ts_lr at k = {row.k} (Holm over 5)"
        nums.test(f"rqTwoAdvantage{K[row.k]}", row, src, what)

    src = "summary/calib_trials_saved.csv"
    pair_tok = {"rct_tslr - ts_lr": "", "eegnet_ea_ft - eegnet_scratch": "Eegnet"}
    for _, row in nums.csv(src).iterrows():
        stem = SCENARIO[row.scenario] + "Reach" + pair_tok[row.pair] + TASK[row.task]
        stem += SESSION[row.session] + SPELL[round(100 * row.threshold)]
        first, second = row.pair.split(" - ")
        what = (
            f"{row.scenario}, {TASK_LABEL[row.task]}, {row.session}, "
            f"patients reaching {100 * row.threshold:.0f} %"
        )
        for column, token, label in (
            ("n_both_reach", "Both", f"with both {first} and {second}"),
            ("n_only_first", "OnlyTransfer", f"only with {first}"),
            ("n_only_second", "OnlyScratch", f"only with {second}"),
            ("n_neither", "Neither", "with neither"),
        ):
            nums.add(stem + token, integer(row[column]), src, f"{what} {label}")
        saved = f"{what}: trials per class saved by {first}"
        median = whole_or(row.median_trials_saved)
        nums.add(stem + "MedianSaved", median, src, f"{saved}, median", optional=True)
        mean = fixed(row.mean_trials_saved)
        nums.add(stem + "MeanSaved", mean, src, f"{saved}, mean", optional=True)

    src = "summary/calib_friedman.csv"
    friedman = nums.csv(src)
    for (scenario, task, k), part in friedman.groupby(["scenario", "task", "k"]):
        stem = SCENARIO[scenario] + "Friedman" + TASK[task] + K[k]
        what = f"{scenario}, {TASK_LABEL[task]}, {K_LABEL[k]}: Friedman test over the methods"
        nums.add(stem + "ChiSq", fixed(single(part.chi2)), src, f"{what}, chi-squared")
        nums.add(stem + "P", sig(single(part.p)), src, f"{what}, p")
        nums.add(stem + "Cd", fixed2(single(part.nemenyi_cd)), src, f"{what}, Nemenyi CD")
        nums.add(stem + "N", integer(single(part.n_subjects)), src, f"{what}, patients")
        if k != 5:
            continue
        for _, row in part.iterrows():
            name = SCENARIO[scenario] + "Rank" + TASK[task] + K[k] + METHOD[row.method]
            what = f"{scenario}, {TASK_LABEL[task]}, {K_LABEL[k]}: mean rank of {row.method}"
            nums.add(name, fixed2(row.mean_rank), src, what)

    src = "summary/calib_nosignal.csv"
    nosignal = nums.csv(src)
    for _, row in nosignal.iterrows():
        what = f"labels permuted, {TASK_LABEL[row.task]}, {row.method}: balanced accuracy (%)"
        name = "rqTwoNoSignal" + TASK[row.task] + METHOD[row.method]
        nums.add(name, pct(row.mean_bal_acc), src, what)
    for task, part in nosignal.groupby("task"):
        what = f"labels permuted, {TASK_LABEL[task]}: allowed distance from chance"
        nums.add(f"rqTwoNoSignal{TASK[task]}Tolerance", fixed2(single(part.tolerance)), src, what)
    nums.add("rqTwoNoSignalN", integer(single(nosignal.n)), src, "labels permuted: patients")
    passed = integer(nosignal.passes.sum())
    nums.add("rqTwoNoSignalPassed", passed, src, "labels permuted: cells within it", "count")

    what = "labels permuted: largest distance of a method's mean from chance"
    distance = fixed3(nosignal.distance_from_chance.max())
    nums.add("rqTwoNoSignalDistanceMax", distance, src, what, "range")

    src = "summary/calib_method_summary.csv"
    methods = nums.csv(src)
    for _, row in methods[methods.session == "pre"].iterrows():
        stem = SCENARIO[row.scenario] + TASK[row.task] + METHOD[row.method]
        what = f"{row.scenario}, {TASK_LABEL[row.task]}, pre, {row.method}"
        nums.add(stem + "AlcMean", fixed3(row.mean_alc), src, f"{what}: ALC, mean over patients")
        for thr, token in ((60, "Sixty"), (70, "Seventy")):
            reach = integer(row[f"n_reach_{thr}"])
            nums.add(f"{stem}Reach{token}", reach, src, f"patients reaching {thr} %", optional=True)
            k = whole_or(row[f"median_k_star_{thr}"])
            nums.add(
                f"{stem}Reach{token}MedianK", k, src, f"their median k* ({thr} %)", optional=True
            )
        # The own-hand control ignores the budget.
        if pd.isna(row.get("n_k0_k1")) or row.method == "ah_proxy":
            continue
        drop = fixed(row.k1_minus_k0_points)
        nums.add(stem + "KOneMinusKZeroDiff", drop, src, "k = 1 minus k = 0, mean (points)")
        below = integer(row.n_k1_below_k0)
        nums.add(stem + "KOneBelowKZero", below, src, "patients lower at k = 1 than at k = 0")

    src = "summary/calib_pair_whole_pool.csv"
    for _, row in nums.csv(src).query("session == 'pre'").iterrows():
        stem = SCENARIO[row.scenario] + TASK[row.task] + "TsLrMinusRctTslrKAll"
        what = f"{row.scenario}, {TASK_LABEL[row.task]}, pre, k = all: ts_lr minus rct_tslr"
        nums.add(stem + "Diff", fixed(-row.mean_diff_points), src, f"{what} (points, no test)")
        nums.add(stem + "DiffCiLo", fixed(-row.ci_hi_points), src, "CI lower")
        nums.add(stem + "DiffCiHi", fixed(-row.ci_lo_points), src, "CI upper")
        nums.add(stem + "Better", integer(row.n_second_higher), src, "patients higher with ts_lr")
        nums.add(stem + "Worse", integer(row.n_first_higher), src, "patients higher with rct_tslr")

    src = "summary/calib_alc_subject_values.csv"
    alcs = nums.csv(src)
    h3a = alcs[(alcs.hypothesis == "H3a") & (alcs.role == "confirmatory")].nsmallest(3, "diff")
    for (_, row), token in zip(h3a.iterrows(), ("", "Second", "Third"), strict=True):
        stem = f"rqThreeHThreeAPatient{token}Lowest"
        what = f"H3a, rct_tslr minus ts_lr, ALC: the {token.lower() or 'first'} lowest patient"
        nums.add(stem + "Diff", fixed3(row["diff"]), src, f"{what}, difference", "range")
        nums.add(stem + "Subject", word(row.subject), src, "that patient", "range")

    src = "summary/calib_zeroshot_check.csv"
    check = nums.csv(src)
    what = "EEGNet at k = 0 against P07's zero-shot"
    nums.add("rqTwoZeroShotCheckCells", integer(len(check)), src, f"{what}: cells", "count")
    largest = sig(check.abs_diff.max())
    nums.add("rqTwoZeroShotCheckMaxDiff", largest, src, f"{what}: largest difference", "range")

    src = "summary/transfer_hparams.csv"
    hparams = nums.csv(src)
    for method in ("rct_tslr", "rct_mdm"):
        part = hparams[hparams.method == method]
        weight = integer(one(part, chosen=True).target_weight)
        stem = f"rqTwoHparam{METHOD[method]}"
        nums.add(stem + "Weight", weight, src, f"{method}: target weight chosen")
        for _, row in part.iterrows():
            what = f"{method}, target weight {int(row.target_weight)}: development mean (%)"
            name = f"{stem}Weight{SPELL[int(row.target_weight)]}Mean"
            nums.add(name, pct(row.mean_bal_acc), src, what)
        what = f"{method}: development means of the candidate weights (%)"
        nums.span(f"{stem}Mean", part.mean_bal_acc, src, what)
    chosen = one(hparams[hparams.method == "eegnet_ea_ft"], chosen=True)
    lr = general(chosen.finetune_lr)
    nums.add("rqTwoHparamEegnetLr", lr, src, "eegnet_ea_ft: fine-tuning learning rate")
    steps = integer(chosen.finetune_epochs)
    nums.add("rqTwoHparamEegnetEpochs", steps, src, "eegnet_ea_ft: fine-tuning steps")

    src = "summary/rq3_sf_vs_ah.csv"
    for _, row in nums.csv(src).iterrows():
        if row.method == "ah_proxy" and row.k != 0:
            continue
        budget = "" if row.method == "ah_proxy" else K[row.k]
        name = "rqThreeHandAsFinger" + SESSION[row.session] + METHOD[row.method] + budget
        when = "" if row.method == "ah_proxy" else f", {K_LABEL[row.k]}"
        what = f"S2 SF-vs-REST decoder, {row.session}, {row.method}{when}: AH windows called SF"
        nums.add(name, pct(row.mean_sf_vs_ah), src, what + " (%)")


def rq_four(nums: Numbers) -> None:
    src = "summary/rq4_mirror_table.csv"
    mirror = nums.csv(src)
    for _, row in mirror.iterrows():
        stem = "rqFourMirror" + METHOD[row.method] + K[row.k]
        what = f"mirroring, S1 three classes, {row.method}, {K_LABEL[row.k]}"
        for column, token, label in (
            ("mean_mirrored", "Mirrored", "mirrored (%)"),
            ("mean_unmirrored", "Unmirrored", "unmirrored (%)"),
            ("mean_diff", "Diff", "mirrored minus unmirrored (points)"),
            ("ci_lo", "DiffCiLo", "CI lower"),
            ("ci_hi", "DiffCiHi", "CI upper"),
            ("mean_diff_L", "DiffLeft", "difference, left-hemiplegic patients (points)"),
            ("mean_diff_R", "DiffRight", "difference, right-hemiplegic patients (points)"),
        ):
            nums.add(
                stem + token,
                pct(row[column]),
                src,
                f"{what}: {label}" if token == "Mirrored" else label,
            )
        nums.add(stem + "P", sig(row.p), src, "two-sided Wilcoxon p")
        nums.add(stem + "PHolm", sig(row.p_holm), src, "Holm p over k")
    for method, part in mirror.groupby("method"):
        what = f"mirroring, {method}, over k"
        stem = f"rqFourMirror{METHOD[method]}"
        nums.span(stem + "Diff", part.mean_diff, src, f"{what}: difference (points)")
        nums.span(stem + "DiffLeft", part.mean_diff_L, src, f"{what}: left-hemiplegic (points)")
    nums.add("rqFourMirrorN", integer(single(mirror.n)), src, "mirroring: patients")
    left = integer(single(mirror.n_left))
    nums.add("rqFourMirrorNLeft", left, src, "mirroring: left-hemiplegic patients")
    lowest = sig(mirror.p_holm.min())
    nums.add("rqFourMirrorPHolmMin", lowest, src, "mirroring: smallest Holm p", "range")
    for _, row in mirror.iterrows():
        stem = "rqFourMirror" + METHOD[row.method] + K[row.k]
        nums.add(stem + "MedianDiff", pct(row.median_diff), src, "per-patient median (points)")
        nums.add(stem + "Better", integer(row.n_better), src, "patients higher mirrored")
        nums.add(stem + "Worse", integer(row.n_worse), src, "patients lower mirrored")
    for side, token, who in (
        ("L", "Left", "left-hemiplegic, own data mirrored"),
        ("R", "Right", "right-hemiplegic, own data unchanged"),
    ):
        what = f"mirroring, {who}: one patient's difference, every method and k (points)"
        lows, highs = mirror[f"min_diff_{side}"], mirror[f"max_diff_{side}"]
        nums.add(f"rqFourMirrorPatientDiff{token}Min", pct(lows.min()), src, what, "range")
        nums.add(f"rqFourMirrorPatientDiff{token}Max", pct(highs.max()), src, "largest", "range")

    src = "summary/rq4_longitudinal_table.csv"
    arm_tok = {
        "pre_unchanged": "Unchanged",
        "recentred": "Recentred",
        "pooled": "Pooled",
        "new_only": "NewOnly",
    }
    for _, row in nums.csv(src).iterrows():
        budget = "" if row.arm == "pre_unchanged" else K[row.k]
        stem = "rqFourLater" + row.session.capitalize() + arm_tok[row.arm] + budget
        stem += GROUP[row.population]
        who = "all patients" if row.population == "all" else f"group {row.population}"
        what = f"pre decoder on {row.session}, {row.arm}, {row.k} new trials per class, {who}"
        everyone = row.population == "all"
        nums.mean_ci(stem, row, src, f"{what}: three-class balanced accuracy", ci=everyone)
        if everyone:
            nums.add(stem + "N", integer(row.n), src, "patients")

    src = "summary/rq4_longitudinal_reference.csv"
    refs = nums.csv(src)
    for (session, ref), part in refs.groupby(["session", "reference_session"]):
        stem = f"rqFourLater{session.capitalize()}Within{ref.capitalize()}"
        what = (
            f"ts_lr with the whole {ref} pool, within {ref}, on the {session} patients "
            "(P08, three classes)"
        )
        nums.add(stem + "Mean", pct(single(part.reference_mean)), src, f"{what} (%)")
        nums.add(stem + "N", integer(single(part.n)), src, "patients")
    for _, row in refs.iterrows():
        budget = "" if row.arm == "pre_unchanged" else K[row.k]
        stem = f"rqFourLater{row.session.capitalize()}{arm_tok[row.arm]}{budget}"
        what = f"{row.session}, {row.arm}, k = {row.k}, minus the within-{row.reference_session}"
        nums.add(
            f"{stem}VsWithin{row.reference_session.capitalize()}Diff",
            fixed(row.arm_minus_reference_points),
            src,
            f"{what} reference (points)",
        )

    replay_metrics = {
        "sf_detection_rate": ("FingerDetect", pct, "%", "SF periods with an SF command"),
        "ah_detection_rate": ("HandDetect", pct, "%", "AH periods with an AH command"),
        "ah_as_sf_rate": ("HandAsFinger", pct, "%", "AH periods that flexed the sixth finger"),
        "false_per_minute": ("FalsePerMin", fixed2, "per minute", "false activations of rest"),
        "sf_latency_s": ("FingerLatency", fixed2, "s", "SF latency after the cue"),
        "itr_bits_per_min": ("Itr", fixed2, "bits per minute", "information transfer rate"),
    }
    src = "summary/rq4_pseudo_online_table.csv"
    replay = nums.csv(src)
    for _, row in replay[replay.population == "all"].iterrows():
        token, fmt, unit, label = replay_metrics[row.metric]
        stem = "rqFourReplay" + METHOD[row.method] + token
        what = f"pseudo-online, {row.method}: {label}"
        nums.mean_ci(stem, row, src, what, fmt, unit)
        if row.metric == "sf_latency_s":
            nums.add(stem + "N", integer(row.n), src, "patients with a detection")
    for (population, metric), part in replay.groupby(["population", "metric"]):
        token, fmt, unit, label = replay_metrics[metric]
        what = f"pseudo-online, {POP_LABEL[population]}, four methods: {label} ({unit})"
        nums.span(f"rqFourReplay{POP[population]}{token}", part["mean"], src, what, fmt)
        if metric == "sf_latency_s":
            what = f"pseudo-online, {POP_LABEL[population]}: patients with an SF detection"
            nums.span(f"rqFourReplay{POP[population]}FingerLatencyN", part.n, src, what, integer)
    src = "summary/rq4_pseudo_online_details.csv"
    details = nums.csv(src)
    for _, row in details.iterrows():
        stem = "rqFourReplay" + METHOD[row.method]
        what = f"pseudo-online, {row.method}"
        nums.add(
            stem + "FingerHalf",
            integer(row.n_sf_half),
            src,
            f"{what}: patients with half of their SF periods detected",
        )
        nums.add(stem + "FingerNone", integer(row.n_sf_none), src, "patients with none")
        nums.add(
            stem + "FingerDetectMax",
            pct(row.sf_detection_max),
            src,
            "SF periods detected, best patient (%)",
        )
        ratio = fixed2(row.ah_as_sf_over_sf_detection)
        nums.add(
            stem + "HandAsFingerRatio",
            ratio,
            src,
            "AH periods flexing SF over SF periods detected (means)",
        )
        nums.add(stem + "False", integer(row.false_activations), src, "false activations")
        nums.add(
            stem + "FalseEarly",
            integer(row.false_first_seconds),
            src,
            "of them, in the first 2 s of a rest period",
        )
        nums.add(stem + "FalseEarlyShare", pct(row.false_first_share), src, "share (%)")
        nums.add(
            stem + "FalsePerMinStoppedEarlyDiff",
            fixed2(row.false_per_minute_stopped_early_change),
            src,
            "periods stopped at the next one and at a cut: change of false per minute",
        )
        nums.add(
            stem + "DetectMovedStoppedEarly",
            integer(row.n_detection_moved_stopped_early),
            src,
            "patients whose detection rates change then",
        )
        nums.add(
            "rqFourSwitch" + METHOD[row.method] + "Half",
            integer(row.n_switch_half),
            src,
            f"one switch, {row.method}: patients with half of their imagery periods",
        )
    what = "pseudo-online, four methods"
    nums.span(
        "rqFourReplayFingerHalf",
        details.n_sf_half,
        src,
        f"{what}: patients with half of their SF periods",
        integer,
    )
    nums.span(
        "rqFourReplayFalseEarlyShare",
        details.false_first_share,
        src,
        f"{what}: false activations in the first 2 s of rest (%)",
    )
    nums.span(
        "rqFourReplayFalsePerMinStoppedEarlyDiff",
        details.false_per_minute_stopped_early_change,
        src,
        f"{what}: change of false per minute, periods stopped early",
        fixed2,
    )
    nums.span(
        "rqFourSwitchHalf",
        details.n_switch_half,
        src,
        "one switch, four methods: patients with half of their imagery periods",
        integer,
    )

    src = "summary/rq4_pseudo_online_replay.json"
    replay = nums.json(src)
    kept = replay["windows kept per run (share)"]
    nums.add("rqFourReplayRuns", integer(kept["runs"]), src, "runs replayed")
    nums.add(
        "rqFourReplayWindowsKeptMedian",
        pct(kept["median"]),
        src,
        "windows kept per run, median (%)",
    )
    nums.add("rqFourReplayWindowsKeptMin", pct(kept["min"]), src, "lowest run (%)")
    nums.add("rqFourReplayWindowsKeptMax", pct(kept["max"]), src, "highest run (%)")
    periods = replay["periods"]
    nums.add("rqFourReplayPeriods", integer(periods["total"]), src, "scored periods")
    nums.add(
        "rqFourReplayPeriodsOverlapping",
        integer(periods["overlapping the next"]),
        src,
        "periods overlapping the next",
    )
    nums.add(
        "rqFourReplayPeriodsCut",
        integer(periods["holding a boundary cut"]),
        src,
        "periods holding a boundary cut",
    )
    spacing = replay["rest onset to the next rest onset (s)"]
    for key, token, label in (
        ("median", "Median", "median"),
        ("p5", "PercentileFive", "5th percentile"),
        ("p95", "PercentileNinetyFive", "95th percentile"),
        ("min", "Min", "shortest"),
        ("max", "Max", "longest"),
    ):
        nums.add(
            f"rqFourReplaySpacing{token}",
            fixed(spacing[key]),
            src,
            f"one rest onset to the next, {label} (s)",
        )
    silent = replay["a gate that never fires"]
    nums.add(
        "rqFourReplaySilentP",
        fixed3(silent["P correct, mean over patients"]),
        src,
        "a gate that never fires: P correct, mean over patients",
    )
    nums.add(
        "rqFourReplaySilentItr",
        fixed2(silent["ITR bits per minute, mean over patients"]),
        src,
        "a gate that never fires: bits per minute, mean over patients",
    )
    early = replay["early false activation"]
    nums.add(
        "rqFourReplayEarlySeconds",
        whole_or(early["seconds"]),
        src,
        "an early false activation: within this many seconds of rest",
    )
    nums.add(
        "rqFourReplayEarlyEvenShare",
        pct(early["share of the rest period"]),
        src,
        "the share of a rest period those seconds are (%)",
    )
    anyone = integer(replay["patients reaching half of their SF periods with any method"])
    nums.add(
        "rqFourReplayFingerHalfAnyMethod",
        anyone,
        src,
        "patients with half of their SF periods detected by any method",
    )

    src = "summary/rq4_pseudo_online_repro.csv"
    for _, row in nums.csv(src).iterrows():
        what = f"replay refit of {row.method} against P08: largest balanced-accuracy difference"
        nums.add(
            f"rqFourReplayRepro{METHOD[row.method]}MaxDiff", fixed3(row.max_abs_diff), src, what
        )

    switch_metrics = {
        "imagery_detection_rate": ("Detect", pct, "%", "imagery periods detected"),
        "false_per_minute": ("FalsePerMin", fixed2, "per minute", "false activations of rest"),
        "latency_s": ("Latency", fixed2, "s", "latency, mean of each patient's median"),
    }
    src = "summary/rq4_pseudo_online_switch_table.csv"
    switch = nums.csv(src)
    for _, row in switch.iterrows():
        token, fmt, unit, label = switch_metrics[row.metric]
        what = f"one switch (rest vs any imagery), {row.method}: {label}"
        nums.mean_ci("rqFourSwitch" + METHOD[row.method] + token, row, src, what, fmt, unit)
    nums.add("rqFourSwitchN", integer(switch.n.max()), src, "one switch: patients", "range")
    for metric, part in switch.groupby("metric"):
        token, fmt, unit, label = switch_metrics[metric]
        what = f"one switch, four methods: {label} ({unit})"
        nums.span(f"rqFourSwitch{token}", part["mean"], src, what, fmt)

    src = "summary/rq4_visual_cue_table.csv"
    channels = {
        "all_40": "AllChannels",
        "central_14": "Central",
        "parieto_occipital_5": "ParietoOccipital",
    }
    cue = nums.csv(src)
    for _, row in cue.iterrows():
        stem = "rqFourCue" + TASK[row.task] + channels[row.channels]
        what = f"visual-cue check, ts_lr chrono, {TASK_LABEL[row.task]}, {row.channels}"
        nums.mean_ci(stem, row, src, f"{what}: balanced accuracy")
    nums.add("rqFourCueN", integer(single(cue.n)), src, "visual-cue check: patients")
    src = "summary/rq4_visual_cue_paired.csv"
    for _, row in nums.csv(src).iterrows():
        stem = f"rqFourCue{TASK[row.task]}{channels[row.arm]}Vs{channels[row.baseline]}"
        what = f"visual-cue check, {TASK_LABEL[row.task]}, {row.arm} minus {row.baseline}"
        nums.paired(stem, row, src, what, means=False)
        # The text says how far the central channels are ahead on SF vs REST.
        if row.task == "T3_sf_vs_rest" and (row.arm, row.baseline) == (
            "parieto_occipital_5",
            "central_14",
        ):
            turned = f"rqFourCue{TASK[row.task]}CentralMinusParietoOccipital"
            what = f"visual-cue check, {TASK_LABEL[row.task]}, central_14 minus parieto_occipital_5"
            nums.add(turned + "Diff", fixed(-row.diff_points), src, f"{what} (points)")
            nums.add(turned + "DiffCiLo", fixed(-row.diff_ci_hi), src, "CI lower")
            nums.add(turned + "DiffCiHi", fixed(-row.diff_ci_lo), src, "CI upper")

    src = "summary/rq4_pattern_share_summary.csv"
    shares = nums.csv(src)
    source_tok = {
        "csp_T1_ah_vs_sf": "CspAhSf",
        "csp_T3_sf_vs_rest": "CspSfRest",
        "eegnet_pretrained": "Eegnet",
    }
    for _, row in shares.iterrows():
        stem = "rqFourPattern" + source_tok[row.source]
        what = f"pattern weight, {row.source}, mean over {row.n} maps"
        nums.add(
            stem + "FrontalShare",
            pct(row.frontal_share_mean),
            src,
            f"{what}: four frontal channels (%)",
        )
        nums.add(
            stem + "ParietoOccipitalShare",
            pct(row.parieto_occipital_share_mean),
            src,
            "five parieto-occipital channels (%)",
        )
        nums.add(stem + "N", integer(row.n), src, "maps averaged")
    csp = shares[shares.source.str.startswith("csp_")]
    nums.span(
        "rqFourPatternCspFrontalShare",
        csp.frontal_share_mean,
        src,
        "pattern weight on the frontal channels, both CSP tasks (%)",
    )
    nums.span(
        "rqFourPatternCspParietoOccipitalShare",
        csp.parieto_occipital_share_mean,
        src,
        "pattern weight on the parieto-occipital channels, both CSP tasks (%)",
    )
    nums.add(
        "rqFourPatternFrontalChannelShare",
        pct(single(shares.frontal_channel_share)),
        src,
        "the frontal channels' share of the 40 (%)",
    )
    po_share = pct(single(shares.parieto_occipital_channel_share))
    nums.add(
        "rqFourPatternParietoOccipitalChannelShare",
        po_share,
        src,
        "the parieto-occipital channels' share of the 40 (%)",
    )


def rq_five(nums: Numbers) -> None:
    data_tok = {"mumtaz": "Mumtaz", "modma": "Modma"}
    pipe_tok = {"bp_lr": "BpLr", "ts_lr": "TsLr"}
    prot_tok = {"segment_cv": "SegmentCv", "subject_cv": "SubjectCv"}
    src = "summary/rq5_table.csv"
    for _, row in nums.csv(src).iterrows():
        stem = "rqFive" + data_tok[row.dataset] + pipe_tok[row.pipeline] + prot_tok[row.protocol]
        what = f"{row.dataset}, {row.pipeline}, {row.protocol}"
        nums.add(stem + "Ba", pct(row.ba), src, f"{what}: subject-weighted balanced accuracy (%)")
        mine = pct(row.diagnosed)
        nums.add(stem + "Diagnosed", mine, src, f"{what}: people assigned their own group (%)")
    src = "summary/rq5_stats.csv"
    for _, row in nums.csv(src).iterrows():
        stem = "rqFive" + data_tok[row.dataset] + pipe_tok[row.pipeline]
        what = f"{row.hypothesis}, {row.dataset}, {row.pipeline}, segment minus subject CV"
        for column, token, fmt, label in (
            ("inflation_points", "Inflation", fixed, "inflation (points)"),
            ("ci_lo_points", "InflationCiLo", fixed, "CI lower"),
            ("ci_hi_points", "InflationCiHi", fixed, "CI upper"),
            ("median_diff", "MedianDiff", pct, "median per-person difference (points)"),
            ("n", "N", integer, "people"),
            ("n_nonzero", "NNonzero", integer, "people whose values differ"),
            ("W", "W", whole_or, "Wilcoxon W"),
            ("p", "P", sig, "one-sided p"),
            ("p_holm", "PHolm", sig, "Holm p"),
            ("r_rb", "R", fixed2, "rank-biserial r"),
            ("category", "Category", word, "category"),
        ):
            nums.add(
                stem + token,
                fmt(row[column]),
                src,
                f"{what}: {label}" if token == "Inflation" else label,
            )
    src = "summary/rq5_auc.csv"
    auc = nums.csv(src)
    for _, row in auc.iterrows():
        stem = "rqFive" + data_tok[row.dataset] + pipe_tok[row.pipeline] + prot_tok[row.protocol]
        what = f"{row.dataset}, {row.pipeline}, {row.protocol}: ROC-AUC over segments"
        nums.add(stem + "Auc", fixed2(row.auc), src, what)
    for name, part in auc.groupby("dataset"):
        segments = integer(single(part.n_segments))
        nums.add(f"rqFive{data_tok[name]}Segments", segments, src, f"{name}: segments")
    src = "summary/rq5_exploratory.csv"
    analysis_tok = {"E1_year_2013": "TwentyThirteen", "E2_overlap": "Overlap", "E3_gad7": "Anxiety"}
    for _, row in nums.csv(src).iterrows():
        name = "rqFive" + data_tok[row.dataset] + analysis_tok[row.analysis]
        name += pipe_tok[row.pipeline] + prot_tok[row.protocol] + "Ba"
        what = f"{row.analysis} (exploratory), {row.dataset}, {row.pipeline}, {row.protocol}"
        nums.add(name, pct(row.ba), src, f"{what}: balanced accuracy (%)")
    src = "summary/rq5_null.csv"
    null = nums.csv(src)
    for protocol, part in null.groupby("protocol"):
        what = f"Mumtaz ts_lr, diagnoses shuffled, {protocol}: balanced accuracy (%)"
        nums.span(f"rqFiveShuffled{prot_tok[protocol]}", part.ba, src, what)
    shuffles = integer(single(null.groupby("protocol").size()))
    nums.add("rqFiveShuffles", shuffles, src, "diagnoses shuffled: permutations", "count")
    src = "summary/rq5_null_summary.csv"
    for _, row in nums.csv(src).iterrows():
        what = f"Mumtaz ts_lr, diagnoses shuffled, {row.protocol}: mean over the permutations (%)"
        nums.add(f"rqFiveShuffled{prot_tok[row.protocol]}Mean", pct(row["mean"]), src, what)
    src = "summary/rq5_years_mumtaz.csv"
    year_tok = {2011: "TwentyEleven", 2013: "TwentyThirteen"}
    for _, row in nums.csv(src).iterrows():
        stem = f"rqFiveMumtaz{year_tok[row.year]}"
        nums.add(stem + "Healthy", integer(row.H), src, f"Mumtaz {row.year}: healthy recordings")
        nums.add(stem + "Depressed", integer(row.MDD), src, f"Mumtaz {row.year}: MDD recordings")
    for name in ("mumtaz", "modma"):
        src = f"audit/rq5_audit_{name}.csv"
        kept = nums.csv(src)
        kept = kept[kept.kept]
        stem = "rqFive" + data_tok[name]
        people = integer(kept.subject.nunique())
        nums.add(stem + "People", people, src, f"{name}: people after the audit", "count")
        for group, token in (("H", "Healthy"), ("MDD", "Depressed")):
            count = integer(kept[kept.group == group].subject.nunique())
            nums.add(stem + token, count, src, f"{name}: {group} people after the audit", "count")
    src = "summary/rq5_signals_mumtaz.csv"
    signals_tok = {21: "TwentyOne", 23: "TwentyThree"}
    group_tok = {"H": "Healthy", "MDD": "Depressed"}
    for _, row in nums.csv(src).iterrows():
        name = f"rqFiveMumtaz{year_tok[row.year]}{group_tok[row.group]}"
        name += f"Signals{signals_tok[row.n_signals]}"
        what = f"Mumtaz {row.year}, {row.group}: kept files whose EDF header has {row.n_signals}"
        nums.add(name, integer(row.files), src, f"{what} signals")
    src = "summary/rq5_gad7_modma.csv"
    side_tok = {"gad7_10_or_more": "AnxietyHigh", "gad7_below_10": "AnxietyLow"}
    side_label = {"gad7_10_or_more": "GAD-7 of 10 or more", "gad7_below_10": "GAD-7 below 10"}
    for _, row in nums.csv(src).iterrows():
        name = f"rqFiveModma{side_tok[row.gad7_side]}{group_tok[row.group]}"
        what = f"MODMA, {side_label[row.gad7_side]}, {row.group}: participants"
        nums.add(name, integer(row.participants), src, what)


EX_ONE = {
    "A_standard": "CropsVsTsLr",
    "A_crop_mean": "CropsCropMeanVsTsLr",
    "A_baseline_crop_mean": "CropMeanVsTsLr",
    "C": "RctPooledVsPostOnly",
    "C_plain_pooled": "PlainPooledVsPostOnly",
    "B": "ArmBVsEegnetScratch",
    "B_vs_ts_lr": "ArmBVsTsLr",
    "B_vs_zeroshot_rest": "ArmBVsZeroShot",
    "B_pretrained_same_alignment": "ArmBPretrainedVsEegnetScratch",
    "B_vs_pretrained_same_alignment": "ArmBVsArmBPretrained",
    "B_pretrained_same_alignment_vs_ts_lr": "ArmBPretrainedVsTsLr",
}


def ex_one(nums: Numbers) -> None:
    src = "summary/ex1_transfer_ah_sf_paired.csv"
    for _, row in nums.csv(src).iterrows():
        comparison, _, channels = row.comparison.partition(" [")
        # A check that the zero-shot model was read back exactly, not a comparison.
        if comparison == "zeroshot_rest_logspace_vs_committed":
            continue
        central = "Central" if channels.startswith("central_14") else ""
        where = ", central 14 channels" if central else ""
        what = f"AH vs SF, pre, chrono{where}, {row.arm} vs {row.baseline}"
        nums.paired("exOne" + EX_ONE[comparison] + central, row, src, what)
    src = "summary/ex1_transfer_ah_sf_checks.json"
    checks = nums.json(src)
    spread = fixed2(checks["B mean seed SD (points)"])
    nums.add("exOneArmBSeedSd", spread, src, "arm B: mean SD over 3 seeds (points)")
    spread = fixed2(checks["B central mean seed SD (points)"])
    nums.add("exOneArmBCentralSeedSd", spread, src, "arm B, central: mean SD over 3 seeds (points)")


EX_TWO_ARM = {
    "B0": "Base",
    "B0_central": "BaseCentral",
    "B0_posterior": "BasePosterior",
    "R40": "RawForty",
    "R59": "RawFiftyNine",
    "R40_535": "RawFortyPublishedBand",
    "R_central": "RawCentral",
    "S59": "SlowFiftyNine",
    "S_central": "SlowCentral",
    "S_posterior": "SlowPosterior",
    "S_eog": "SlowEyes",
    "S52_no_near_eyes": "SlowNoEyes",
    "C59": "BothFiftyNine",
    "C_central": "BothCentral",
}
EX_TWO_KIND = {
    "B0": "ts_lr, published windows",
    "R": "ts_lr, raw 8-30 Hz",
    "S": "slow-wave LDA",
    "C": "raw and slow averaged",
}
EX_TWO_LABEL = {
    "R40": "ts_lr, raw 8-30 Hz, 40 channels",
    "R59": "ts_lr, raw 8-30 Hz, 59 channels",
    "R40_535": "ts_lr, raw in the published 5-35 Hz band, 40 channels",
    "S59": "slow-wave LDA, 59 channels",
    "S_eog": "slow-wave LDA, the four eye channels",
    "S52_no_near_eyes": "slow-wave LDA without the 7 electrodes nearest the eyes",
    "C59": "raw and slow averaged, 59 channels",
}
WINDOW = {"primary": "", "secondary": "Cue"}
WINDOW_LABEL = {"primary": "[1, 5) s", "secondary": "[0, 4) s"}


def _ex_two_label(arm: str) -> str:
    if arm in EX_TWO_LABEL:
        return EX_TWO_LABEL[arm]
    kind, _, channels = arm.partition("_")
    where = {"": "40 channels", "central": "central 14", "posterior": "parieto-occipital 5"}
    return f"{EX_TWO_KIND[kind]}, {where[channels]}"


def ex_two(nums: Numbers) -> None:
    src = "summary/ex2_slow_waves_table.csv"
    table = nums.csv(src)
    for _, row in table.iterrows():
        what = f"AH vs SF, {WINDOW_LABEL[row.window]}, {_ex_two_label(row.arm)}"
        stem = "exTwo" + WINDOW[row.window] + EX_TWO_ARM[row.arm]
        nums.mean_ci(stem, row, src, f"{what}: balanced accuracy")
    nums.add("exTwoN", integer(single(table.n)), src, "slow-wave follow-up: patients")
    for name in ("ex2_slow_waves_paired.csv", "ex2_slow_waves_posthoc.csv"):
        src = f"summary/{name}"
        for _, row in nums.csv(src).iterrows():
            window = WINDOW[row.window]
            if row.arm.startswith("spearman"):
                what = (
                    f"{WINDOW_LABEL[row.window]}: Spearman correlation of the eye channels' "
                    "accuracy with the slow-wave gain (post hoc)"
                )
                nums.add(f"exTwo{window}EyesGainSpearman", fixed2(row.arm_mean), src, what)
                continue
            arm = f"exTwo{window}{EX_TWO_ARM[row.arm]}"
            # The post-hoc arm has no row in the table: its mean is the one stated here.
            if arm + "Mean" not in nums.entries:
                what = f"AH vs SF, {WINDOW_LABEL[row.window]}, {_ex_two_label(row.arm)}"
                nums.add(arm + "Mean", pct(row.arm_mean), src, f"{what}: balanced accuracy (%)")
            stem = f"{arm}Vs{EX_TWO_ARM[row.baseline]}"
            kind = "post hoc" if "posthoc" in name else row.kind
            what = (
                f"{WINDOW_LABEL[row.window]}, {_ex_two_label(row.arm)} minus "
                f"{_ex_two_label(row.baseline)} ({kind})"
            )
            nums.test(stem, row, src, what, fmt=pct, full=False)
            nums.add(stem + "Better", integer(row.n_better), src, "patients better")
            nums.add(stem + "Worse", integer(row.n_worse), src, "patients worse")
    src = "summary/ex2_slow_waves_per_patient.csv"
    per_patient = nums.csv(src)
    eyes = per_patient[(per_patient.window == "primary") & (per_patient.arm == "S_eog")]
    best = pct(eyes.bal_acc.max())
    nums.add(
        "exTwoSlowEyesPatientMax", best, src, "eye channels alone, [1, 5) s: best patient", "range"
    )

    src = "summary/ex2_slow_waves_alignment_checks.json"
    align = nums.json(src)
    for key, token, fmt, label in (
        ("n_cached_windows", "Windows", integer, "published AH and SF windows matched"),
        ("n_lag0", "AtCue", integer, "windows found at their cue"),
        ("n_searched_shifted", "Shifted", integer, "windows found after their cue, behind a cut"),
        ("n_unmatched", "Unmatched", integer, "windows not matched"),
        ("n_runs", "Runs", integer, "runs aligned"),
        ("lag0_direct_r_median", "DirectCorrMedian", fixed3, "median r without fitting"),
        ("lag0_mapped_r_median", "MappedCorrMedian", fixed3, "median r after a per-run map"),
        ("lag0_mapped_r_min", "MappedCorrMin", fixed3, "lowest r after the map"),
        ("lag0_second_best_r_max", "WrongCorrMax", fixed3, "best r with a wrong trial"),
    ):
        nums.add("exTwoAlign" + token, fmt(align[key]), src, f"raw alignment: {label}")
    shifts = pd.Series(align["shifted_samples"])
    what = "raw alignment: samples from cue to window, shifted windows"
    nums.span("exTwoAlignShiftSamples", shifts, src, what, integer)
    renumbered = integer(len(align["runs_renumbered"]))
    what = "sub-20's published runs that are other raw runs"
    nums.add("exTwoAlignRenumberedRuns", renumbered, src, what, "count")
    src = "summary/ex2_slow_waves_alignment_shifts.csv"
    shifted = nums.csv(src).shift_s
    what = "raw alignment: seconds from cue to window, shifted windows"
    nums.span("exTwoAlignShiftSeconds", shifted, src, what, fixed)


EX_THREE = {
    "GP_vs_B": "ArmGpVsArmB",
    "GP_vs_ts_lr": "ArmGpVsTsLr",
    "GP_vs_eegnet_scratch": "ArmGpVsEegnetScratch",
    "GP_no_finetune_vs_B_no_finetune": "ArmGpPretrainedVsArmBPretrained",
    "GP_vs_GP_no_finetune": "ArmGpVsArmGpPretrained",
    "G_vs_B": "ArmGVsArmB",
    "G_vs_ts_lr": "ArmGVsTsLr",
    "G_vs_eegnet_scratch": "ArmGVsEegnetScratch",
    "GP_vs_G": "ArmGpVsArmG",
    "P_vs_B": "ArmPVsArmB",
    "GP_vs_P_on_P_targets": "ArmGpVsArmP",
}
GRASP_TASK = {
    "cylindrical_vs_spherical": "CylindricalSpherical",
    "cylindrical_vs_lumbrical": "CylindricalLumbrical",
    "spherical_vs_lumbrical": "SphericalLumbrical",
    "all_three": "AllThree",
}


def ex_three(nums: Numbers) -> None:
    src = "summary/ex3_grasp_pretraining_paired.csv"
    for _, row in nums.csv(src).iterrows():
        what = f"AH vs SF, pre, chrono, {row.arm} vs {row.baseline}"
        nums.paired("exThree" + EX_THREE[row.comparison], row, src, what)
    src = "summary/ex3_grasp_pretraining_benchmark_summary.csv"
    bench = nums.csv(src)
    bench = bench[bench.train_set == "all"]
    for _, row in bench.iterrows():
        stem = "exThreeBench" + GRASP_TASK[row.task] + METHOD[row.method]
        what = f"healthy grasps, day 1 to day 2, {row.task}, {row.method}"
        nums.add(stem + "Mean", pct(row["mean"]), src, f"{what}: balanced accuracy (%)")
        nums.add(stem + "NAbove", integer(row.n_above_chance), src, "people above chance")
        threshold = pct(row.chance_threshold, 0)
        nums.add(stem + "Chance", threshold, src, "binomial chance threshold (%)")
    pairs = bench[bench.task != "all_three"]
    what = "healthy, two grasps of one hand, both methods"
    nums.span("exThreeBenchPairs", pairs["mean"], src, f"{what}: mean (%)")
    nums.span(
        "exThreeBenchPairsNAbove", pairs.n_above_chance, src, f"{what}: above chance", integer
    )
    three = bench[bench.task == "all_three"]["mean"]
    nums.span("exThreeBenchAllThree", three, src, "healthy, all three grasps, both methods (%)")
    nums.add("exThreeBenchPeople", integer(single(bench.n)), src, "healthy people")

    src = "summary/ex3_grasp_pretraining_pretraining.csv"
    grasp = nums.csv(src)
    grasp = grasp[grasp.arm == "G"]
    for model, token in (("eegnet_grasp_raw.pt", "Raw"), ("eegnet_grasp_mir.pt", "Mirrored")):
        row = one(grasp, model=model)
        what = (
            f"arm G pre-training ({token.lower()} channels): held-out healthy people's "
            "three grasps, accuracy at the best epoch (%)"
        )
        nums.add(f"exThreeArmGPretrainAcc{token}", pct(row.valid_acc_at_best), src, what)
    src = "summary/ex3_grasp_pretraining_g_selection.csv"
    chosen = one(nums.csv(src), chosen=True)
    lr = general(chosen.finetune_lr)
    nums.add("exThreeArmGFinetuneLr", lr, src, "arm G: fine-tuning learning rate chosen")
    steps = integer(chosen.finetune_epochs)
    nums.add("exThreeArmGFinetuneEpochs", steps, src, "arm G: fine-tuning steps chosen")
    src = "summary/ex3_grasp_pretraining_checks.json"
    checks = nums.json(src)
    conversion = checks["grasp_conversion"]
    trials = sum(sum(day.values()) for day in conversion["trials_per_class_by_day"].values())
    nums.add("exThreeGraspTrials", integer(trials), src, "healthy grasp trials, both days", "count")
    nums.add("exThreeGraspFiles", integer(conversion["files"]), src, "grasp files converted")
    for device, token in (("cpu", "Cpu"), ("mps", "Mps")):
        value = fixed(checks["device_timing"][device]["seconds_one_epoch"])
        what = f"one pre-training epoch on the Mac's {device} (s)"
        nums.add(f"exThreeEpochSeconds{token}", value, src, what)
    summary = checks["summary"]
    for subject, value in summary["P minus B per target, seed mean (points)"].items():
        what = f"arm P minus arm B, {subject}, mean over seeds (points)"
        nums.add(f"exThreeArmPVsArmB{SUBJECT[subject]}Diff", fixed(value), src, what)
    spread = summary["GP minus B per patient (points)"]
    what = "arm GP minus arm B, per patient (points)"
    nums.add("exThreeArmGpVsArmBPatientSd", fixed(spread["sd"]), src, f"{what}: SD")
    nums.add("exThreeArmGpVsArmBPatientMin", fixed(spread["min"]), src, "lowest patient")
    nums.add("exThreeArmGpVsArmBPatientMax", fixed(spread["max"]), src, "highest patient")
    moved = integer(spread["patients_moved_10_or_more"])
    nums.add("exThreeArmGpVsArmBPatientMovedTen", moved, src, "patients moved 10 points or more")
    for arm, hours in summary["pre-training hours on the device"].items():
        what = f"arm {arm}: pre-training hours on the Mac's GPU, all its models"
        nums.add(f"exThreeArm{arm.capitalize()}PretrainHours", fixed(hours), src, what)


EX_FOUR_ARM = {
    "csp_lda": ("", "CspLda"),
    "ts_lr": ("", "TsLr"),
    "ts_lr_c14": ("", "TsLrCentral"),
    "T_ea_ft": ("", "EegnetEaFt"),
    "T_ea_ft_c14": ("", "EegnetEaFtCentral"),
    "W_ts_lr_c14": ("", "CropsTsLrCentral"),
    "W_csp_lda": ("", "CropsCspLda"),
    "T1_ts_lr": ("AhSf", "TsLr"),
    "T1_ea_ft": ("AhSf", "EegnetEaFt"),
    "T2_ts_lr": ("RestAhSf", "TsLr"),
    "T2_ea_ft": ("RestAhSf", "EegnetEaFt"),
}
EX_FOUR_TASK = {"": "SF vs REST", "AhSf": "AH vs SF", "RestAhSf": "REST vs AH vs SF"}
EX_FOUR_LABEL = {
    "ts_lr_c14": "ts_lr on the 14 central channels",
    "T_ea_ft": "pre-trained EEGNet fine-tuned",
    "T_ea_ft_c14": "pre-trained EEGNet fine-tuned, central inputs only",
    "W_ts_lr_c14": "ts_lr central, trained on crops",
    "W_csp_lda": "csp_lda, trained on crops",
    "T1_ts_lr": "ts_lr",
    "T1_ea_ft": "pre-trained EEGNet fine-tuned",
    "T2_ts_lr": "ts_lr",
    "T2_ea_ft": "pre-trained EEGNet fine-tuned",
}
EX_FOUR_PAIRS = {
    "R (ts_lr_c14) acting vs ts_lr_c14 all windows": "TsLrCentralSureVsAll",
    "ts_lr_c14 fires on AH vs on REST": "TsLrCentralFiresAhVsRest",
    "ts_lr_c14 fires on SF vs on AH": "TsLrCentralFiresSfVsAh",
    "ts_lr_c14 fires on AH vs on REST_gated": "TsLrCentralFiresAhVsRestSure",
    "ts_lr_c14 fires on SF vs on AH_gated": "TsLrCentralFiresSfVsAhSure",
    "T1_ea_ft vs T1_ts_lr, all windows": "AhSfEegnetEaFtVsTsLr",
    "T1_ea_ft vs T1_ts_lr, accuracy when acting": "AhSfEegnetEaFtVsTsLrSure",
    "T2_ea_ft vs T2_ts_lr, all windows": "RestAhSfEegnetEaFtVsTsLr",
    "T2_ea_ft vs T2_ts_lr, accuracy when acting": "RestAhSfEegnetEaFtVsTsLrSure",
}
CLASS = {"rest": "Rest", "ah": "Ah", "sf": "Sf", "REST": "Rest", "AH": "Ah", "SF": "Sf"}


def _ex_four_arm(arm: str) -> tuple[str, str]:
    task, token = EX_FOUR_ARM[arm]
    return task + token, f"{EX_FOUR_TASK[task]}, {EX_FOUR_LABEL.get(arm, arm)}"


def _ex_four_sure(nums: Numbers, stem: str, label: str, row: pd.Series, src: str) -> None:
    plain = "plain" in row.row
    stem += "SurePlain" if plain else "Sure"
    what = f"{label}, acting only when sure, {'plain' if plain else 'class-weighted'} accuracy"
    nums.mean_ci(stem, row, src, what)
    nums.add(stem + "N", integer(row.n), src, "patients with a decision")
    nums.add(stem + "NAtLeastNinety", integer(row.n_ge_90), src, "patients at 90 % or more")
    if plain:
        return
    nums.add(stem + "Share", pct(row.share_mean), src, f"{label}: windows acted on (%)")
    nums.add(stem + "ShareCiLo", pct(row.share_ci_lo), src, "windows acted on, CI lower")
    nums.add(stem + "ShareCiHi", pct(row.share_ci_hi), src, "windows acted on, CI upper")
    none = integer(row.n_patients_no_action)
    nums.add(stem + "NoDecision", none, src, f"{label}: patients given no decision")
    reached = integer(row.n_patients_inner_reached_90)
    what = f"{label}: thresholds reaching 90 % on runs 01-02"
    nums.add(stem + "InnerReached", reached, src, what)


def ex_four(nums: Numbers) -> None:
    src = "summary/ex4_sf_command_table.csv"
    for _, row in nums.csv(src).iterrows():
        if row.section == "part1":
            stem, label = _ex_four_arm(row.row)
            stem, what = "exFour" + stem, f"{label}, every window: balanced accuracy"
            nums.mean_ci(stem, row, src, what)
            for column, token, at in (
                ("n_ge_80", "NAtLeastEighty", 80),
                ("n_ge_90", "NAtLeastNinety", 90),
            ):
                nums.add(stem + token, integer(row[column]), src, f"patients at {at} % or more")
            spread = fixed2(row.seed_sd_points)
            nums.add(stem + "SeedSd", spread, src, "mean SD over seeds (points)", optional=True)
        elif row.section == "part2_fires":
            arm, _, fire = row.row.partition(" fire_")
            cls, _, gated = fire.partition("_")
            stem, label = _ex_four_arm(arm)
            behind = " behind the threshold" if gated else ""
            what = f"{label}: {cls.upper()} test windows that turn it on{behind}"
            name = f"exFour{stem}Fires{CLASS[cls]}{'Sure' if gated else ''}"
            nums.mean_ci(name, row, src, what, ci=arm == "ts_lr_c14")
        elif row.section == "gate_share_by_class":
            arm, cls = re.fullmatch(r"(\S+), share of (\w+) windows acted on", row.row).groups()
            stem, label = _ex_four_arm(arm)
            what = f"{label}: {cls} windows acted on behind the threshold"
            nums.mean_ci(f"exFour{stem}Acted{CLASS[cls]}", row, src, what, ci=arm == "ts_lr_c14")
        else:
            arm = "ts_lr_c14" if row.section == "arm_R" else row.row.split(", ")[0]
            stem, label = _ex_four_arm(arm)
            if row.row.endswith("all windows"):
                what = f"{label}, every window: balanced accuracy"
                nums.mean_ci("exFour" + stem, row, src, what)
            else:
                _ex_four_sure(nums, "exFour" + stem, label, row, src)

    src = "summary/ex4_sf_command_selection.csv"
    for _, row in nums.csv(src).iterrows():
        stem, label = _ex_four_arm(row.arm)
        what = f"{label}, inner validation on runs 01-02: balanced accuracy"
        nums.add(f"exFour{stem}InnerMean", pct(row.inner_mean), src, f"{what} (%)")
        nums.add(f"exFour{stem}InnerCiLo", pct(row.inner_ci_lo), src, "CI lower")
        nums.add(f"exFour{stem}InnerCiHi", pct(row.inner_ci_hi), src, "CI upper")

    src = "summary/ex4_sf_command_coverage.csv"
    coverage = nums.csv(src)
    for arm in ("ts_lr_c14", "T1_ea_ft"):
        numeric = pd.to_numeric(coverage.share, errors="coerce").notna()
        stem, label = _ex_four_arm(arm)
        for _, row in coverage[(coverage.arm == arm) & numeric].iterrows():
            share = round(100 * float(row.share))
            what = f"{label}, acting on the {share} % of windows it is surest of: accuracy"
            name = f"exFour{stem}Coverage{SPELL[share]}"
            nums.add(name + "Acc", pct(row.acc_when_acting), src, f"{what} (%)")
            nums.add(name + "CiLo", pct(row.ci_lo), src, "CI lower")
            nums.add(name + "CiHi", pct(row.ci_hi), src, "CI upper")

    src = "summary/ex4_sf_command_paired.csv"
    for _, row in nums.csv(src).iterrows():
        if row.comparison in EX_FOUR_PAIRS:
            token = EX_FOUR_PAIRS[row.comparison]
        else:
            arm, base = row.comparison.split(" vs ")
            token = f"{_ex_four_arm(arm)[0]}Vs{_ex_four_arm(base)[0]}"
        # The arms' means and intervals are in the table above.
        nums.paired("exFour" + token, row, src, row.comparison, means=False, nodev=False)


EX_FIVE_ARM = {
    "M14": "Move",
    "S14": "Finger",
    "M14_sure": "MoveSure",
    "eegnet_scratch": "EegnetScratch",
    "ts_lr": "TsLr",
    "csp_lda": "CspLda",
}
EX_FIVE_LABEL = {
    "M14": "M14 (central, rest vs any movement)",
    "S14": "S14 (central, rest vs sixth finger)",
    "M14_sure": "M14-sure (M14, each patient's threshold)",
}
EX_FIVE_METRIC = {
    "imagery_detection_rate": ("Detect", pct, "%", "imagery periods detected"),
    "false_per_minute": ("FalsePerMin", fixed2, "per minute", "false activations of rest"),
    "latency_s": ("Latency", fixed2, "s", "latency, mean of each patient's median"),
    "ah_on_rate": ("HandOn", pct, "%", "hand periods that switch it on"),
    "sf_on_rate": ("FingerOn", pct, "%", "sixth-finger periods that switch it on"),
    "trial_fire_rest": ("TrialFireRest", pct, "%", "REST windows read as on, trial by trial"),
    "trial_fire_ah": ("TrialFireAh", pct, "%", "AH windows read as on, trial by trial"),
    "trial_fire_sf": ("TrialFireSf", pct, "%", "SF windows read as on, trial by trial"),
    "threshold": ("Threshold", fixed2, "probability", "on-threshold"),
}
DIFF_UNIT = {"points": fixed, "per minute": fixed2, "s": fixed2}


def ex_five(nums: Numbers) -> None:
    src = "summary/ex5_live_switch_table.csv"
    table = nums.csv(src)
    for _, row in table[table.population == "all"].iterrows():
        token, fmt, unit, label = EX_FIVE_METRIC[row.metric]
        stem = "exFive" + EX_FIVE_ARM[row.arm] + token
        what = f"as if live, {EX_FIVE_LABEL.get(row.arm, row.arm)}: {label}"
        nums.mean_ci(stem, row, src, what, fmt, unit)
        if row.n != 22:
            nums.add(stem + "N", integer(row.n), src, "patients")
    src = "summary/ex5_live_switch_paired.csv"
    for _, row in nums.csv(src).iterrows():
        arm, base = row.comparison.split(" vs ")
        token, _, _, label = EX_FIVE_METRIC[row.metric]
        stem = f"exFive{EX_FIVE_ARM[arm]}Vs{EX_FIVE_ARM[base]}{token}"
        fmt, unit = DIFF_UNIT[row.diff_unit], row.diff_unit
        what = f"{arm} minus {base}, {label}"
        nums.add(stem + "Diff", fmt(row["diff"]), src, f"{what}: mean difference ({unit})")
        nums.add(stem + "DiffCiLo", fmt(row.diff_ci_lo), src, "CI lower")
        nums.add(stem + "DiffCiHi", fmt(row.diff_ci_hi), src, "CI upper")
        nums.add(stem + "P", sig(row.p_wilcoxon), src, "two-sided Wilcoxon p")
        nums.add(stem + "Better", integer(row.better), src, "patients better")
        nums.add(stem + "Worse", integer(row.worse), src, "patients worse")
        if row.n != 22:
            nums.add(stem + "N", integer(row.n), src, "patients")
        if base != "eegnet_scratch":
            continue
        nodev = f"{what}, without sub-01, sub-03"
        nums.add(stem + "DiffNoDev", fmt(row.diff_without_dev), src, f"{nodev} ({unit})")
        nums.add(stem + "DiffNoDevCiLo", fmt(row.diff_ci_lo_without_dev), src, "CI lower")
        nums.add(stem + "DiffNoDevCiHi", fmt(row.diff_ci_hi_without_dev), src, "CI upper")
    src = "summary/ex5_live_switch_checks.json"
    checks = nums.json(src)
    low, median, high = checks["M14_sure thresholds (min, median, max)"]
    nums.add("exFiveThresholdMin", fixed2(low), src, "M14-sure: lowest threshold", "range")
    nums.add("exFiveThresholdMedian", fixed3(median), src, "M14-sure: median threshold")
    nums.add("exFiveThresholdMax", fixed2(high), src, "M14-sure: highest threshold", "range")
    below, _, above = checks["M14_sure thresholds below / at / above the gate's 0.6"]
    nums.add("exFiveThresholdBelowGate", integer(below), src, "M14-sure: thresholds below 0.6")
    nums.add("exFiveThresholdAboveGate", integer(above), src, "M14-sure: thresholds above 0.6")
    within = integer(checks["M14_sure thresholds within the limit on runs 01-02"])
    nums.add("exFiveThresholdWithinLimit", within, src, "M14-sure: within the limit on runs 01-02")
    windows = integer(checks["replayed windows of runs 03-04 per arm"]["M14"])
    nums.add("exFiveWindows", windows, src, "windows of runs 03-04 replayed per arm")
    nums.add("exFivePatients", integer(checks["patients"]), src, "patients")
    keeps = word(checks["page rule (settings page_rule)"]["page_shows"])
    nums.add("exFivePageShows", keeps, src, "the method the demo page keeps by the page rule")


def demo(nums: Numbers) -> None:
    src = "summary/demo_model.json"
    model = nums.json(src)
    candidates = model["choice"]["candidates"]
    chosen = next(c for c in candidates if c["subject"] == model["subject"])
    other = next(c for c in candidates if c["subject"] != model["subject"])
    parity = model["parity"]
    for name, value, meaning in (
        ("demoSubject", word(model["subject"]), "the demo patient"),
        ("demoMethod", word(model["method"]), "the demo's method"),
        ("demoHeldOutAcc", pct(model["held_out_bal_acc"]), "on the bundle's held-out windows (%)"),
        (
            "demoWindowAcc",
            pct(model["runner_row_bal_acc"]),
            "on every test window of runs 03-04 (%)",
        ),
        ("demoWindowTest", integer(model["runner_row_n_test"]), "test windows of runs 03-04"),
        (
            "demoChosenByAcc",
            pct(chosen["chrono_bal_acc"]),
            "the score it was chosen by (chrono, %)",
        ),
        (
            "demoCohortMedianAcc",
            pct(model["choice"]["cohort_median_chrono"]),
            "the group's median (%)",
        ),
        ("demoTieSubject", word(other["subject"]), "the patient tied with it by the rule"),
        ("demoTieAcc", pct(other["chrono_bal_acc"]), "that patient's chrono score (%)"),
        ("demoTieTrials", integer(other["whole_trials"]), "that patient's whole held-out trials"),
        ("demoTieTrialsTotal", integer(other["trials"]), "that patient's held-out trials"),
        ("demoTrials", integer(model["trials_whole"]), "whole held-out trials in the bundle"),
        ("demoTrialsTotal", integer(model["trials_total"]), "the demo patient's held-out trials"),
        (
            "demoTrainingTrials",
            integer(model["n_training_trials"]),
            "trials the model learned from",
        ),
        ("demoModelBytes", integer(parity["bytes"]), "the ONNX model (bytes)"),
        ("demoModelKb", fixed(parity["bytes"] / 1000), "the ONNX model (KB)"),
        ("demoBundleMb", fixed(model["bundle_bytes"] / 1e6), "the demo bundle (MB)"),
        ("demoOpset", integer(parity["opset"]), "ONNX opset"),
        ("demoParityRandom", sig(parity["max_abs_diff_random"]), "PyTorch vs ONNX, random input"),
        ("demoParityReal", sig(parity["max_abs_diff_real"]), "PyTorch vs ONNX, held-out windows"),
        ("demoParityMethod", sig(parity["max_abs_diff_method"]), "ONNX vs the fitted method"),
        (
            "demoQuantisationUv",
            sig(model["max_quantisation_error_uv"], 1),
            "16-bit storage error (µV)",
        ),
        ("demoClippedSamples", integer(model["clipped_samples"]), "samples clipped in storage"),
    ):
        nums.add(name, value, src, meaning)
    src = "summary/calib_demo_method.csv"
    for _, row in nums.csv(src).iterrows():
        what = f"demo method choice, S1 three classes, {row.method}: balanced accuracy"
        nums.mean_ci("demoChoice" + METHOD[row.method], row, src, what)
    src = "summary/demo_page.json"
    page = nums.json(src)
    nums.add("demoParameters", integer(page["parameters"]), src, "numbers in the ONNX model")
    for key, token, label in (
        ("move_rest", "MoveRest", "move or rest, every held-out window"),
        ("hand_finger", "HandFinger", "hand or sixth finger, the imagery windows"),
    ):
        reading = page[key]
        what = f"the demo's reading, {label}: balanced accuracy (%)"
        nums.add(f"demo{token}Acc", pct(reading["acc"]), src, what)
        nums.add(f"demo{token}Right", integer(reading["right"]), src, "windows read right")
        nums.add(f"demo{token}N", integer(reading["n"]), src, "windows")
    src = "summary/demo_inference_timing.json"
    timing = nums.json(src)
    latency, host = timing["latency_ms"], timing["machine"]
    for name, value, meaning in (
        (
            "demoInferenceMedianMs",
            fixed2(latency["median"]),
            "deciding one 4 s window, measured in P14: median (ms)",
        ),
        ("demoInferenceIqrLoMs", fixed2(latency["q1"]), "lower quartile (ms)"),
        ("demoInferenceIqrHiMs", fixed2(latency["q3"]), "upper quartile (ms)"),
        ("demoInferenceN", integer(timing["n"]), "windows timed"),
        ("demoInferenceMachine", word(host["cpu"]), "the machine timed on (CPU)"),
        ("demoInferenceOnnxruntimeVersion", word(host["onnxruntime"]), "onnxruntime version"),
        ("demoInferenceThreads", integer(host["intra_op_threads"]), "CPU threads"),
    ):
        nums.add(name, value, src, meaning)


SECTIONS = (
    dataset,
    audit,
    erd,
    rq_one,
    rq_one_b,
    deep,
    calibration,
    rq_four,
    rq_five,
    ex_one,
    ex_two,
    ex_three,
    ex_four,
    ex_five,
    demo,
)


def build(root: Path) -> Numbers:
    nums = Numbers(root)
    for section in SECTIONS:
        section(nums)
    return nums


def tex_sources(root: Path) -> list[Path]:
    sources = [root / "paper" / "main.tex", root / "report" / "main.tex"]
    for folder in ("paper/sections", "paper/college", "report/chapters", "report/frontmatter"):
        sources += sorted((root / folder).glob("*.tex"))
    return sources


def used_macros(sources: list[Path]) -> tuple[set[str], bool]:
    """Names of this scheme used in the sources, and whether a \\TBD placeholder is left."""
    used, placeholders = set(), False
    for tex in sources:
        text = tex.read_text()
        used |= set(OWNED.findall(text))
        placeholders |= "\\TBD" in text
    return used - NOT_OURS, placeholders


def missing_macros(nums: Numbers, used: set[str]) -> dict[str, str]:
    """Used but not generated, each with the tag its TBD prints."""
    missing = {name: name for name in sorted(used - set(nums.entries) - set(PENDING))}
    return missing | {name: tag for name, tag in PENDING.items() if name not in nums.entries}


def topic(name: str) -> str:
    return max((t for t in TOPICS if name.startswith(t) and name[len(t)].isupper()), key=len)


def ordered(nums: Numbers) -> list[tuple[str, Entry]]:
    """Entries grouped by topic in the order of TOPICS, each topic in the order made."""
    order = list(TOPICS)
    return sorted(nums.entries.items(), key=lambda item: order.index(topic(item[0])))


def render_tex(nums: Numbers, missing: dict[str, str], placeholders: bool) -> str:
    lines = [
        "% Generated by scripts/make_paper_numbers.py from results/summary/ and results/audit/.",
        "% Do not edit by hand. paper/generated/numbers-index.md lists every macro.",
    ]
    if missing or placeholders:
        lines.append(TBD)
    last = None
    for name, entry in ordered(nums):
        if topic(name) != last:
            last = topic(name)
            lines.append(f"% {TOPICS[last]}")
        lines.append(f"\\newcommand{{\\{name}}}{{{entry.tex}}}")
    if missing:
        lines.append("% Used in the paper or report but not generated yet: printed as TBD")
        lines += [f"\\newcommand{{\\{name}}}{{\\TBD{{{tag}}}}}" for name, tag in missing.items()]
    return "\n".join(lines) + "\n"


def render_index(nums: Numbers, missing: dict[str, str]) -> str:
    kinds = {"range": " (range)", "count": " (count)", "cell": ""}
    lines = [
        "# Index of the paper's numbers",
        "",
        "Generated by `scripts/make_paper_numbers.py` with `numbers.tex`; do not edit by hand.",
        "In LaTeX write the macro, `\\rqOneCspLdaCvLeakfreeMean\\,\\%`; slides use the value.",
        "Values carry no % sign. A CI row is the 95 % bootstrap interval of the value above it,",
        "and rows with a short meaning belong to the last full one. Sources are under",
        "`results/`. A value is one cell of its file unless marked: (range) is the smallest or",
        "largest of the cells named, (count) is counted from audit rows. The naming scheme is",
        "in the script's docstring.",
        "",
        f"{len(nums.entries)} macros. Not generated yet, printed as TBD: "
        + (", ".join(f"`\\{m}` ({tag})" for m, tag in missing.items()) or "none")
        + ".",
    ]
    last_topic = last_source = None
    for name, entry in ordered(nums):
        if topic(name) != last_topic:
            last_topic, last_source = topic(name), None
            lines += ["", f"## {TOPICS[last_topic]} (`\\{last_topic}`)"]
        if entry.source != last_source:
            last_source = entry.source
            lines += ["", f"`{entry.source}`", "", "| Macro | Value | Meaning |", "|---|---|---|"]
        lines.append(f"| `\\{name}` | {entry.plain} | {entry.meaning}{kinds[entry.kind]} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    root = get_paths().root
    generated = root / "paper" / "generated"
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=generated / "numbers.tex")
    parser.add_argument("--index", type=Path, default=generated / "numbers-index.md")
    args = parser.parse_args()

    nums = build(root)
    used, placeholders = used_macros(tex_sources(root))
    missing = missing_macros(nums, used)
    for path, text in (
        (args.out, render_tex(nums, missing, placeholders)),
        (args.index, render_index(nums, missing)),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    print(f"wrote {len(nums.entries)} macros to {args.out} and {args.index}")
    if missing:
        print("not generated yet (printed as TBD):", ", ".join(missing))


if __name__ == "__main__":
    main()
