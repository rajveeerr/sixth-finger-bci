"""Kaggle notebook that runs one job of this project on the bundled code and epoch cache.

push.sh writes the job into JOB and pushes this file as a private script notebook; bundle.sh
made its inputs, the code (a git archive with GIT_SHA and PREREG) and the epoch cache. A job
that needs the pre-trained EEGNets also mounts the output of the "pretrain" job. Kaggle's own
CUDA build of torch is kept; the project's Linux pin would select the CPU wheel. Everything
the job writes, and job.json with its provenance, is the notebook's output.
"""

import glob
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

JOB = {}  # filled in by push.sh

OUT = Path("/kaggle/working")
REPO = Path("/tmp/repo")  # outside the output, which then holds results only


def find(name: str) -> list[Path]:
    return sorted(Path(p) for p in glob.glob(f"/kaggle/input/**/{name}", recursive=True))


epochs_dir = find("metadata.parquet")[0].parent
# Kaggle unpacks an uploaded archive into a folder; the archive itself may or may not remain.
archives = find("code.tar.gz") + find("code.tar")
if archives:
    REPO.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archives[0]) as tar:
        tar.extractall(REPO, filter="data")
else:
    snapshot = [p.parent for p in find("pyproject.toml") if (p.parent / "src/sixthfinger").is_dir()]
    shutil.copytree(snapshot[0], REPO, dirs_exist_ok=True)
for stamp in ("GIT_SHA", "PREREG"):
    if not (REPO / stamp).exists():
        shutil.copy(next(p for p in find(stamp)), REPO / stamp)
sha = (REPO / "GIT_SHA").read_text().strip()
(REPO / "data/derived").mkdir(parents=True, exist_ok=True)
(REPO / "data/derived/epochs").symlink_to(epochs_dir)
# Results are written straight into the output, so a job stopped part-way keeps what it did.
(OUT / "results").mkdir(parents=True, exist_ok=True)
(REPO / "results").symlink_to(OUT / "results")
for manifest in find("manifest.json"):
    weights = sorted(manifest.parent.glob("eegnet_loso_*.pt"))
    if weights:
        dest = REPO / "models/pretrained"
        dest.mkdir(parents=True, exist_ok=True)
        for f in [*weights, manifest]:
            shutil.copy(f, dest / f.name)
print("job", JOB, "code at", sha, "epochs in", epochs_dir)

pins = ["braindecode==1.8.1", "mne==1.13.2", "pyriemann==0.12", "pymatreader", "typer"]
subprocess.run([sys.executable, "-m", "pip", "install", "-q", *pins], check=True)
env = {
    **os.environ,
    "PYTHONPATH": str(REPO / "src"),
    "SIXTHFINGER_ROOT": str(REPO),
    "SIXTHFINGER_GIT_SHA": sha,
}
probe = (
    "import json, torch; c = torch.cuda.is_available(); print(json.dumps({'torch': "
    "torch.__version__, 'cuda': c, 'device_name': torch.cuda.get_device_name(0) if c else 'cpu'}))"
)
device = json.loads(
    subprocess.run([sys.executable, "-c", probe], env=env, check=True, capture_output=True,
                   text=True).stdout.strip().splitlines()[-1]
)  # fmt: skip
print("device", device)

if JOB["kind"] == "pretrain":
    cmd = [sys.executable, str(REPO / "scripts/pretrain_loso.py"), "--epochs-dir", str(epochs_dir)]
    cmd += ["--out", str(OUT / "pretrained"), *JOB["args"]]
elif JOB["kind"] == "run":
    cmd = [sys.executable, "-c", "from sixthfinger.cli import app; app()", "run", *JOB["args"]]
else:
    raise SystemExit(f"unknown job kind {JOB['kind']!r}")
start = time.time()
info = {"job": JOB, "git_sha": sha, "prereg": (REPO / "PREREG").read_text().split("\n"), **device}
try:
    subprocess.run(cmd, env=env, cwd=REPO, check=True)
    info["status"] = "complete"
finally:
    info["seconds"] = round(time.time() - start)
    (OUT / "job.json").write_text(json.dumps(info, indent=2) + "\n")
