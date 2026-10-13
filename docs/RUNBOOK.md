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
| Cut windows | `make epochs` (subset: `make epochs SUBJECTS=sub-01,sub-03`) | P03 | `data/derived/epochs/*.npz` (64 files), `metadata.parquet`, `manifest.json`, `results/audit/epoch_counts.csv` | 9615 windows of shape (40, 1000); `doctor` shows 64 cached session files |

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
| Redeploy | from a clean `git archive HEAD web` folder: `bunx vercel@latest link --yes --project sixth-finger-bci`, then `bunx vercel@latest deploy --prod --yes` | P12 | the project's Production variables stay `VITE_SERVER_URL=none`, `VITE_DECODE_URL=/api/decode` |
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
| Paper PDF | `make paper` | now (skeleton) | `paper/build/main.pdf`; red TBD markers until results exist |
| Paper numbers | `uv run python scripts/make_paper_numbers.py` | P13 | regenerates `paper/generated/numbers.tex` |
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
- Streaming server on Render (optional): New > Blueprint in Render, pick this repository
  (`render.yaml`: Docker, free plan, Singapore, health check `/health`, `ALLOWED_ORIGINS` set to the
  two site addresses). Then set the Vercel variable `VITE_SERVER_URL` to the service's
  `https://…onrender.com` address and redeploy the site. The page wakes the server when it opens,
  decodes in the browser until the server answers, then moves to it, and pings it every 10 minutes
  while it is open; an outside monitor (e.g. every 10 minutes on `/health`) keeps it awake between
  visits, inside the free plan's 750 hours a month.
- Model server: the Vercel function `/api/decode` on the same site, in Mumbai (`bom1`), one window
  per request (about 0.2 s round trip from Delhi, a few ms of it the model); the
  streaming WebSocket server (`server/`) is not hosted, `make server` runs it locally
- Backup demo video: on the reference Mac at `~/Movies/sixth-finger-bci-demo-backup.mp4`
  (2 min, 1366×768); copy it to a USB stick and a shared drive and add the link here
