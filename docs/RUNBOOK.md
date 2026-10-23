# Runbook

How to install, run, test and verify every part of the project, what each
command should print, and how to tell that it worked. Commands are run from
the repository root unless stated otherwise.

The column **Available** says from which project phase a command does real
work; before that it prints a message naming the phase that implements it.

## 1. One-time setup

| Step | Command | Expected result |
|------|---------|-----------------|
| System tools (macOS) | `brew install uv git node@22 tectonic` | tools on PATH |
| System tools (Linux/WSL2) | `curl -LsSf https://astral.sh/uv/install.sh \| sh`, then Node 22 (e.g. `curl -fsSL https://deb.nodesource.com/setup_22.x \| sudo -E bash - && sudo apt-get install -y nodejs`), git, and optionally Tectonic for the PDFs | tools on PATH |
| Everything else | `make setup` | Python env (`.venv`), git hooks, server env, web packages; ends without errors (first run 3–6 min) |
| Check the environment | `uv run sixthfinger doctor` | python 3.12, numpy 2.5.3, mne 1.13.2, scikit-learn 1.9.1, pyriemann 0.12, torch 2.11.0, braindecode 1.8.1, accelerator `mps`/`cuda`/`cpu`, disk free, data and cache status |

Two `FutureWarning` lines about a montage name from braindecode's EEGPT
module are harmless.

## 2. Data

| Step | Command | Available | Expected result | How to know it worked |
|------|---------|-----------|-----------------|-----------------------|
| Download + verify | `make data` | now | downloads `processeddata.zip` (3.5 GB, resumable), checks md5 `7a3138c1…`, unzips, verifies, deletes the zip | `data/processed/` has 268 `.mat` files |
| Re-verify | `make verify-data` | now | `OK: 268 .mat files, sizes match processeddata_listing.tsv` | exit code 0 |
| Integrity audit | `make audit` | P02 | writes `results/audit/inventory.csv`, `event_flags.csv`, `near_duplicates.csv`, `raw_crc_duplicates.csv`, `audit_report.md` | sub-02 post/follow pairs at r ≥ 0.9; 8 duplicate groups in the raw archive |
| Cut windows | `make epochs` (subset: `make epochs SUBJECTS=sub-01,sub-03`) | P03 | `data/derived/epochs/*.npz` (64 files), `metadata.parquet`, `manifest.json`, `results/audit/epoch_counts.csv`, `epoch_drops.csv`, `epoch_trials.csv` | 9615 windows of shape (40, 1000); `doctor` shows 64 cached session files |
| Count them again | `uv run sixthfinger epochs counts` | now | rewrites the three `results/audit/epoch_*.csv` from the cache's tables in a second, without cutting | 5061 trials; the window counts unchanged |

If the download stops, run `make data` again; it resumes. Never use figshare's
"Download all".

## 3. Tests and quality checks

| What | Command | Expected result |
|------|---------|-----------------|
| Everything CI runs | `make check` | ruff `All checks passed!`, all files formatted, Python tests pass, server tests pass, web lint/typecheck/tests/build pass |
| Python unit tests only | `make test` | all pass (synthetic data, no download needed) |
| Tests that need the real data | `make test-real` | pass once data and cache exist |
| Lint / auto-format | `make lint` / `make format` | clean |
| Server tests | `cd server && uv run pytest -q` | `24 passed` |
| Web unit tests | `npm --prefix web run test` | all pass |
| Web type check / lint / build | `npm --prefix web run typecheck`, `run lint`, `run build` | no errors; `web/dist/` created |
| Browser tests | `npx --prefix web playwright install chromium` (once), then `make e2e` | all pass |

The leakage guarantees are tested in `tests/test_leakage.py` (P05): a test
trial in training, the target subject in source data, or the linked subjects
sub-21/sub-22 split across train and test all make the tests fail, and a
label-permutation test checks that shuffled labels give chance accuracy.

## 4. Experiments

