"""Exploratory, added after the results: the raw recordings for AH vs SF (T1_ah_vs_sf).

uv run python scripts/ex2_slow_waves.py --part fetch    # raw pre runs, cut and deleted (1.7 GB)
uv run python scripts/ex2_slow_waves.py --part align    # every published window to a raw cue
uv run python scripts/ex2_slow_waves.py --part shifts   # the shifted windows in seconds (stored)
uv run python scripts/ex2_slow_waves.py --part score
uv run python scripts/ex2_slow_waves.py --part summary
uv run python scripts/ex2_slow_waves.py --part posthoc  # added after the scores were seen

Do slow waves below 3 Hz, or all 59 EEG channels, help? `pre`, learn runs 01-02, test runs
03-04 (only scored). Settings: configs/experiments/ex2_slow_waves.yaml, fixed before any score.
`fetch` reads one raw run at a time out of the remote sourcedata.zip by HTTP range requests,
cuts the windows every arm needs into data/derived/raw_windows/ (1.0 GB) and deletes the run;
it resumes. `score` refuses to start until `align` has passed. `--part repro --research DIR`
compares every output with the exploratory run's. Writes results/summary/ex2_slow_waves_*.
"""

from __future__ import annotations

import os

# One BLAS thread, as in the exploratory run, so the fits repeat to the last digit.
for _var in (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"
):  # fmt: skip
    os.environ.setdefault(_var, "1")

import argparse  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import shutil  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import mne  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.signal import correlate  # noqa: E402
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis  # noqa: E402

import sixthfinger.models  # noqa: E402, F401  (registers every method)
from sixthfinger.config import load_data_config  # noqa: E402
from sixthfinger.data.channels import (  # noqa: E402
    CENTRAL_14,
    CHANNELS_40,
    PARIETO_OCCIPITAL_5,
    subject_group,
)
from sixthfinger.data.epochs import assign_trials, load_windows, recut  # noqa: E402
from sixthfinger.data.loading import list_processed_runs, read_eeglab_mat  # noqa: E402
from sixthfinger.evaluation import exploratory as ex  # noqa: E402
from sixthfinger.evaluation.leakage import assert_no_leakage  # noqa: E402
from sixthfinger.evaluation.metrics import score  # noqa: E402
from sixthfinger.evaluation.runner import method_params  # noqa: E402
from sixthfinger.evaluation.stats import bootstrap_ci, paired_test  # noqa: E402
from sixthfinger.models.registry import Batch, make_method  # noqa: E402
from sixthfinger.paths import current_git_sha, get_paths  # noqa: E402

mne.set_log_level("ERROR")

NAME = "ex2_slow_waves"
CONFIG = ex.settings(NAME)
RUNS_DIR = get_paths().runs / NAME
CACHE = get_paths().derived / "raw_windows"
TMP = CACHE / "_download"
ALIGN_DIR = CACHE / "align"

SFREQ = 250.0
RUNS = ["01", "02", "03", "04"]
# The amplifier's 64 rows: 59 EEG electrodes, then ECG and four EOG. CPz was the online
# reference, so it is not among them; it is restored as a row of zeros.
RAW_CHANNELS = [
    "Fpz", "Fp1", "Fp2", "AF3", "AF4", "AF7", "AF8", "Fz", "F1", "F2", "F3", "F4", "F5", "F6",
    "F7", "F8", "FCz", "FC1", "FC2", "FC3", "FC4", "FC5", "FC6", "FT7", "FT8", "Cz", "C1", "C2",
    "C3", "C4", "C5", "C6", "T7", "T8", "CP1", "CP2", "CP3", "CP4", "CP5", "CP6", "TP7", "TP8",
    "Pz", "P3", "P4", "P5", "P6", "P7", "P8", "POz", "PO3", "PO4", "PO5", "PO6", "PO7", "PO8",
    "Oz", "O1", "O2", "ECG", "HEOR", "HEOL", "VEOU", "VEOL",
]  # fmt: skip
EEG_59 = RAW_CHANNELS[:59]
EOG_4 = ["HEOR", "HEOL", "VEOU", "VEOL"]
EEG_60 = [*EEG_59, "CPz"]

# Stored windows: [0, 5) s after the cue at 250 Hz, and [-1, 5) s at 10 Hz for slow waves.
STORE_T0, STORE_N = 0.0, 1250
SLOW_T0, SLOW_N, DECIM = -1.0, 60, 25
CODE_LABEL = {"2": 1, "3": 2}

log = logging.getLogger(NAME)


def out(name: str) -> Path:
    return get_paths().summary / f"{NAME}_{name}"


def setup_logging() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for h in (logging.StreamHandler(), logging.FileHandler(RUNS_DIR / "run.log")):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)


def pre_subjects() -> list[str]:
    return ex.pre_subjects(load_data_config())


def cached_rows(subject: str) -> tuple[np.ndarray, pd.DataFrame]:
    paths, cfg = get_paths(), load_data_config()
    X, md = load_windows(paths.epochs, cfg, subjects=[subject], sessions=["pre"], labels=[1, 2])
    return X, md.reset_index(drop=True)


def check_disk(wait_s: int = 1200) -> None:
    # Other programs' swap moves free space by gigabytes within a minute on this machine, so a
    # low reading is waited out for a while before giving up; nothing is downloaded below 2 GB.
    waited = 0
    while (free := shutil.disk_usage(CACHE).free) < 2e9:
        if waited >= wait_s:
            raise SystemExit(f"free disk {free / 1e9:.2f} GB is below 2 GB; stopping")
        if waited % 300 == 0:
            log.info("free disk %.2f GB is below 2 GB; waiting", free / 1e9)
        time.sleep(30)
        waited += 30


