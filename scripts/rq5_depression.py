"""RQ5: segment-level vs subject-level cross-validation in public depression EEG (P09 Study 6).

Everything is fixed in _workspace/research/preregistration-rq5.md (tag prereg-rq5-v1):

uv run python scripts/rq5_depression.py fetch       # downloads; refuses before the tag
uv run python scripts/rq5_depression.py audit       # results/audit/rq5_audit_<dataset>.csv
uv run python scripts/rq5_depression.py run         # both pipelines, both protocols, E1-E3
uv run python scripts/rq5_depression.py summarise   # results/summary/rq5_*.csv and the figure

Privacy: the primary dataset's EDF headers hold names in the patient field. Only the channel
labels, the sampling rate and the start date are read from a header; linked recordings are
found by comparing SHA-256 hashes of the patient field. Header text is never printed, logged,
stored or committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import welch
from sklearn.base import BaseEstimator, TransformerMixin

from sixthfinger.paths import current_git_sha, get_paths

log = logging.getLogger("rq5")
TAG = "prereg-rq5-v1"
CHANNELS = ["Fp1", "Fp2", "F7", "F3", "Fz", "F4", "F8", "T3", "C3", "Cz", "C4", "T4", "T5",
            "P3", "Pz", "P4", "T6", "O1", "O2"]  # fmt: skip
# Preregistration-rq5 §2.2: the HydroCel GSN-129 electrode for each name above.
MODMA_CHANNELS = {"Fp1": "E22", "Fp2": "E9", "F7": "E26", "F3": "E24", "Fz": "E11",
                  "F4": "E124", "F8": "E2", "T3": "E39", "C3": "E36", "Cz": "Cz",
                  "C4": "E104", "T4": "E115", "T5": "E50", "P3": "E52", "Pz": "E62",
                  "P4": "E92", "T6": "E101", "O1": "E70", "O2": "E83"}  # fmt: skip
SFREQ, SEG_S, SKIP_S, KEEP_S = 128, 4.0, 5.0, 300.0
P2P_MAX, P2P_MIN, MIN_SEGMENTS = 200.0, 0.5, 20  # µV, µV, segments
MUMTAZ_API = "https://api.figshare.com/v2/articles/4244171/versions/2"
MODMA_URL = (
    "https://reshare.ukdataservice.ac.uk/854301/4/854301_EEG_128Channels_Resting_Lanzhou_2015.zip"
)
MODMA_MD5 = "32b0dd6eb897c1617c19cfd529f7aad5"
MODMA_RECORD = "https://reshare.ukdataservice.ac.uk/854301/"


def data_dir() -> Path:
    return get_paths().data / "depression"


def require_tag() -> None:
    """Nothing is downloaded before the pre-registration (its gate in P09 step 4.5)."""
    root = get_paths().root
    ok = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", TAG, "HEAD"], capture_output=True
    ).returncode == 0  # fmt: skip
    if not ok:
        raise SystemExit(f"{TAG} is not an ancestor of HEAD: freeze RQ5 first")


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(url: str, dest: Path) -> int:
    """Download to dest (atomically); the HTTP status, 200 on success."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=120) as r, tmp.open("wb") as f:
            while block := r.read(1 << 20):
                f.write(block)
    except urllib.error.HTTPError as err:
        tmp.unlink(missing_ok=True)
        return err.code
    tmp.replace(dest)
    return 200


# EDF headers (primary dataset) ---------------------------------------------------------------


def edf_patient_hash(path: Path) -> str:
    """SHA-256 of the 80-byte local patient field (EDF bytes 8-88); the field is not kept."""
    with path.open("rb") as f:
        head = f.read(256)
    return hashlib.sha256(head[8:88]).hexdigest()


def edf_start_year(path: Path) -> int:
    """Recording year from the start date (EDF bytes 168-176, dd.mm.yy; 1985-2084 rule)."""
    with path.open("rb") as f:
        yy = int(f.read(256)[174:176].decode("ascii"))
    return 1900 + yy if yy >= 85 else 2000 + yy