All experiments are YAML files in `configs/experiments/` and run with one
command. Runs are resumable: running the same command again skips finished
units. Full scores go to `results/runs/<experiment>/scores.parquet`
(not committed); summaries and figures are produced by the scripts below.

| Experiment | Command | Available | Where it runs | Time (approx.) |
|------------|---------|-----------|---------------|----------------|
| Smoke test | `uv run sixthfinger run configs/experiments/smoke.yaml --subjects sub-01,sub-03` | P05 | Mac | < 1 min |
| RQ1 re-benchmark | `uv run sixthfinger run configs/experiments/rq1_benchmark.yaml` | P06 | Mac | 1–4 h |
| Deep baselines | `bash notebooks/kaggle/push.sh dl-baselines gpu run configs/experiments/dl_baselines.yaml` | P07 | Kaggle GPU | 1.7 h (T4) |
| Leave-one-subject-out pre-training | `bash notebooks/kaggle/push.sh pretrain gpu pretrain` | P07 | Kaggle GPU | 45 min (T4) |
| RQ2 calibration, new user | `uv run sixthfinger run configs/experiments/rq2_calib_s1.yaml --methods <classical> --jobs 3`, or Kaggle shards (`push.sh ... cpu run ... --subjects ... --jobs 4`); EEGNet methods with `push.sh ... gpu --models run ...` | P08 | Mac or Kaggle CPU + Kaggle GPU | hours per shard |
| RQ3 calibration, new command | same with `rq3_calib_s2.yaml` | P08 | same | same |
| Transfer values (P08 step 4.5) | `uv run python scripts/select_transfer_hparams.py --methods rct_tslr rct_mdm eegnet_ea_ft` | P08 | Mac | 30 min |
| RQ5 depression leakage | `uv run python scripts/rq5_depression.py fetch`, then `audit`, `run`, `summarise` | P09 | Mac | minutes after a 2.5 GB download |
| RQ4 mirroring | Kaggle shards of `configs/experiments/rq4_mirror.yaml` (`push.sh rq4-mirror-<i> cpu run ... --subjects ... --jobs 4`), then `merge_scores.py` | P09 | Kaggle CPU | 40-60 min per shard |
| RQ4 stability over time | `uv run python scripts/rq4_longitudinal.py` | P09 | Mac | 20 min |
| RQ4 pseudo-online replay | `uv run python scripts/pseudo_online.py` (fits through the runner and replays runs 03-04 through `server/app/gate.py`) | P09 | Mac | 35 min |
| RQ4 explainability and visual-cue check | `uv run python scripts/make_explain_figures.py`; `uv run python scripts/check_visual_cue.py` | P09 | Mac | 10 min each |

Quick versions for debugging: add `--quick` (small k grid, two draws) and
`--subjects sub-01,sub-03`.

Kaggle jobs: `bash notebooks/kaggle/bundle.sh --code` uploads the committed code (add the
epoch cache without `--code` when it changed); `push.sh <name> <cpu|gpu> [--models] <kind>
[args]` starts a private notebook; `fetch.sh <name>` downloads its output to
`results/kaggle/<name>/`; `scripts/merge_scores.py results/kaggle/*/results/runs` merges
the scores into `results/runs/`.

Summaries and figures:

| Command | Available | Output |
|---------|-----------|--------|
| `uv run python scripts/make_eda_figures.py --session pre --out docs/figures` | P04 | `docs/figures/eda_*` |
| `uv run python scripts/summarise_rq1.py` | P06 | `results/summary/rq1_*`, `docs/figures/rq1_*` |
| `uv run python scripts/summarise_calibration.py` | P08 | `results/summary/calib_*`, `rq3_sf_vs_ah.csv`, `docs/figures/rq2_*`, `rq3_*` |
| `uv run python scripts/summarise_rq4.py` | P09 | `results/summary/rq4_mirror*`, `docs/figures/rq4_mirror_effect` |
| `uv run python scripts/pseudo_online.py --summarise` | P09 | `results/summary/rq4_pseudo_online*`, `docs/figures/rq4_pseudo_online` |
| `uv run python scripts/summarise_dl.py` | P07 | `results/summary/dl_*` (with `dl_summary.json` and `dl_class_recall.csv`), `results/audit/pretrain*`, `docs/figures/dl_*` |