def download(members: list[str]) -> None:
    from remotezip import RemoteZip

    url = load_data_config().figshare.url_for("sourcedata")
    for attempt in range(1, 7):
        try:
            with RemoteZip(url, timeout=60) as z:
                for name in members:
                    z.extract(name, TMP)
                    if (TMP / name).stat().st_size != z.getinfo(name).file_size:
                        raise OSError(f"{name}: size differs from the zip index")
            return
        except Exception as err:  # requests, remotezip and zipfile raise different errors
            log.warning("download attempt %d failed: %r", attempt, err)
            time.sleep(min(60, 10 * attempt))
    raise SystemExit(f"could not download {members}")


def raw_events(raw: mne.io.BaseRaw) -> tuple[list[str], np.ndarray]:
    ann = raw.annotations
    samples = np.rint(np.asarray(ann.onset) * raw.info["sfreq"]).astype(np.int64)
    return [str(d).strip() for d in ann.description], samples


def median_r(a: np.ndarray, b: np.ndarray) -> float:
    """Median over channels of Pearson r between two (channels, times) arrays."""
    a = a - a.mean(axis=1, keepdims=True)
    b = b - b.mean(axis=1, keepdims=True)
    den = np.sqrt((a * a).sum(axis=1) * (b * b).sum(axis=1))
    return float(np.median((a * b).sum(axis=1) / np.where(den > 0, den, np.nan)))


def check_alignment(
    subject: str, run: str, eeg60: np.ndarray, codes: list[str], samples: np.ndarray,
    cached: set[tuple[int, int]],
) -> tuple[pd.DataFrame, np.ndarray]:  # fmt: skip
    """First pass, same run number at lag 0: one row per published cue, and for every raw cue
    the published trial_in_run it matched (-1 if none)."""
    info = next(r for r in list_processed_runs(get_paths().processed)
                if r.subject == subject and r.session == "pre" and r.run == run)  # fmt: skip
    rec = read_eeglab_mat(info.path)
    i43 = [EEG_60.index(c) for c in rec.ch_names]
    raw43 = eeg60[i43] - eeg60[i43].mean(axis=0, keepdims=True)
    raw43 = mne.filter.filter_data(raw43, SFREQ, 5.0, 35.0)
    k40 = [rec.ch_names.index(c) for c in CHANNELS_40]
    pub = rec.data_uv[k40].astype(np.float64)
    raw40 = raw43[k40]
    s0, n = 250, 1000  # [1, 5) s

    trials = assign_trials(rec.event_codes)
    events = zip(rec.event_codes, rec.event_samples, trials, strict=True)
    pub_cues = [(c, int(s), t) for c, s, t in events if c in CODE_LABEL]
    raw_cues = [(c, int(s)) for c, s in zip(codes, samples, strict=True) if c in CODE_LABEL]
    matched_trial = np.full(len(raw_cues), -1, dtype=np.int64)

    def pub_win(s):
        return pub[:, s + s0 : min(s + s0 + n, pub.shape[1])]

    def raw_win(s, lag=0, length=n):
        a = s + s0 + lag
        return raw40[:, a : a + length] if a >= 0 and a + length <= raw40.shape[1] else None

    rows = []
    for j, (code, ps, trial) in enumerate(pub_cues):
        label = CODE_LABEL[code]
        if (trial, label) not in cached:
            # A published window that crosses a cut mixes two stretches of signal and matches
            # nothing; no arm uses it, so it is listed but not matched.
            rows.append(dict(subject=subject, run=int(run), pub_cue=j, code=code,
                             trial_in_run=trial, cached=False, pub_sample=ps,
                             raw_cue=-1))  # fmt: skip
            continue
        p = pub_win(ps)
        cands = []
        for i, (rcode, rs) in enumerate(raw_cues):
            r = raw_win(rs, length=p.shape[1])
            if rcode == code and r is not None:
                cands.append((median_r(r, p), i))
        cands.sort(reverse=True)
        best_r, best_i = cands[0]
        second = cands[1][0] if len(cands) > 1 else np.nan
        rs = raw_cues[best_i][1]
        lags = np.arange(-25, 26)
        lag_r = [median_r(w, p) if (w := raw_win(rs, int(lag), p.shape[1])) is not None
                 else -np.inf for lag in lags]  # fmt: skip
        rows.append(dict(subject=subject, run=int(run), pub_cue=j, code=code,
                         trial_in_run=trial, cached=True,
                         pub_sample=ps, raw_cue=best_i, raw_sample=rs, offset=rs - ps,
                         window_len=p.shape[1], direct_r=best_r, second_r=second,
                         best_lag=int(lags[int(np.argmax(lag_r))]),
                         frac_ch_r_gt_09=np.nan, mapped_r=np.nan))  # fmt: skip
        matched_trial[best_i] = trial

    df = pd.DataFrame(rows)
    pool = df.index[df.cached & (df.window_len == n)].to_numpy()
    raw_w = {k: raw43[:, int(df.raw_sample[k]) + s0 : int(df.raw_sample[k]) + s0 + n]
             for k in pool}  # fmt: skip
    for k in pool:
        if raw_w[k].shape[1] != n:
            continue
        fit = [j for j in pool if j != k]
        R = np.hstack([raw_w[j] for j in fit])
        P = np.hstack([pub_win(int(df.pub_sample[j])) for j in fit])
        M = np.linalg.lstsq(R.T, P.T, rcond=None)[0].T
        p = pub_win(int(df.pub_sample[k]))
        df.loc[k, "mapped_r"] = median_r(M @ raw_w[k], p)
        a = raw40[:, int(df.raw_sample[k]) + s0 : int(df.raw_sample[k]) + s0 + n]
        a, b = a - a.mean(1, keepdims=True), p - p.mean(1, keepdims=True)
        r_ch = (a * b).sum(1) / np.sqrt((a * a).sum(1) * (b * b).sum(1))
        df.loc[k, "frac_ch_r_gt_09"] = float((r_ch > 0.9).mean())
    df["n_raw_cues"] = len(raw_cues)
    df["n_pub_cues"] = len(pub_cues)
    df["raw_order"] = "".join(c for c, _ in raw_cues)
    df["pub_order"] = "".join(c for c, _, _ in pub_cues)
    return df, matched_trial


