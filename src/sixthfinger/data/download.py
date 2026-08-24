"""Download and unpack the figshare archives with resume, md5 and size checks."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import requests
from tqdm import tqdm

log = logging.getLogger(__name__)

CHUNK = 8 * 1024 * 1024
# Free space kept in reserve after an operation; the OS and the IDE need room too.
DISK_MARGIN = 2 * 1024**3


class DownloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class Archive:
    name: str
    file_id: int
    filename: str
    size_bytes: int
    md5: str
    expected_files: int
    extract_to: str


def md5_of(path: Path, chunk: int = CHUNK) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def free_bytes(path: Path) -> int:
    probe = path
    while not probe.exists():
        probe = probe.parent
    return shutil.disk_usage(probe).free


def ensure_space(path: Path, needed: int, margin: int = DISK_MARGIN) -> None:
    free = free_bytes(path)
    if free < needed + margin:
        raise DownloadError(
            f"Not enough disk space at {path}: need {(needed + margin) / 1e9:.1f} GB "
            f"(including {margin / 1e9:.0f} GB margin), have {free / 1e9:.1f} GB."
        )


def download_file(
    url: str,
    dest: Path,
    *,
    expected_size: int | None = None,
    expected_md5: str | None = None,
    session: requests.Session | None = None,
    progress: bool = True,
    timeout: float = 60.0,
) -> Path:
    """Download url to dest, resuming a previous partial download if one exists.

    The partial file lives next to dest as ``<name>.part`` and is only renamed once the
    size and md5 checks pass, so dest existing always means a verified file.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if expected_md5 is None or md5_of(dest) == expected_md5:
            log.info("%s already present and verified", dest.name)
            return dest
        log.warning("%s exists but md5 differs; downloading again", dest.name)
        dest.unlink()

    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    if expected_size is not None:
        if have > expected_size:
            part.unlink()
            have = 0
        ensure_space(dest, expected_size - have)

    sess = session or requests.Session()
    headers = {"Range": f"bytes={have}-"} if have else {}
    with sess.get(url, stream=True, headers=headers, timeout=timeout, allow_redirects=True) as r:
        if have and r.status_code == 200:
            # Server ignored the Range header: start over rather than append a second copy.
            have = 0
        elif have and r.status_code == 416:
            pass
        else:
            r.raise_for_status()
        total = expected_size or (have + int(r.headers.get("Content-Length", 0))) or None
        mode = "ab" if have else "wb"
        if r.status_code != 416:
            with (
                part.open(mode) as f,
                tqdm(
                    total=total,
                    initial=have,
                    unit="B",
                    unit_scale=True,
                    desc=dest.name,
                    disable=not progress,
                ) as bar,
            ):
                for block in r.iter_content(chunk_size=CHUNK):
                    f.write(block)
                    bar.update(len(block))

    size = part.stat().st_size
    if expected_size is not None and size != expected_size:
        raise DownloadError(
            f"{dest.name}: got {size} bytes, expected {expected_size}. "
            "Run the same command again to resume."
        )
    if expected_md5 is not None:
        got = md5_of(part)
        if got != expected_md5:
            part.unlink()
            raise DownloadError(f"{dest.name}: md5 {got} != expected {expected_md5}; deleted.")
    part.rename(dest)
    return dest


def fetch_article(api_url: str, session: requests.Session | None = None) -> dict:
    sess = session or requests.Session()
    r = sess.get(api_url, timeout=60)
    r.raise_for_status()
    return r.json()


def download_metadata(
    article: dict,
    names: list[str],
    dest_dir: Path,
    session: requests.Session | None = None,
) -> list[Path]:
    """Fetch the small BIDS metadata files listed in the article, md5-checked."""
    by_name = {f["name"]: f for f in article["files"]}
    missing = [n for n in names if n not in by_name]
    if missing:
        raise DownloadError(f"Files not found in the figshare article: {missing}")
    out = []
    for name in names:
        f = by_name[name]
        out.append(
            download_file(
                f["download_url"],
                dest_dir / name,
                expected_size=f["size"],
                expected_md5=f["computed_md5"],
                session=session,
                progress=False,
            )
        )
    (dest_dir / "article.json").write_text(json.dumps(article, indent=2, ensure_ascii=False))
    return out


def unzip_verified(
    zip_path: Path,
    dest_dir: Path,
    *,
    expected_files: int | None = None,
    suffixes: tuple[str, ...] = (".mat", ".set", ".fdt"),
    listing_path: Path | None = None,
    on_member: Callable[[str], None] | None = None,
) -> int:
    """Extract an archive and check every member's size; returns the number of data files.

    zipfile verifies each member's CRC32 while reading it, so a corrupted member raises
    instead of silently producing a damaged file.
    """
    with zipfile.ZipFile(zip_path) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        ensure_space(dest_dir, sum(i.file_size for i in infos))
        n_data = sum(i.filename.endswith(suffixes) for i in infos)
        if expected_files is not None and n_data != expected_files:
            raise DownloadError(
                f"{zip_path.name} lists {n_data} data files, expected {expected_files}."
            )
        dest_root = dest_dir.resolve()
        for info in tqdm(infos, desc=f"unzip {zip_path.name}", unit="file"):
            target = (dest_dir / info.filename).resolve()
            if not target.is_relative_to(dest_root):
                raise DownloadError(f"Refusing to extract outside {dest_dir}: {info.filename}")
            if target.exists() and target.stat().st_size == info.file_size:
                continue
            zf.extract(info, dest_dir)
            if target.stat().st_size != info.file_size:
                raise DownloadError(f"Size mismatch after extracting {info.filename}")
            if on_member:
                on_member(info.filename)
        if listing_path is not None:
            listing_path.parent.mkdir(parents=True, exist_ok=True)
            rows = ["path\tsize_bytes\tcrc32"]
            rows += [f"{i.filename}\t{i.file_size}\t{i.CRC:08x}" for i in infos]
            listing_path.write_text("\n".join(rows) + "\n")
    return n_data


def verify_extracted(dest_dir: Path, listing_path: Path) -> list[str]:
    """Compare files on disk against a saved listing; returns a list of problems."""
    problems = []
    for line in listing_path.read_text().splitlines()[1:]:
        rel, size, _crc = line.split("\t")
        p = dest_dir / rel
        if not p.exists():
            problems.append(f"missing: {rel}")
        elif p.stat().st_size != int(size):
            problems.append(f"size differs: {rel}")
    return problems