The group numbers the text quotes, written by each analysis's own summary step from the stored
per-patient values, without fitting anything (add `--no-figures` where the script draws
figures, to leave them alone): `make_eda_figures.py --summary-only` (`eda_erd_summary.csv`),
`rq4_longitudinal.py --summary-only` (`rq4_longitudinal_reference.csv`),
`make_explain_figures.py --summary-only` (`rq4_pattern_share_summary.csv`),
`check_visual_cue.py --summary-only` (`rq4_visual_cue_paired.csv`),
`ex2_slow_waves.py --part shifts` (`ex2_slow_waves_alignment_shifts.csv`),
`make_web_explain_data.py --facts-only` (`demo_page.json`, the model's size and its two
readings from the demo bundle); `summarise_rq1.py`, `summarise_dl.py`,
`summarise_calibration.py`, `summarise_rq4.py`, `pseudo_online.py --summarise` and
`rq5_depression.py summarise` write theirs on every run. After re-running any of them,
`uv run python scripts/compare_summaries.py <ref> --record results/summary/summary_rerun_repro.csv`
compares every file of `results/summary/` and `results/audit/` with the commit before, byte for
byte, and the old columns of a table value by value; exit code 0 means nothing but new files and
new columns appeared.

Exploratory follow-ups, added after the results (deviation log, 2026-10-23). Each script
reads its settings from `configs/experiments/<name>.yaml`, fixed before any score on runs
03-04, runs one part at a time (the order is in its docstring) and writes
`results/summary/<name>_*`; window-level predictions and logs go to
`results/runs/<name>/`. None of them chooses anything on runs 03-04.