def channel_name(label: str) -> str:
    """'EEG Fp1-LE' -> 'Fp1': drop a leading 'EEG ' and everything from the first '-'."""
    label = label.strip()
    if label.upper().startswith("EEG "):
        label = label[4:]
    return label.split("-")[0].strip()


def match_channels(labels: list[str], wanted: list[str]) -> dict[str, str] | None:
    """The file label for each wanted name (case-insensitive), or None if one is missing."""
    by_name = {channel_name(lab).lower(): lab for lab in labels}
    if not all(w.lower() in by_name for w in wanted):
        return None
    return {w: by_name[w.lower()] for w in wanted}


def mumtaz_files(meta: dict) -> pd.DataFrame:
    """The eyes-closed files of the figshare record, with group-prefixed subject ids."""
    rows = []
    for f in meta["files"]:
        name = f["name"]
        parts = name.replace(".edf", "").split()
        if len(parts) == 3 and parts[2] == "EC" and parts[0] in ("H", "MDD"):
            rows.append(dict(file=name, subject=f"{parts[0]}-{parts[1]}", group=parts[0],
                             url=f["download_url"], md5=f["computed_md5"],
                             number=int(parts[1][1:])))  # fmt: skip
    return pd.DataFrame(rows).sort_values(["group", "number"]).reset_index(drop=True)


# Segments ------------------------------------------------------------------------------------


def segment(data_uv: np.ndarray, sfreq: float, step_s: float = SEG_S) -> np.ndarray:
    """Preregistration-rq5 §3 steps 4-6 on a (19, n) µV recording at 128 Hz.

    Drop the first 5 s, keep up to 300 s, cut 4 s segments every step_s seconds, and drop a
    segment in which any channel's peak-to-peak amplitude is above 200 µV or below 0.5 µV.
    """
    start, stop = int(SKIP_S * sfreq), int((SKIP_S + KEEP_S) * sfreq)
    x = data_uv[:, start:stop]
    n, step = int(SEG_S * sfreq), int(step_s * sfreq)
    starts = range(0, x.shape[1] - n + 1, step)
    segs = np.stack([x[:, s : s + n] for s in starts]) if len(starts) else np.empty((0, *x.shape))
    p2p = segs.max(axis=-1) - segs.min(axis=-1)
    keep = (p2p <= P2P_MAX).all(axis=1) & (p2p >= P2P_MIN).all(axis=1)
    return segs[keep].astype(np.float32)


def preprocess(raw, picks: dict[str, str]):
    """§3 steps 1-3: the 19 channels, 1-40 Hz, 128 Hz, average reference; data in µV."""
    raw = raw.copy().pick(list(picks.values()))
    raw.rename_channels({v: k for k, v in picks.items()})
    raw.reorder_channels(CHANNELS)
    raw.filter(1.0, 40.0, verbose="ERROR")
    raw.resample(SFREQ, verbose="ERROR")
    raw.set_eeg_reference("average", verbose="ERROR")
    return raw.get_data() * 1e6


# Pipelines and protocols (preregistration-rq5 §4-5) ------------------------------------------

BANDS = [(1, 4), (4, 8), (8, 13), (13, 30), (30, 40)]
PIPELINES = ("bp_lr", "ts_lr")
PROTOCOLS = ("segment_cv", "subject_cv")


