"""Command-line entry point: ``uv run sixthfinger --help``."""

from __future__ import annotations

import logging
import platform
import shutil
import sys
from pathlib import Path
from typing import Annotated

import typer

from sixthfinger.config import load_data_config
from sixthfinger.paths import get_paths

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Sixth-finger BCI pipeline.")
data_app = typer.Typer(no_args_is_help=True, help="Download, verify and audit the dataset.")
epochs_app = typer.Typer(no_args_is_help=True, help="Cut and cache EEG windows.")
export_app = typer.Typer(no_args_is_help=True, help="Export models and the demo bundle.")
app.add_typer(data_app, name="data")
app.add_typer(epochs_app, name="epochs")
app.add_typer(export_app, name="export")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _not_yet(phase: str, what: str) -> None:
    typer.secho(
        f"'{what}' is implemented in phase {phase} (see the phase plan). Nothing was run.",
        fg=typer.colors.YELLOW,
        err=True,
    )
    raise typer.Exit(code=2)


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    _setup_logging(verbose)


@app.command()
def doctor() -> None:
    """Print versions, accelerator, disk space and data status."""
    import mne
    import numpy as np
    import pyriemann
    import sklearn
    import torch

    paths = get_paths()
    typer.echo(f"python       {sys.version.split()[0]} ({platform.machine()})")
    for name, mod in [
        ("numpy", np),
        ("mne", mne),
        ("scikit-learn", sklearn),
        ("pyriemann", pyriemann),
        ("torch", torch),
    ]:
        typer.echo(f"{name:<13}{mod.__version__}")
    try:
        import braindecode

        typer.echo(f"{'braindecode':<13}{braindecode.__version__}")
    except ImportError:
        typer.echo("braindecode not installed")
    accel = (
        "cuda"
        if torch.cuda.is_available()
        else "mps"
        if torch.backends.mps.is_available()
        else "cpu only"
    )
    typer.echo(f"accelerator  {accel}")
    free = shutil.disk_usage(paths.root).free / 1e9
    typer.echo(f"disk free    {free:.1f} GB at {paths.root}")
    n_mat = len(list(paths.processed.glob("sub-*/*/*.mat"))) if paths.processed.exists() else 0
    typer.echo(f"data         {n_mat} preprocessed run files in {paths.processed}")
    n_npz = len(list(paths.epochs.glob("*.npz"))) if paths.epochs.exists() else 0
    typer.echo(f"epochs       {n_npz} cached session files in {paths.epochs}")


@data_app.command("download")
def data_download(
    archive: Annotated[str, typer.Option(help="processeddata or sourcedata")] = "processeddata",
    keep_zip: Annotated[bool, typer.Option(help="Keep the zip after a verified unzip.")] = False,
    metadata: Annotated[bool, typer.Option(help="Also fetch the BIDS metadata files.")] = True,
) -> None:
    """Download an archive (resumable), check md5, unzip, verify, then remove the zip."""
    from sixthfinger.data import download as dl

    cfg = load_data_config()
    paths = get_paths()
    arc = cfg.figshare.archives[archive]
    if metadata:
        article = dl.fetch_article(cfg.figshare.article_api)
        if article.get("version") != cfg.figshare.version:
            typer.secho(
                f"figshare article is now version {article.get('version')}, "
                f"config pins {cfg.figshare.version}. Check what changed before continuing.",
                fg=typer.colors.YELLOW,
            )
        dl.download_metadata(article, cfg.figshare.metadata_files, paths.metadata)
        typer.echo(f"metadata  -> {paths.metadata}")
    zip_path = paths.figshare / arc.filename
    dest = paths.data / arc.extract_to
    listing = paths.audit / f"{archive}_listing.tsv"
    if not zip_path.exists() and listing.exists() and not dl.verify_extracted(dest, listing):
        typer.echo(f"{archive}: already extracted and verified in {dest}")
        return
    dl.download_file(
        cfg.figshare.url_for(archive),
        zip_path,
        expected_size=arc.size_bytes,
        expected_md5=arc.md5,
    )
    typer.echo(f"md5 ok    {arc.md5}  {zip_path}")
    n = dl.unzip_verified(zip_path, dest, expected_files=arc.expected_files, listing_path=listing)
    problems = dl.verify_extracted(dest, listing)
    if problems:
        typer.secho(f"{len(problems)} problems after unzip, zip kept: {problems[:5]}", fg="red")
        raise typer.Exit(code=1)
    typer.echo(f"unzipped  {n} data files -> {dest} (listing: {listing})")
    if not keep_zip:
        zip_path.unlink()
        typer.echo(f"removed   {zip_path}")


@data_app.command("verify")
def data_verify(archive: Annotated[str, typer.Option()] = "processeddata") -> None:
    """Check the extracted files against the listing saved at unzip time."""
    from sixthfinger.data.download import verify_extracted

    cfg = load_data_config()
    paths = get_paths()
    arc = cfg.figshare.archives[archive]
    listing = paths.audit / f"{archive}_listing.tsv"
    if not listing.exists():
        typer.secho(f"No listing at {listing}; run `sixthfinger data download` first.", fg="red")
        raise typer.Exit(code=1)
    dest = paths.data / arc.extract_to
    problems = verify_extracted(dest, listing)
    suffix = ".mat" if archive == "processeddata" else ".set"
    n = len(list(dest.glob(f"sub-*/*/*{suffix}")))
    expected = arc.expected_files if suffix == ".mat" else arc.expected_files // 2
    if problems or n != expected:
        typer.secho(f"FAIL: {n} {suffix} files (expected {expected}); {problems[:10]}", fg="red")
        raise typer.Exit(code=1)
    typer.echo(f"OK: {n} {suffix} files, sizes match {listing.name}")


@data_app.command("audit")
def data_audit() -> None:
    """Integrity audit of every run (events, durations, duplicates)."""
    _not_yet("P02", "data audit")


@epochs_app.command("build")
def epochs_build(
    subjects: Annotated[str, typer.Option(help="Comma-separated ids or 'all'.")] = "all",
) -> None:
    """Cut [tmin, tmax) windows around each cue and cache them per session."""
    _not_yet("P03", "epochs build")


@app.command()
def run(
    config: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    subjects: Annotated[str, typer.Option()] = "all",
    quick: Annotated[bool, typer.Option(help="Small grid for smoke tests.")] = False,
) -> None:
    """Run an experiment described by a config in configs/experiments/."""
    _not_yet("P05/P06", "run")


@export_app.command("demo")
def export_demo() -> None:
    """Export the demo model to ONNX and build the demo bundle."""
    _not_yet("P10", "export demo")


if __name__ == "__main__":
    app()