| Analysis | Command | Where it runs | Time (approx.) |
|----------|---------|---------------|----------------|
| More data per decision for AH vs SF | `uv run python scripts/ex1_transfer_ah_sf.py --part A`, then `--part C`, `--part B`, `--part B_central`, `--part summary` | Mac (CPU) | 2 min classical; B and B_central 15 min together |
| Raw recordings: slow waves and all 59 channels | `uv run python scripts/ex2_slow_waves.py --part fetch` (reads 1.7 GB from the remote archive, keeps 1.0 GB of cut windows in `data/derived/raw_windows/`), then `--part align`, `--part score`, `--part summary`, `--part posthoc` | Mac | 10 min after the download |
| Pre-training with healthy grasp imagery | `uv run python scripts/ex3_grasp_pretraining.py --part fetch` (4.2 GB from OSF), then the parts listed in the script, from `--part convert` to `--part summary` | Mac (MPS for pre-training) | 13 h, most of it the GP pre-training |
| The sixth finger as its own command | `uv run python scripts/ex4_sf_command.py --part inner_classical`, then `--part inner_eegnet`, `--part select`, `--part test_classical`, `--part test_eegnet`, `--part summary` | Mac (CPU) | 3 min classical; 80 min EEGNet |
| The central switch played as if live | `uv run python scripts/ex5_live_switch.py --part repro` (question 4's `ts_lr` again; must match), then `--part inner`, `--part select`, `--part test`, `--part summary` | Mac (CPU) | about 1.5 min in all |

When these were moved into the repository, the cheap parts were re-run and the expensive
EEGNet parts were brought over from the first run (`--part carry --research <folder of that
run>`), each row keeping the commit that made it (`git_sha`) and the commit that holds it
(`source_commit`); the EEGNet parts with `--subjects` re-run some or all patients beside the
stored values. `--part repro --research <folder of that run>` compares every output with the
first run cell by cell and writes `results/summary/<name>_repro.csv`.

The fifth, `ex5_live_switch`, was written in the repository from the start and has no first
run to compare with. Its `--part repro` instead fits question 4's `ts_lr` again and replays
it with the new code; every patient's values must equal `rq4_pseudo_online_switch.csv`, or
the arms are never replayed. It reads the stored replays of question 4 in
`results/runs/rq4_pseudo_online/replay/` (made by `scripts/pseudo_online.py`) for the
baselines' hand and sixth-finger periods.

How to verify a result: every row of every scores file carries `git_sha`,
`config_hash` and `data_manifest_sha`. Runs made on the development machine
record the commit of the private development history; runs made on Kaggle
(which clones this repository) record a commit of this repository. Every
commit here carries a git note (`refs/notes/devsha`) listing the development
commits it corresponds to, so either kind of `git_sha` leads to a commit you can
check out:

```sh
git fetch origin refs/notes/devsha:refs/notes/devsha
git log --notes=devsha --format='%h %N' | grep <git_sha>   # prints the commit to check out
```

Check out that commit, make sure `data/derived/epochs/manifest.json` has the
same hash, and re-run the experiment: classical methods give identical
numbers.

## 5. Demo

| Step | Command | Available | Expected result |
|------|---------|-----------|-----------------|
| Server only | `make server` | now (synthetic bundle) | `http://localhost:8000/health` → `{"status":"ok", …, "synthetic": true}` until P10, then `false` |
| Server info | `curl -s localhost:8000/api/info` | now | channels, classes, model, number of trials |
| Web only | `make web` | now (placeholder UI) | `http://localhost:5173` shows the layout |
| Both | `make demo` | now; full demo after P11 | server on :8000, web on :5173 |
| Rebuild the bundle from the trained model | `make demo-bundle` | P10 | `web/public/demo/` with the real model and held-out trials, < 25 MB |
| Browser-only preview (no server) | `npm --prefix web run build && npm --prefix web run preview` | P11 | `http://localhost:4173`; badge shows "in-browser" |
| Live demo | https://sixth-finger-bci.vercel.app (static page and a model function, built with `VITE_SERVER_URL=none`, `VITE_DECODE_URL=/api/decode`) | P12 | badge "Model running on the server" within a few seconds; "in this browser" if the function cannot be reached |
| Model function | `curl -s https://sixth-finger-bci.vercel.app/api/decode` | P12 | `{"ok": true, ...}` with the bundle model's sha256; `web/api/decode.py`, checked by `tests/test_web_decode_api.py` |
| Redeploy | automatic: every push to GitHub `main` deploys production through Vercel's Git connection, with the project's Root Directory set to `web`; by hand, `bunx vercel@latest redeploy <deployment-url> --environment production` | P12 | the project's Production variables stay `VITE_SERVER_URL=https://sixth-finger-bci-server.onrender.com`, `VITE_DECODE_URL=/api/decode` |
| Check the live demo | `DEPLOYED_URL=https://sixth-finger-bci.vercel.app npx --prefix web playwright test e2e/deployed.spec.ts` | P12 | 2 passed |
| Backup video | not in git (videos are never committed); where it is in §9 | P12 | a 2-minute screen recording of the demo |
| Offline check | `npx --prefix web playwright test e2e/offline.spec.ts` | P12 | the built site decodes with every other host unreachable |

How to verify the demo is honest and working:

1. The badge shows the data source (server / in-browser / replay).
2. Each prediction shows the instructed class next to the decoded class.
3. The trials in the bundle were never used for training (the bundle builder
   asserts this; `results/summary/demo_model.json` records the subject and method).
4. Stop the server while the page is open: the badge switches to "in-browser"
   within a few seconds and the demo continues. Pausing does not: a paused
   stream sends a `status` heartbeat every 2 s.

## 6. Paper and report

| Step | Command | Available | Expected result |
|------|---------|-----------|-----------------|
| Paper numbers | `uv run python scripts/make_paper_numbers.py` | now | rewrites `paper/generated/numbers.tex` (one macro per number, about 5000) and `paper/generated/numbers-index.md` (each macro's value, meaning and source file) in a second; prints the macros the paper or report use that it does not make, which the PDFs show as red TBDs |
| Check they are current | `uv run python scripts/make_paper_numbers.py --out /tmp/numbers.tex --index /tmp/numbers-index.md && diff /tmp/numbers.tex paper/generated/numbers.tex` | now | no output; `tests/test_paper_numbers.py` fails in `make check` when the committed files are stale |
| Web figures | `make web-figures` (or `npm --prefix web run figures`; add `-- leak setup` for some, `-- --no-build` to reuse the last build) | now | under a minute (needs `uv` the first time); writes `docs/figures/web/` (PDF, 3x PNG, SVG where pure) and copies the paper's to `paper/figures/web/`; commit web changes first, look at the PNGs, then commit both folders together |
| Paper PDF | `make paper` | now (skeleton) | `paper/build/main.pdf`; red TBD markers where the text has no number yet |
| Report PDF | `make report` | now (skeleton) | `report/build/main.pdf` |
| Report as Word | `make -C report docx` (needs `brew install pandoc`) | now | `report/build/report.docx` |

## 7. Reproducing everything from scratch

```sh
git clone <repository> sixth-finger-bci && cd sixth-finger-bci
make setup
make data
make epochs
make check
uv run sixthfinger run configs/experiments/rq1_benchmark.yaml
uv run python scripts/summarise_rq1.py
# then the calibration experiments (section 4) and the demo (section 5)
```

Expected: classical results identical to the committed summaries; deep-learning
results within small run-to-run differences (GPU arithmetic is not bit-exact).

## 8. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `uv: command not found` | open a new terminal; on Linux `source ~/.local/bin/env` |
| `ModuleNotFoundError: sixthfinger` | prefix commands with `uv run` |
| `md5 mismatch` during `make data` | delete the partial zip in `data/raw/figshare/` and run `make data` again |
| Not enough disk space | about 8 GB needed at peak for the data; `uv cache prune` frees space |
| `Epoch cache was built with different settings` | run `make epochs` again |
| Server tests: `No module named 'app'` | update; `server/pyproject.toml` must contain `pythonpath = ["."]` |
| Web: `npm warn EBADENGINE` | a Node version below 22; install Node 22 (LTS) |
| Browser demo stuck on "connecting" | the server is asleep or not running; the app falls back after 2 s, check the browser console |
| `tectonic: command not found` | `brew install tectonic`, or build on Overleaf |

## 9. Live URLs

- Web demo: https://sixthfinger.rajveers.com (CNAME `sixthfinger` at the rajveers.com DNS
  host), also https://sixth-finger-bci.vercel.app; the demo alone, for presenting, at `/live`
- Streaming server: https://sixth-finger-bci-server.onrender.com (Render, free plan, Singapore);
  the site's `VITE_SERVER_URL` (Production) points at it. To set it up again: New > Blueprint in Render, pick this repository
  (`render.yaml`: Python, root directory `server`, build `uv sync --frozen --no-dev`, start
  `.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT`, free plan, Singapore, health check
  `/health`, `ALLOWED_ORIGINS` set to the two site addresses). The same values work in Render's
  "New Web Service" form. Then set the Vercel variable `VITE_SERVER_URL` to the service's
  `https://…onrender.com` address and redeploy the site. The page wakes the server when it opens,
  decodes in the browser until the server answers, then moves to it, and pings it every 10 minutes
  while it is open; an outside monitor (e.g. every 10 minutes on `/health`) keeps it awake between
  visits, inside the free plan's 750 hours a month.
- Model server: the Vercel function `/api/decode` on the same site, in Mumbai (`bom1`), one window
  per request (about 0.2 s round trip from Delhi, a few ms of it the model); the
  streaming WebSocket server (`server/`) is not hosted, `make server` runs it locally
- Backup demo video: on the reference Mac at `~/Movies/sixth-finger-bci-demo-backup.mp4`
  (2 min, 1366×768); copy it to a USB stick and a shared drive and add the link here