class LogBandPower(BaseEstimator, TransformerMixin):
    """Welch log band power per channel (2 s Hann windows, 50 % overlap): 19 x 5 features."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        f, psd = welch(X, fs=SFREQ, window="hann", nperseg=2 * SFREQ, noverlap=SFREQ, axis=-1)
        bands = [psd[..., (f >= lo) & (f < hi)].mean(axis=-1) for lo, hi in BANDS]
        return np.log(np.stack(bands, axis=-1)).reshape(len(X), -1)


def pipeline(name: str):
    from pyriemann.estimation import Covariances
    from pyriemann.tangentspace import TangentSpace
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    lr = LogisticRegression(C=1.0, max_iter=1000)
    if name == "bp_lr":
        return make_pipeline(LogBandPower(), StandardScaler(), lr)
    return make_pipeline(Covariances("oas"), TangentSpace(metric="riemann"), lr)


def splits(md: pd.DataFrame, protocol: str):
    """Ten folds; every segment is tested once. subject_cv keeps each split group whole."""
    from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

    y = (md.group == "MDD").to_numpy().astype(int)
    if protocol == "segment_cv":
        return list(StratifiedKFold(10, shuffle=True, random_state=0).split(md, y))
    cv = StratifiedGroupKFold(10, shuffle=True, random_state=0)
    return list(cv.split(md, y, groups=md.split_group.to_numpy()))


def evaluate(X: np.ndarray, md: pd.DataFrame, pipe_name: str, protocol: str) -> pd.DataFrame:
    """Out-of-fold P(MDD) for every segment; the whole pipeline is fitted inside each fold."""
    from sklearn.base import clone

    y = (md.group == "MDD").to_numpy().astype(int)
    proba = np.full(len(md), np.nan)
    template = pipeline(pipe_name)
    for train, test in splits(md, protocol):
        if protocol == "subject_cv" and set(md.split_group.iloc[train]) & set(
            md.split_group.iloc[test]
        ):
            raise AssertionError("a split group on both sides of a subject-level split")
        model = clone(template).fit(X[train], y[train])
        proba[test] = model.predict_proba(X[test])[:, 1]
    if np.isnan(proba).any():
        raise AssertionError("a segment was never tested")
    return md.assign(p_mdd=proba, correct=(proba > 0.5) == (y == 1))


def per_subject(pred: pd.DataFrame) -> pd.DataFrame:
    """a = share of a subject's segments assigned to its own group (preregistration-rq5 §1)."""
    return pred.groupby(["subject", "group", "split_group"], as_index=False).agg(
        a=("correct", "mean"), n_segments=("correct", "size")
    )


def subject_balanced_accuracy(values: pd.DataFrame) -> float:
    return float(values.groupby("group").a.mean().mean())


def fetch(_args) -> None:
    require_tag()
    out = data_dir() / "mumtaz"
    out.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(MUMTAZ_API, timeout=60) as r:
        meta = json.load(r)
    (out / "figshare_record.json").write_text(json.dumps(meta, indent=1))
    files = mumtaz_files(meta)
    status = []
    for f in files.itertuples():
        dest = out / f.file
        code = 200 if dest.exists() and md5(dest) == f.md5 else download(f.url, dest)
        ok = code == 200 and md5(dest) == f.md5
        status.append(dict(file=f.file, http=code, md5_ok=ok))
        log.info("%s: %s", f.file, "ok" if ok else f"failed ({code})")
    pd.DataFrame(status).to_csv(out / "download_status.csv", index=False)
    modma = data_dir() / "modma"
    modma.mkdir(parents=True, exist_ok=True)
    zip_path = modma / MODMA_URL.rsplit("/", 1)[1]
    download(MODMA_RECORD, modma / "reshare_record.html")  # the access terms on the day
    if not (zip_path.exists() and md5(zip_path) == MODMA_MD5):
        code = download(MODMA_URL, zip_path)
        log.info("MODMA zip: %s", code)
    log.info("MODMA zip md5 ok: %s", md5(zip_path) == MODMA_MD5)


def _kept(subject, group, data_uv, **extra) -> dict:
    return dict(subject=subject, group=group, segs=segment(data_uv, SFREQ),
                overlap=segment(data_uv, SFREQ, step_s=SEG_S / 2), **extra)  # fmt: skip


