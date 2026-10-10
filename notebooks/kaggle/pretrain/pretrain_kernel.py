"""Kaggle GPU notebook: the leave-one-subject-out EEGNet pre-training of P07 step 4.4.

Pushed with `kaggle kernels push -p notebooks/kaggle/pretrain`. Its two inputs are private
datasets made by bundle.sh: the code (a git archive with its commit id) and the epoch cache.
Kaggle's own CUDA build of torch is kept; the project's Linux pin would select the CPU wheel.
The models and their manifest are this notebook's output.
"""

import glob
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

TARGETS = os.environ.get("TARGETS", "").split()  # empty: every subject
MAX_EPOCHS = os.environ.get("MAX_EPOCHS", "")  # set only for a smoke run


def find(name: str) -> list[Path]:
    return sorted(Path(p) for p in glob.glob(f"/kaggle/input/**/{name}", recursive=True))


for path in sorted(Path("/kaggle/input").glob("*/*"))[:20]:
    print("input:", path)
epochs_dir = find("metadata.parquet")[0].parent
repo = Path("/kaggle/working/repo")
# Kaggle unpacks an uploaded archive into a folder; the archive itself may or may not remain.
archives = find("code.tar.gz") + find("code.tar")
if archives:
    repo.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archives[0]) as tar:
        tar.extractall(repo, filter="data")
else:
    snapshot = [
        p.parent for p in find("pyproject.toml") if (p.parent / "src" / "sixthfinger").is_dir()
    ]
    shutil.copytree(snapshot[0], repo, dirs_exist_ok=True)
sha_files = [repo / "GIT_SHA", *find("GIT_SHA")]
sha = next(p for p in sha_files if p.exists()).read_text().strip()
print("code at", sha, "epochs in", epochs_dir)

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