def cut(x: np.ndarray, starts: np.ndarray, n: int, step: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Windows x[:, s : s + n*step : step] for every start; invalid ones left at zero."""
    windows = np.zeros((len(starts), x.shape[0], n), np.float32)
    ok = (starts >= 0) & (starts + n * step <= x.shape[1])
    for k in np.flatnonzero(ok):
        windows[k] = x[:, starts[k] : starts[k] + n * step : step]
    return windows, ok


def process_run(subject: str, run: str, cached: set[tuple[int, int]]) -> None:
    dest = CACHE / f"{subject}_pre_{run}.npz"
    if dest.exists():
        return
    check_disk()
    t0 = time.perf_counter()
    stem = f"{subject}/pre/{subject}_{subject_group(subject)}_pre_{run}_original"
    download([stem + ".set", stem + ".fdt"])
    t_dl = time.perf_counter() - t0
    raw = mne.io.read_raw_eeglab(TMP / f"{stem}.set", preload=True, uint16_codec="latin1")
    shutil.rmtree(TMP / subject)
    if raw.ch_names != RAW_CHANNELS or raw.info["sfreq"] != SFREQ:
        raise SystemExit(f"{stem}: unexpected channels or sampling rate")
    data = raw.get_data()  # volts, float64
    codes, samples = raw_events(raw)
    eeg60 = np.vstack([data[:59], np.zeros((1, data.shape[1]))])
    eeg60 -= eeg60.mean(axis=1, keepdims=True)
    eog = data[[RAW_CHANNELS.index(c) for c in EOG_4]]
    eog = eog - eog.mean(axis=1, keepdims=True)

    first, matched = check_alignment(subject, run, eeg60 * 1e6, codes, samples, cached)
    ALIGN_DIR.mkdir(parents=True, exist_ok=True)
    first.to_csv(ALIGN_DIR / f"{subject}_pre_{run}.csv", index=False)

    cue_codes = np.array([c for c in codes if c in CODE_LABEL])
    cue_samples = np.array([s for c, s in zip(codes, samples, strict=True) if c in CODE_LABEL],
                           np.int64)  # fmt: skip
    f830 = mne.filter.filter_data(eeg60, SFREQ, 8.0, 30.0)
    f535 = mne.filter.filter_data(eeg60, SFREQ, 5.0, 35.0)
    slow = mne.filter.filter_data(eeg60, SFREQ, 0.1, 3.0)
    eog_slow = mne.filter.filter_data(eog, SFREQ, 0.1, 3.0)
    st = cue_samples + round(STORE_T0 * SFREQ)
    ss = cue_samples + round(SLOW_T0 * SFREQ)
    w830, ok1 = cut(f830, st, STORE_N)
    w535, _ = cut(f535, st, STORE_N)
    slow10, ok2 = cut(slow, ss, SLOW_N, DECIM)
    eog10, _ = cut(eog_slow, ss, SLOW_N, DECIM)
    mad = np.median(np.abs(f830 - np.median(f830, axis=1, keepdims=True)), axis=1)
    np.savez(dest.with_suffix(".tmp.npz"), codes=cue_codes, samples=cue_samples,
             matched_trial=matched, valid=ok1 & ok2, w830=w830, w535=w535, slow10=slow10,
             eog10=eog10, mad830=mad.astype(np.float32), ch_names=np.array(EEG_60))  # fmt: skip
    dest.with_suffix(".tmp.npz").replace(dest)
    log.info("%s pre %s: %d raw cues, %d published, %d cached; median mapped r %.3f; "
             "download %.0f s, total %.0f s; free %.1f GB", subject, run, len(cue_codes),
             len(first), int(first.cached.sum()), first.mapped_r.median(), t_dl,
             time.perf_counter() - t0, shutil.disk_usage(CACHE).free / 1e9)  # fmt: skip


def part_fetch(subjects: list[str]) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    for subject in subjects:
        _, md = cached_rows(subject)
        for run in RUNS:
            rows = md[md.run == int(run)]
            cached = set(zip(rows.trial_in_run.astype(int), rows.label.astype(int), strict=True))
            process_run(subject, run, cached)


def unit_rows(a: np.ndarray) -> np.ndarray:
    a = a - a.mean(axis=-1, keepdims=True)
    return a / np.linalg.norm(a, axis=-1, keepdims=True)


def published_cues(subject: str) -> dict[str, dict]:
    """Per published run: cue codes in order, and for every (trial_in_run, label) the cue's
    order, sample and whether a cut lies between the cue and the [1, 5) window."""
    files = {r.run: r.path for r in list_processed_runs(get_paths().processed)
             if r.subject == subject and r.session == "pre"}  # fmt: skip
    cues_by_run = {}
    for run in RUNS:
        rec = read_eeglab_mat(files[run])
        codes = np.array(rec.event_codes)
        bounds = rec.event_samples[codes == "boundary"]
        cues, order = {}, []
        trials = assign_trials(rec.event_codes)
        for c, s, t in zip(rec.event_codes, rec.event_samples, trials, strict=True):
            if c in CODE_LABEL:
                cut_before = bool(np.any((bounds > s) & (bounds <= s + 250)))
                cues[(t, CODE_LABEL[c])] = dict(pub_cue=len(order), pub_sample=int(s),
                                                cut_before_window=cut_before)  # fmt: skip
                order.append(c)
        cues_by_run[run] = dict(cues=cues, order="".join(order))
    return cues_by_run


def raw_cue_windows(subject: str) -> pd.DataFrame:
    frames = []
    for run in RUNS:
        with np.load(CACHE / f"{subject}_pre_{run}.npz") as z:
            frames.append(pd.DataFrame({"raw_run": run, "raw_cue": np.arange(len(z["codes"])),
                                        "code": z["codes"].astype(str)}))  # fmt: skip
    return pd.concat(frames, ignore_index=True)


def continuous_raw43(subject: str, raw_run: str, i43: list[int]) -> np.ndarray:
    """One raw run again as the alignment compares it: 43 channels, common average, 5-35 Hz,
    microvolts. Downloaded, read and deleted."""
    check_disk()
    stem = f"{subject}/pre/{subject}_{subject_group(subject)}_pre_{raw_run}_original"
    download([stem + ".set", stem + ".fdt"])
    raw = mne.io.read_raw_eeglab(TMP / f"{stem}.set", preload=True, uint16_codec="latin1")
    shutil.rmtree(TMP / subject)
    data = raw.get_data() * 1e6
    eeg60 = np.vstack([data[:59], np.zeros((1, data.shape[1]))])
    eeg60 -= eeg60.mean(axis=1, keepdims=True)
    x = eeg60[i43] - eeg60[i43].mean(axis=0, keepdims=True)
    return mne.filter.filter_data(x, SFREQ, 5.0, 35.0)


def sliding_median_r(y: np.ndarray, p: np.ndarray, lo: int, hi: int) -> np.ndarray:
    """Median over channels of r between p (channels, n) and y[:, s : s + n], s = lo..hi."""
    n = p.shape[1]
    seg = y[:, lo : hi + n]
    r = np.empty((p.shape[0], hi - lo + 1))
    for ch in range(p.shape[0]):
        a, b = seg[ch], p[ch] - p[ch].mean()
        cc = correlate(a, b, mode="valid", method="fft")
        cs = np.concatenate([[0.0], np.cumsum(a)])
        cs2 = np.concatenate([[0.0], np.cumsum(a * a)])
        mean = (cs[n:] - cs[:-n]) / n
        var = np.maximum((cs2[n:] - cs2[:-n]) / n - mean**2, 1e-12)
        r[ch] = cc / (n * np.sqrt(var) * b.std())
    return np.median(r, axis=0)


def align_subject(subject: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    X, md = cached_rows(subject)
    P = X.astype(np.float64) * 1e6
    pub = published_cues(subject)
    raw_idx = raw_cue_windows(subject)
    i43 = [EEG_60.index(c) for c in
           ["Fpz", "Fp1", "Fp2", *[c for c in CHANNELS_40 if c != "CPz"], "CPz"]]  # fmt: skip
    w43 = []
    for run in RUNS:
        with np.load(CACHE / f"{subject}_pre_{run}.npz") as z:
            w = z["w535"][:, i43].astype(np.float64) * 1e6
        w43.append(w - w.mean(axis=1, keepdims=True))
    W43 = np.concatenate(w43)
    names43 = [EEG_60[i] for i in i43]
    k40 = [names43.index(c) for c in CHANNELS_40]
    W40 = W43[:, k40]

    # Pass 1: every published window against every raw cue of the same code, lag 0, all runs.
    Pn, Rn = unit_rows(P), unit_rows(W40[..., 250:1250])
    # One matrix product per channel: an einsum over all four axes builds a 2 GB temporary.
    r = np.median(np.stack([Pn[:, c] @ Rn[:, c].T for c in range(Pn.shape[1])], axis=2), axis=2)
    codes_pub = np.where(md.label.to_numpy() == 1, "2", "3")
    r[codes_pub[:, None] != raw_idx.code.to_numpy()[None, :]] = -np.inf
    best = r.argmax(axis=1)
    srt = np.sort(r, axis=1)
    rows = []
    for i, row in enumerate(md.itertuples()):
        cue = pub[f"{int(row.run):02d}"]["cues"][(int(row.trial_in_run), int(row.label))]
        j = int(best[i])
        rows.append(dict(subject=subject, run=int(row.run), trial_in_run=int(row.trial_in_run),
                         label=int(row.label), code=codes_pub[i], **cue,
                         lag0_best_r=float(r[i, j]), lag0_second_r=float(srt[i, -2]),
                         lag0_raw_run=raw_idx.raw_run[j], lag0_raw_cue=int(raw_idx.raw_cue[j]),
                         lag0_row=j))  # fmt: skip
    df = pd.DataFrame(rows)
    df["match"] = np.where(df.lag0_best_r > 0.5, "lag0", "unmatched")

    run_map = {}
    for run, g in df[df.match == "lag0"].groupby("run"):
        found = g.lag0_raw_run.unique()
        run_map[run] = found[0] if len(found) == 1 else "several"
    df["raw_run"] = df.run.map(run_map)
    df["raw_cue"] = np.where(df.match == "lag0", df.lag0_raw_cue, -1)
    df["row"] = np.where(df.match == "lag0", df.lag0_row, -1)
    df["shift"] = 0
    df["r"] = np.where(df.match == "lag0", df.lag0_best_r, np.nan)
    df["overlap"] = np.where(df.match == "lag0", 1000, 0)

    # Pass 2: a cut between cue and window start moves the published window later in the raw
    # recording, so a window without a lag-0 match is slid along the continuous raw run,
    # through the run's spatial map, between the raw cues its published neighbours matched.
    todo = df.index[df.match == "unmatched"]
    cols = ["match", "raw_cue", "row", "shift", "r", "overlap"]
    for run in sorted(df.run[todo].unique()):
        rr = run_map[run]
        done = ALIGN_DIR / f"pass2_{subject}_pre_{run:02d}.csv"
        if done.exists():
            prev = pd.read_csv(done, index_col=0)
            df.loc[prev.index, cols] = prev[cols].to_numpy()
            continue
        x43 = continuous_raw43(subject, rr, i43)
        with np.load(CACHE / f"{subject}_pre_{rr}.npz") as z:
            raw_samples, raw_codes = z["samples"], z["codes"].astype(str)
        g = df[(df.run == run) & (df.match == "lag0")]
        R = np.hstack([W43[int(df.row[m])][:, 250:1250] for m in g.index])
        M = np.linalg.lstsq(R.T, np.hstack([P[m] for m in g.index]).T, rcond=None)[0].T
        y = M @ x43
        for k in todo[df.run[todo] == run]:
            before = g[g.pub_cue < df.pub_cue[k]].raw_cue.max()
            after = g[g.pub_cue > df.pub_cue[k]].raw_cue.min()
            lo = 0 if pd.isna(before) else int(raw_samples[int(before)]) + 251
            hi = y.shape[1] - 1000 if pd.isna(after) else int(raw_samples[int(after)]) + 249
            rs = sliding_median_r(y, P[k], lo, hi)
            start = lo + int(np.argmax(rs))
            cue_at = start - 250
            ok = [i for i in range(len(raw_codes))
                  if raw_codes[i] == df.code[k] and raw_samples[i] <= cue_at + 2
                  and (pd.isna(before) or i > before)
                  and (pd.isna(after) or i < after)]  # fmt: skip
            if not ok:
                continue
            i = max(ok, key=lambda i: raw_samples[i])
            row = int(raw_idx.index[(raw_idx.raw_run == rr) & (raw_idx.raw_cue == i)][0])
            df.loc[k, cols] = ["searched", i, row, int(cue_at - raw_samples[i]),
                               float(rs.max()), 1000]  # fmt: skip
        df.loc[todo[df.run[todo] == run], cols].to_csv(done)

    # Lag scan and the leave-trial-out spatial map, lag-0 matches only.
    df["best_lag"] = np.nan
    df["mapped_r"] = np.nan
    lags = np.arange(-25, 26)
    for k in df.index[df.match == "lag0"]:
        j = int(df.row[k])
        scan = [median_r(W40[j][:, 275 + lag : 1225 + lag], P[k][:, 25:975]) for lag in lags]
        df.loc[k, "best_lag"] = int(lags[int(np.argmax(scan))])
    for _, g in df[df.match == "lag0"].groupby("run"):
        for k in g.index:
            fit = [m for m in g.index if m != k]
            R = np.hstack([W43[int(df.row[m])][:, 250:1250] for m in fit])
            Pt = np.hstack([P[m] for m in fit])
            M = np.linalg.lstsq(R.T, Pt.T, rcond=None)[0].T
            df.loc[k, "mapped_r"] = median_r(M @ W43[int(df.row[k])][:, 250:1250], P[k])

    runs = []
    for run in RUNS:
        g = df[df.run == int(run)].sort_values("pub_cue")
        rr = run_map.get(int(run), "none")
        raw_codes = raw_idx[raw_idx.raw_run == rr].code if rr in RUNS else pd.Series([], dtype=str)
        runs.append(dict(subject=subject, run=int(run), raw_run=rr,
                         n_pub_cues=len(pub[run]["order"]), n_raw_cues=len(raw_codes),
                         n_cached=len(g), pub_order=pub[run]["order"],
                         raw_order="".join(raw_codes),
                         order_kept=bool(np.all(np.diff(g.raw_cue.to_numpy()) > 0)),
                         n_searched=int((g.match == "searched").sum()),
                         n_unmatched=int((g.match == "unmatched").sum())))  # fmt: skip
    return df, pd.DataFrame(runs)


def is_subsequence(short: str, long: str) -> bool:
    it = iter(long)
    return all(ch in it for ch in short)


def part_align() -> None:
    frames, run_frames = [], []
    for subject in pre_subjects():
        df, runs = align_subject(subject)
        frames.append(df)
        run_frames.append(runs)
        log.info("%s aligned: %d lag 0, %d searched, %d unmatched; raw runs %s", subject,
                 int((df.match == "lag0").sum()), int((df.match == "searched").sum()),
                 int((df.match == "unmatched").sum()), runs.raw_run.tolist())  # fmt: skip
    df = pd.concat(frames, ignore_index=True)
    runs = pd.concat(run_frames, ignore_index=True)
    runs["pub_in_raw_order"] = [
        is_subsequence(p, r) for p, r in zip(runs.pub_order, runs.raw_order, strict=True)
    ]
    df.drop(columns=["row", "lag0_row"]).to_csv(out("alignment_trials.csv"), index=False,
                                                float_format="%.4f")  # fmt: skip
    runs.to_csv(out("alignment_runs.csv"), index=False)
    lag0, found = df[df.match == "lag0"], df[df.match == "searched"]
    shifted = found[found["shift"].abs() > 2]
    in_place = found[found["shift"].abs() <= 2]
    used = df[df.match != "unmatched"]
    checks = {
        "n_cached_windows": len(df),
        "n_lag0": len(lag0),
        "n_searched": len(found),
        "n_searched_in_place": len(in_place),
        "n_searched_shifted": len(shifted),
        "n_unmatched": int((df.match == "unmatched").sum()),
        "one_to_one": bool(not used.duplicated(["subject", "raw_run", "raw_cue"]).any()),
        "each_published_run_from_one_raw_run": bool(runs.raw_run.isin(RUNS).all()),
        "runs_renumbered": runs[runs.raw_run != runs.run.map(lambda r: f"{r:02d}")][
            ["subject", "run", "raw_run"]].to_dict("records"),
        "order_kept_all_runs": bool(runs.order_kept.all()),
        "published_cue_sequence_in_raw_order_all_runs": bool(runs.pub_in_raw_order.all()),
        "runs_with_identical_cue_sequence": int((runs.pub_order == runs.raw_order).sum()),
        "n_runs": len(runs),
        "lag0_best_lag_zero": int((lag0.best_lag == 0).sum()),
        "lag0_mapped_r_gt_09": int((lag0.mapped_r > 0.9).sum()),
        "lag0_mapped_r_min": float(lag0.mapped_r.min()),
        "lag0_mapped_r_median": float(lag0.mapped_r.median()),
        "lag0_direct_r_median": float(lag0.r.median()),
        "lag0_direct_r_gt_09": int((lag0.r > 0.9).sum()),
        "lag0_second_best_r_max": float(lag0.lag0_second_r.max()),
        "cached_with_cut_before_window": int(df.cut_before_window.sum()),
        "shifted_all_have_cut_before_window": bool(shifted.cut_before_window.all()),
        "in_place_none_has_cut_before_window": bool(not in_place.cut_before_window.any()),
        "searched_mapped_r_min": float(found.r.min()) if len(found) else None,
        "shifted_samples": shifted["shift"].astype(int).tolist(),
    }  # fmt: skip
    checks["passed"] = bool(
        checks["n_unmatched"] == 0
        and checks["one_to_one"]
        and checks["each_published_run_from_one_raw_run"]
        and checks["order_kept_all_runs"]
        and checks["published_cue_sequence_in_raw_order_all_runs"]
        and checks["lag0_best_lag_zero"] == len(lag0)
        and checks["lag0_mapped_r_gt_09"] >= 0.95 * len(lag0)
        and checks["lag0_mapped_r_min"] > 0.5
        and checks["shifted_all_have_cut_before_window"]
        and checks["in_place_none_has_cut_before_window"]
        and (not len(found) or checks["searched_mapped_r_min"] > 0.8)
    )  # fmt: skip
    out("alignment_checks.json").write_text(json.dumps(checks, indent=2, default=str) + "\n")
    log.info("alignment: %s", json.dumps(checks, default=str))
    if not checks["passed"]:
        raise SystemExit("alignment check failed: stop and report")
    part_shifts()


def part_shifts() -> None:
    """The published windows found after their cue, from the stored alignment, in seconds."""
    df = pd.read_csv(out("alignment_trials.csv"))
    shifted = df[(df.match == "searched") & (df["shift"].abs() > 2)]
    cols = ["subject", "run", "trial_in_run", "label", "raw_run", "raw_cue"]
    table = shifted[cols].assign(shift_samples=shifted["shift"].astype(int),
                                 shift_s=shifted["shift"] / SFREQ)  # fmt: skip
    table.to_csv(out("alignment_shifts.csv"), index=False, float_format="%.6g")


def ts_lr_proba(Xtr, ytr, mdtr, Xte) -> np.ndarray:
    m = make_method("ts_lr", n_classes=2, **method_params("ts_lr", get_paths().configs))
    m.fit(Batch(Xtr, ytr, mdtr))
    return m.predict_proba(Xte)


def lda_proba(Xtr, ytr, Xte) -> np.ndarray:
    """Shrinkage LDA on the flattened slow-wave samples. X: (n, channels, 40), volts."""
    lda = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
    lda.fit(Xtr.reshape(len(Xtr), -1), ytr)
    if list(lda.classes_) != CONFIG["classes"]:
        raise AssertionError("LDA class order differs from the task's")
    return lda.predict_proba(Xte.reshape(len(Xte), -1))


def raw_arrays(subject: str, md: pd.DataFrame) -> dict[str, np.ndarray]:
    """Raw windows of the cached trials, in md's order, common average applied."""
    parts: dict[str, list] = {"w830": [], "w535": [], "slow10": [], "eog10": []}
    runs = {}
    for run in RUNS:
        with np.load(CACHE / f"{subject}_pre_{run}.npz") as z:
            runs[run] = {k: z[k] for k in z.files}
    amap = pd.read_csv(out("alignment_trials.csv"), dtype={"raw_run": str, "code": str})
    amap = amap[amap.subject == subject].set_index(["run", "trial_in_run", "label"])
    for row in md.itertuples():
        m = amap.loc[(int(row.run), int(row.trial_in_run), int(row.label))]
        run, i = f"{int(m.raw_run):02d}", int(m.raw_cue)
        if str(runs[run]["codes"][i]) != m.code or not runs[run]["valid"][i]:
            raise AssertionError(f"{subject} raw run {run} cue {i}: code or window mismatch")
        for k in parts:
            parts[k].append(runs[run][k][i])
    arrays = {k: np.stack(v) for k, v in parts.items()}
    for k in ("w830", "w535", "slow10"):
        arrays[k] = arrays[k] - arrays[k].mean(axis=1, keepdims=True)
    arrays["mad830"] = np.median([runs[r]["mad830"] for r in RUNS], axis=0)
    return arrays


def score_window(subject: str, window: str, Xpub: np.ndarray, md: pd.DataFrame, raw) -> list:
    tmin = CONFIG["windows_s"][window][0]
    a = round(tmin * SFREQ) - round(STORE_T0 * SFREQ)
    fast = slice(a, a + 1000)
    b = round((tmin - SLOW_T0) * SFREQ / DECIM)
    slow = slice(b, b + 40)
    tr = md.index[md.run.isin(CONFIG["train_runs"])].to_numpy()
    te = md.index[md.run.isin(CONFIG["test_runs"])].to_numpy()
    assert_no_leakage(md.iloc[tr], md.iloc[te])
    y = md.label.to_numpy()
    ch = {
        "40": [EEG_60.index(c) for c in CHANNELS_40],
        "59": [EEG_60.index(c) for c in EEG_59],
        "central": [EEG_60.index(c) for c in CENTRAL_14],
        "posterior": [EEG_60.index(c) for c in PARIETO_OCCIPITAL_5],
    }
    pub = {
        "central": [list(CHANNELS_40).index(c) for c in CENTRAL_14],
        "posterior": [list(CHANNELS_40).index(c) for c in PARIETO_OCCIPITAL_5],
    }

    def ts(X):
        return ts_lr_proba(X[tr], y[tr], md.iloc[tr], X[te])

    def lda(X):
        return lda_proba(X[tr], y[tr], X[te])

    w830, w535 = raw["w830"][..., fast], raw["w535"][..., fast]
    s10, e10 = raw["slow10"][..., slow], raw["eog10"][..., slow]
    proba = {
        "B0": ts(Xpub),
        "B0_central": ts(Xpub[:, pub["central"]]),
        "B0_posterior": ts(Xpub[:, pub["posterior"]]),
        "R40": ts(w830[:, ch["40"]]),
        "R59": ts(w830[:, ch["59"]]),
        "R_central": ts(w830[:, ch["central"]]),
        "R40_535": ts(w535[:, ch["40"]]),
        "S59": lda(s10[:, ch["59"]]),
        "S_central": lda(s10[:, ch["central"]]),
        "S_posterior": lda(s10[:, ch["posterior"]]),
        "S_eog": lda(e10),
    }
    proba["C59"] = (proba["R59"] + proba["S59"]) / 2
    proba["C_central"] = (proba["R_central"] + proba["S_central"]) / 2
    n_ah, n_sf = int((y[tr] == 1).sum()), int((y[tr] == 2).sum())
    return [dict(subject=subject, window=window, arm=arm,
                 bal_acc=score(y[te], p, CONFIG["classes"])["bal_acc"],
                 n_train=len(tr), n_test=len(te), n_train_ah=n_ah, n_train_sf=n_sf)
            for arm, p in proba.items()]  # fmt: skip


def part_score() -> None:
    checks = out("alignment_checks.json")
    if not checks.exists() or not json.loads(checks.read_text())["passed"]:
        raise SystemExit("the alignment check has not passed; run --part align")
    partial = RUNS_DIR / "per_patient.partial.csv"
    done = pd.read_csv(partial) if partial.exists() else pd.DataFrame(columns=["subject"])
    paths, cfg = get_paths(), load_data_config()
    for subject in pre_subjects():
        if subject in set(done.subject):
            continue
        t0 = time.perf_counter()
        Xpub, md = cached_rows(subject)
        raw = raw_arrays(subject, md)
        rows = score_window(subject, "primary", Xpub, md, raw)
        keep, X04 = recut(md, cfg, paths.processed, 0.0, 4.0)
        md04 = md[keep].reset_index(drop=True)
        raw04 = {k: (v[keep] if k != "mad830" else v) for k, v in raw.items()}
        rows += score_window(subject, "secondary", X04, md04, raw04)
        mad = raw["mad830"][:59]
        for r in rows:
            r["max_channel_amp_ratio"] = float(mad.max() / np.median(mad))
            r["worst_channel"] = EEG_59[int(np.argmax(mad))]
            r["n_dropped_secondary"] = int((~keep).sum())
        done = pd.concat([done, pd.DataFrame(rows)], ignore_index=True)
        done.to_csv(partial, index=False, float_format="%.6g")
        log.info("%s scored in %.0f s", subject, time.perf_counter() - t0)
    done = pd.read_csv(partial)
    done["git_sha"] = current_git_sha()
    done.to_csv(out("per_patient.csv"), index=False, float_format="%.6g")
    partial.unlink()


PRIMARY = ["R40", "R59", "S59", "S_central", "S_posterior", "C59", "C_central"]
DESCRIPTIVE = [
    ("R40_535", "B0"),
    ("R_central", "B0_central"),
    ("S_central", "B0_central"),
    ("C_central", "B0_central"),
    ("S_posterior", "B0_posterior"),
    ("S_central", "S_posterior"),
    ("C59", "R59"),
]


def part_summary() -> None:
    pp = pd.read_csv(out("per_patient.csv"))
    cv = pd.read_csv(get_paths().summary / "rq4_visual_cue_decode.csv")
    cv = cv[cv.task == "T1_ah_vs_sf"].set_index(["subject", "channels"]).bal_acc
    prim = pp[pp.window == "primary"].set_index(["subject", "arm"]).bal_acc
    repro = {}
    for arm, chans in (("B0", "all_40"), ("B0_central", "central_14"),
                       ("B0_posterior", "parieto_occipital_5")):  # fmt: skip
        mine = prim.xs(arm, level="arm")
        ref = cv.xs(chans, level="channels").reindex(mine.index)
        repro[arm] = float((mine - ref).abs().max())
    checks = {
        "n_patients": int(pp.subject.nunique()),
        "B0_mean_primary": float(prim.xs("B0", level="arm").mean()),
        "max_abs_diff_to_committed": repro,
        "reproduced": bool(max(repro.values()) < 5e-6),
        "git_sha": current_git_sha(),
    }
    out("checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    rows, table = [], []
    for window, g in pp.groupby("window", sort=False):
        # pivot, not pivot_table: a patient scored twice must fail here, not be averaged.
        wide = g.pivot(index="subject", columns="arm", values="bal_acc")  # noqa: PD010
        for arm in wide.columns:
            mean, lo, hi = bootstrap_ci(wide[arm].to_numpy())
            table.append(dict(window=window, arm=arm, n=len(wide), mean=mean, ci_lo=lo, ci_hi=hi))
        pairs = [(a, "B0") for a in PRIMARY] + DESCRIPTIVE
        for a, b in pairs:
            d = wide[a] - wide[b]
            res = paired_test(wide[a].to_numpy(), wide[b].to_numpy())
            rows.append(dict(window=window, arm=a, baseline=b,
                             kind="primary" if (a, b) in [(p, "B0") for p in PRIMARY]
                             else "descriptive",
                             arm_mean=wide[a].mean(), baseline_mean=wide[b].mean(),
                             n_better=int((d > 0).sum()), n_worse=int((d < 0).sum()),
                             **res))  # fmt: skip
    pd.DataFrame(table).to_csv(out("table.csv"), index=False, float_format="%.6g")
    paired = pd.DataFrame(rows)
    paired.to_csv(out("paired.csv"), index=False, float_format="%.6g")
    log.info("checks: %s", json.dumps(checks))
    show = paired[["window", "arm", "baseline", "arm_mean", "baseline_mean", "mean_diff",
                   "ci_lo", "ci_hi", "p", "n_better", "n_worse"]]  # fmt: skip
    print(show.to_string(index=False, float_format=lambda v: f"{v:.4f}"))


# Added after the scores above were seen, to read them, not to choose anything: S59 without the
# seven frontal-pole and anterior-frontal electrodes nearest the eyes.
NEAR_EYES = ["Fpz", "Fp1", "Fp2", "AF3", "AF4", "AF7", "AF8"]


def part_posthoc() -> None:
    rows = []
    paths, cfg = get_paths(), load_data_config()
    chans = [EEG_60.index(c) for c in EEG_59 if c not in NEAR_EYES]
    for subject in pre_subjects():
        _, md = cached_rows(subject)
        raw = raw_arrays(subject, md)
        keep, _ = recut(md, cfg, paths.processed, 0.0, 4.0)
        for window, rows_md, s10 in (("primary", md, raw["slow10"]),
                                     ("secondary", md[keep].reset_index(drop=True),
                                      raw["slow10"][keep])):  # fmt: skip
            b = round((CONFIG["windows_s"][window][0] - SLOW_T0) * SFREQ / DECIM)
            tr = rows_md.index[rows_md.run.isin(CONFIG["train_runs"])].to_numpy()
            te = rows_md.index[rows_md.run.isin(CONFIG["test_runs"])].to_numpy()
            assert_no_leakage(rows_md.iloc[tr], rows_md.iloc[te])
            y = rows_md.label.to_numpy()
            X = s10[:, chans, b : b + 40]
            proba = lda_proba(X[tr], y[tr], X[te])
            bal = score(y[te], proba, CONFIG["classes"])["bal_acc"]
            rows.append(dict(subject=subject, window=window, arm="S52_no_near_eyes", bal_acc=bal))
    ph = pd.DataFrame(rows)
    pp = pd.read_csv(out("per_patient.csv"))
    res = []
    for window, g in ph.groupby("window", sort=False):
        wide = pp[pp.window == window].pivot(  # noqa: PD010
            index="subject", columns="arm", values="bal_acc"
        )
        a = g.set_index("subject").bal_acc.reindex(wide.index)
        for base in ("B0", "S59"):
            d = a - wide[base]
            res.append(dict(window=window, arm="S52_no_near_eyes", baseline=base,
                            arm_mean=a.mean(), baseline_mean=wide[base].mean(),
                            n_better=int((d > 0).sum()), n_worse=int((d < 0).sum()),
                            **paired_test(a.to_numpy(), wide[base].to_numpy())))  # fmt: skip
        gain = wide["S59"] - wide["B0"]
        res.append(dict(window=window, arm="spearman(S_eog, S59 - B0)", baseline="",
                        arm_mean=float(wide["S_eog"].corr(gain, method="spearman"))))  # fmt: skip
    ph["git_sha"] = current_git_sha()
    ph.to_csv(out("posthoc_per_patient.csv"), index=False, float_format="%.6g")
    res = pd.DataFrame(res)
    res.to_csv(out("posthoc.csv"), index=False, float_format="%.6g")
    print(res[["window", "arm", "baseline", "arm_mean", "baseline_mean", "mean_diff", "ci_lo",
               "ci_hi", "p", "n_better", "n_worse"]].to_string(index=False))  # fmt: skip


def part_repro(research: Path) -> None:
    names = ["alignment_trials.csv", "alignment_runs.csv", "alignment_checks.json",
             "per_patient.csv", "paired.csv", "table.csv", "checks.json", "posthoc.csv",
             "posthoc_per_patient.csv"]  # fmt: skip
    table = ex.repro_table(NAME, research, {n: out(n) for n in names})
    before = json.loads((research / "config.json").read_text())
    table = pd.concat([table, pd.DataFrame([dict(analysis=NAME,
                                                 **ex.settings_diff(CONFIG, before))])],
                      ignore_index=True)  # fmt: skip
    table["git_sha"] = current_git_sha()
    table.to_csv(out("repro.csv"), index=False, float_format="%.6g")
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        log.info("\n%s", table.drop(columns="note").to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parts = ["fetch", "align", "shifts", "score", "summary", "posthoc", "repro"]
    ap.add_argument("--part", required=True, choices=parts)
    ap.add_argument("--subjects", nargs="*", default=None, help="fetch: only these patients")
    ap.add_argument("--research", type=Path, help="repro: folder of the exploratory run")
    args = ap.parse_args()
    if args.part == "repro" and args.research is None:
        ap.error("--research is needed for repro")
    setup_logging()
    t0 = time.perf_counter()
    log.info("part %s start, git %s", args.part, current_git_sha())
    {
        "fetch": lambda: part_fetch(args.subjects or pre_subjects()),
        "align": part_align,
        "shifts": part_shifts,
        "score": part_score,
        "summary": part_summary,
        "posthoc": part_posthoc,
        "repro": lambda: part_repro(args.research),
    }[args.part]()
    log.info("part %s done: %.0f s wall", args.part, time.perf_counter() - t0)


if __name__ == "__main__":
    main()