def audit_mumtaz() -> tuple[pd.DataFrame, list[dict]]:
    """One row per eyes-closed file; and the kept recordings' segments with their subject."""
    import mne

    out = data_dir() / "mumtaz"
    files = mumtaz_files(json.loads((out / "figshare_record.json").read_text()))
    status = pd.read_csv(out / "download_status.csv").set_index("file")
    rows, kept, seen_md5, hashes = [], [], {}, {}
    for f in files.itertuples():
        row = dict(dataset="mumtaz", file=f.file, subject=f.subject, group=f.group, kept=False)
        path = out / f.file
        if not status.loc[f.file, "md5_ok"]:
            rows.append({**row, "reason": f"not downloadable (HTTP {status.loc[f.file, 'http']})"})
            continue
        if f.md5 in seen_md5:
            rows.append({**row, "reason": f"byte-identical to {seen_md5[f.md5]}"})
            continue
        seen_md5[f.md5] = f.subject
        raw = mne.io.read_raw_edf(path, preload=True, verbose="ERROR")
        picks = match_channels(raw.ch_names, CHANNELS)
        if picks is None:
            rows.append({**row, "reason": "a required channel is missing"})
            continue
        year = edf_start_year(path)
        k = _kept(f.subject, f.group, preprocess(raw, picks), year=year)
        duration = raw.n_times / raw.info["sfreq"]
        del raw  # its info holds the header's patient fields; nothing of it is kept
        hashes[f.subject] = edf_patient_hash(path)
        row.update(year=year, duration_s=round(duration, 1), n_segments=len(k["segs"]))
        if len(k["segs"]) < MIN_SEGMENTS:
            rows.append({**row, "reason": f"fewer than {MIN_SEGMENTS} accepted segments"})
            continue
        rows.append({**row, "kept": True, "reason": ""})
        kept.append(k)
    audit = pd.DataFrame(rows)
    # Linked recordings: the same patient field (compared by hash) is one split group.
    by_hash: dict[str, list[str]] = {}
    for subject, h in hashes.items():
        by_hash.setdefault(h, []).append(subject)
    group_of = {s: "+".join(sorted(m)) for m in by_hash.values() for s in m}
    audit["split_group"] = audit.subject.map(group_of).fillna(audit.subject)
    return audit, kept


def read_xlsx(path: Path) -> pd.DataFrame:
    """The first sheet of an .xlsx (a zip of XML files), with the standard library only."""
    import re
    import xml.etree.ElementTree as ET
    import zipfile

    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as z:
        shared = [
            "".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t"))
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns)
        ] if "xl/sharedStrings.xml" in z.namelist() else []  # fmt: skip
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = []
    for r in sheet.find("m:sheetData", ns).findall("m:row", ns):
        cells = {}
        for c in r.findall("m:c", ns):
            v = c.find("m:v", ns)
            if v is not None:
                col = re.match(r"[A-Z]+", c.get("r")).group()
                cells[col] = shared[int(v.text)] if c.get("t") == "s" else v.text
        rows.append(cells)
    header = rows[0]
    return pd.DataFrame([{header[k]: r.get(k) for k in header} for r in rows[1:]])


def audit_modma() -> tuple[pd.DataFrame, list[dict]]:
    import mne
    import scipy.io as sio

    folder = data_dir() / "modma" / "EEG_128channels_resting_lanzhou_2015"
    info = read_xlsx(next(folder.glob("subjects_information*.xlsx")))
    info["subject id"] = info["subject id"].str.zfill(8)
    labels = info.set_index("subject id")
    rows, kept, seen_md5 = [], [], {}
    for path in sorted(folder.glob("*.mat")):
        sid = path.name[:8]
        if sid not in labels.index:
            rows.append(dict(dataset="modma", file=path.name, subject=sid, kept=False,
                             reason="not in the participant sheet"))  # fmt: skip
            continue
        meta = labels.loc[sid]
        group = {"MDD": "MDD", "HC": "H"}[meta["type"]]
        row = dict(dataset="modma", file=path.name, subject=f"{group}-{sid}", group=group,
                   gad7=float(meta["GAD-7"]), kept=False)  # fmt: skip
        digest = md5(path)
        if digest in seen_md5:
            rows.append({**row, "reason": f"byte-identical to {seen_md5[digest]}"})
            continue
        seen_md5[digest] = row["subject"]
        m = sio.loadmat(path)
        key = next(k for k in m if not k.startswith("__") and k.startswith("a"))
        sfreq = float(m["samplingRate"].ravel()[0])
        data = m[key]  # (129, n): E1..E128, then Cz, the recording reference; µV
        if data.shape[0] != 129:
            rows.append({**row, "reason": f"{data.shape[0]} channels, expected 129"})
            continue
        index = {f"E{i + 1}": i for i in range(128)} | {"Cz": 128}
        x = data[[index[MODMA_CHANNELS[c]] for c in CHANNELS]] * 1e-6
        raw = mne.io.RawArray(x, mne.create_info(CHANNELS, sfreq, "eeg"), verbose="ERROR")
        k = _kept(row["subject"], group, preprocess(raw, {c: c for c in CHANNELS}),
                  gad7=row["gad7"])  # fmt: skip
        row.update(duration_s=round(data.shape[1] / sfreq, 1), n_segments=len(k["segs"]))
        if len(k["segs"]) < MIN_SEGMENTS:
            rows.append({**row, "reason": f"fewer than {MIN_SEGMENTS} accepted segments"})
            continue
        rows.append({**row, "kept": True, "reason": ""})
        kept.append(k)
    audit = pd.DataFrame(rows)
    audit["split_group"] = audit.subject  # one recording per person; nothing to link
    return audit, kept


