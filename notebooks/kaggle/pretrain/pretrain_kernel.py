"""Kaggle GPU notebook: the leave-one-subject-out EEGNet pre-training of P07 step 4.4.

Pushed with `kaggle kernels push -p notebooks/kaggle/pretrain`. Its two inputs are private
datasets made by bundle.sh: the code (a git archive with its commit id) and the epoch cache.
Kaggle's own CUDA build of torch is kept; the project's Linux pin would select the CPU wheel.
The models and their manifest are this notebook's output.
"""

import glob
import os
import subprocess
import sys
import tarfile
from pathlib import Path

TARGETS = os.environ.get("TARGETS", "").split()  # empty: every subject
MAX_EPOCHS = os.environ.get("MAX_EPOCHS", "")  # set only for a smoke run

code = glob.glob("/kaggle/input/**/code.tar.gz", recursive=True)[0]
epochs_dir = Path(glob.glob("/kaggle/input/**/metadata.parquet", recursive=True)[0]).parent
repo = Path("/kaggle/working/repo")
repo.mkdir(parents=True, exist_ok=True)
with tarfile.open(code) as tar:
    tar.extractall(repo, filter="data")
sha = (repo / "GIT_SHA").read_text().strip()

pins = ["braindecode==1.8.1", "mne==1.13.2", "pyriemann==0.12", "pymatreader", "typer"]
subprocess.run([sys.executable, "-m", "pip", "install", "-q", *pins], check=True)

env = {
    **os.environ,
    "PYTHONPATH": str(repo / "src"),
    "SIXTHFINGER_ROOT": str(repo),
    "SIXTHFINGER_GIT_SHA": sha,
}
cmd = [sys.executable, str(repo / "scripts" / "pretrain_loso.py"), "--epochs-dir", str(epochs_dir)]
cmd += ["--out", "/kaggle/working/pretrained"]
if TARGETS:
    cmd += ["--targets", *TARGETS]
if MAX_EPOCHS:
    cmd += ["--max-epochs", MAX_EPOCHS]
subprocess.run(
    [
        sys.executable,
        "-c",
        "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())",
    ],
    env=env,
    check=True,
)
subprocess.run(cmd, env=env, cwd=repo, check=True)