def save_segments(name: str, audit: pd.DataFrame, kept: list[dict]) -> None:
    out = data_dir() / "derived"
    out.mkdir(parents=True, exist_ok=True)
    split = audit.set_index("subject").split_group
    for kind in ("segs", "overlap"):
        X = np.concatenate([k[kind] for k in kept])
        md = pd.concat(
            [pd.DataFrame({"subject": k["subject"], "group": k["group"],
                           "split_group": split[k["subject"]], "segment": range(len(k[kind])),
                           **{c: k[c] for c in ("year", "gad7") if c in k}})
             for k in kept],
            ignore_index=True,
        )  # fmt: skip
        tag = "" if kind == "segs" else "_overlap"
        np.save(out / f"{name}{tag}_X.npy", X)
        md.to_parquet(out / f"{name}{tag}_segments.parquet", index=False)


def load_segments(name: str, overlap: bool = False) -> tuple[np.ndarray, pd.DataFrame]:
    tag = "_overlap" if overlap else ""
    out = data_dir() / "derived"
    return np.load(out / f"{name}{tag}_X.npy"), pd.read_parquet(
        out / f"{name}{tag}_segments.parquet"
    )


def audit(_args) -> None:
    require_tag()
    paths = get_paths()
    for name, fn in (("mumtaz", audit_mumtaz), ("modma", audit_modma)):
        table, kept = fn()
        table.assign(git_sha=current_git_sha()).to_csv(
            paths.audit / f"rq5_audit_{name}.csv", index=False
        )
        save_segments(name, table, kept)
        log.info("%s: %d files, %d kept (%s)", name, len(table), table.kept.sum(),
                 table[table.kept].group.value_counts().to_dict())  # fmt: skip


# Run and summarise -------------------------------------------------------------------------

DATASETS = ("mumtaz", "modma")
N_NULL = 20


def shuffled(md: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Diagnoses shuffled across split groups, group sizes kept (preregistration-rq5 §6)."""
    groups = md.drop_duplicates("split_group").set_index("split_group").group
    perm = pd.Series(np.random.default_rng(seed).permutation(groups.to_numpy()), groups.index)
    return md.assign(group=md.split_group.map(perm))


def run(_args) -> None:
    require_tag()
    paths = get_paths()
    out = paths.runs / "rq5"
    out.mkdir(parents=True, exist_ok=True)
    sha = current_git_sha()  # the code this run starts from
    frames = []
    for name in DATASETS:
        X, md = load_segments(name)
        for pipe in PIPELINES:
            for protocol in PROTOCOLS:
                log.info("%s %s %s", name, pipe, protocol)
                v = per_subject(evaluate(X, md, pipe, protocol))
                frames.append(
                    v.assign(dataset=name, pipeline=pipe, protocol=protocol, analysis="main")
                )
        # E2: overlapping segments under segment_cv.
        Xo, mdo = load_segments(name, overlap=True)
        for pipe in PIPELINES:
            v = per_subject(evaluate(Xo, mdo, pipe, "segment_cv"))
            frames.append(
                v.assign(dataset=name, pipeline=pipe, protocol="segment_cv", analysis="E2_overlap")
            )
        if name == "mumtaz":
            # No-signal demonstration: shuffled diagnoses, ts_lr.
            for seed in range(N_NULL):
                ms = shuffled(md, seed)
                for protocol in PROTOCOLS:
                    v = per_subject(evaluate(X, ms, "ts_lr", protocol))
                    frames.append(v.assign(dataset=name, pipeline="ts_lr", protocol=protocol,
                                           analysis=f"null_{seed}"))  # fmt: skip
            # E1: one recording year, if both groups have at least 10 subjects in it.
            years = md.drop_duplicates("subject").pivot_table(
                index="year", columns="group", values="subject", aggfunc="count", fill_value=0
            )
            for year, counts in years.iterrows():
                if (counts >= 10).all():
                    rows = (md.year == year).to_numpy()
                    for pipe in PIPELINES:
                        sub = md[rows].reset_index(drop=True)
                        v = per_subject(evaluate(X[rows], sub, pipe, "subject_cv"))
                        frames.append(v.assign(dataset=name, pipeline=pipe, protocol="subject_cv",
                                               analysis=f"E1_year_{year}"))  # fmt: skip
        if name == "modma":
            # E3: GAD-7 >= 10 vs < 10 over all participants, ts_lr, if both sides >= 10.
            ma = md.assign(group=np.where(md.gad7 >= 10, "MDD", "H"))
            sides = ma.drop_duplicates("subject").group.value_counts()
            if len(sides) == 2 and (sides >= 10).all():
                for protocol in PROTOCOLS:
                    v = per_subject(evaluate(X, ma, "ts_lr", protocol))
                    frames.append(v.assign(dataset=name, pipeline="ts_lr", protocol=protocol,
                                           analysis="E3_gad7"))  # fmt: skip
            else:
                log.info("E3 not run: GAD-7 sides %s", sides.to_dict())
    values = pd.concat(frames, ignore_index=True).assign(git_sha=sha)
    values.to_parquet(out / "subject_values.parquet", index=False)
    log.info("rq5 per-subject values in %s", out)


def stratified_inflation_ci(a_seg, a_sub, groups, n=10_000, seed=12345):
    """Mean inflation and its 95 % CI, resampling subjects within each group."""
    rng = np.random.default_rng(seed)
    a_seg, a_sub, groups = map(np.asarray, (a_seg, a_sub, groups))
    idx = {g: np.flatnonzero(groups == g) for g in np.unique(groups)}

    def ba(a, take):
        return np.mean([a[t].mean() for t in take])

    point = ba(a_seg, idx.values()) - ba(a_sub, idx.values())
    boots = np.empty(n)
    for b in range(n):
        take = [rng.choice(i, size=len(i), replace=True) for i in idx.values()]
        boots[b] = ba(a_seg, take) - ba(a_sub, take)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return float(point), float(lo), float(hi)


def summarise(_args) -> None:
    from sixthfinger.evaluation.stats import paired_test
    from sixthfinger.evaluation.summary import holm_family

    paths = get_paths()
    v = pd.read_parquet(paths.runs / "rq5" / "subject_values.parquet")
    v.to_csv(paths.results / "summary" / "rq5_subject_values.csv", index=False, float_format="%.6g")
    main = v[v.analysis == "main"]
    table, stats = [], []
    for (name, pipe), g in main.groupby(["dataset", "pipeline"]):
        w = g.pivot_table(index=["subject", "group"], columns="protocol", values="a").reset_index()
        for protocol in PROTOCOLS:
            sub = g[g.protocol == protocol]
            table.append(dict(dataset=name, pipeline=pipe, protocol=protocol,
                              n_subjects=len(sub), ba=subject_balanced_accuracy(sub),
                              diagnosed=float((sub.a > 0.5).mean())))  # fmt: skip
        point, lo, hi = stratified_inflation_ci(w.segment_cv, w.subject_cv, w.group)
        res = paired_test(w.segment_cv.to_numpy(), w.subject_cv.to_numpy(), alternative="greater")
        stats.append(dict(hypothesis="H5" if name == "mumtaz" else "H5b", dataset=name,
                          pipeline=pipe, inflation_points=point * 100, ci_lo_points=lo * 100,
                          ci_hi_points=hi * 100, **{k: res[k] for k in
                          ("n", "median_diff", "mean_diff", "W", "p", "r_rb")}))  # fmt: skip
    stats = pd.DataFrame(stats)
    for _, g in stats.groupby("dataset"):
        adj = holm_family(dict(zip(g.pipeline, g.p, strict=True)))
        n_sig = sum(p < 0.05 for p in adj.values())
        stats.loc[g.index, "p_holm"] = [adj[p] for p in g.pipeline]
        stats.loc[g.index, "category"] = (
            "supported" if n_sig == 2 else "partial" if n_sig else "inconclusive"
        )
    summary = paths.results / "summary"
    pd.DataFrame(table).to_csv(summary / "rq5_table.csv", index=False, float_format="%.6g")
    stats.to_csv(summary / "rq5_stats.csv", index=False, float_format="%.6g")
    null = v[v.analysis.str.startswith("null_")]
    null_ba = (
        null.groupby(["analysis", "protocol"])
        .apply(subject_balanced_accuracy, include_groups=False)
        .rename("ba")
        .reset_index()
    )
    null_ba.to_csv(summary / "rq5_null.csv", index=False, float_format="%.6g")
    ex = v[v.analysis.str.startswith("E")]
    ex_ba = (
        ex.groupby(["analysis", "dataset", "pipeline", "protocol"])
        .apply(subject_balanced_accuracy, include_groups=False)
        .rename("ba")
        .reset_index()
    )
    ex_ba.to_csv(summary / "rq5_exploratory.csv", index=False, float_format="%.6g")
    figure(main, null_ba, paths.root / "docs" / "figures")
    log.info("rq5 summaries in %s", summary)


def figure(main: pd.DataFrame, null_ba: pd.DataFrame, figures: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from sixthfinger.viz.plots import ACCENT, SUBJECT_GREY, save, use_style

    use_style()
    fig, axes = plt.subplots(1, 4, figsize=(7.6, 2.9), sharey=True)
    panels = [(d, p) for d in DATASETS for p in PIPELINES]
    for ax, (name, pipe) in zip(axes, panels, strict=True):
        g = main[(main.dataset == name) & (main.pipeline == pipe)]
        w = g.pivot_table(index="subject", columns="protocol", values="a")
        for _, r in w.iterrows():
            ax.plot([0, 1], [r.segment_cv, r.subject_cv], color=SUBJECT_GREY, lw=0.6)
        means = [subject_balanced_accuracy(g[g.protocol == p]) for p in PROTOCOLS]
        ax.plot([0, 1], means, color=ACCENT, marker="o", lw=2)
        if name == "mumtaz" and pipe == "ts_lr" and len(null_ba):
            for i, p in enumerate(PROTOCOLS):
                q = null_ba[null_ba.protocol == p].ba
                ax.fill_between([i - 0.15, i + 0.15], q.min(), q.max(), color="orange", alpha=0.3)
        ax.axhline(0.5, color="0.5", lw=0.8)
        ax.set_xticks([0, 1], ["segment\nCV", "subject\nCV"], fontsize=7)
        ax.set_xlim(-0.35, 1.35)
        ax.set_title(f"{name}, {pipe}", fontsize=8)
    axes[0].set_ylabel("share of a subject's segments\nassigned to its group")
    save(fig, figures, "rq5_leakage_depression")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("fetch", fetch), ("audit", audit), ("run", run), ("summarise", summarise)):
        sub.add_parser(name).set_defaults(fn=fn)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    args.fn(args)


if __name__ == "__main__":
    main()
