"""Copy the paper and the slides into web/public/docs/, where the site serves them.

make site-docs                                # builds the paper first
uv run python scripts/copy_site_docs.py

Each file gets a stable name, so a link to it keeps working, and web/src/explain/documents.json
lists what was copied with its size, for the page's links. The report stays off until its
cover carries the enrolment number and the submission date: then add "report" to PUBLISHED.
"""

from __future__ import annotations

import json
import shutil

from sixthfinger.paths import find_root

# Each document and its files: the build product, the name on the site, and whether it may be
# missing (the slides' PDF exists only once someone has exported one).
DOCUMENTS = {
    "paper": [("paper/build/main.pdf", "sixth-finger-bci-paper.pdf", False)],
    "slides": [
        ("report/slides/sixth-finger-bci.pptx", "sixth-finger-bci-slides.pptx", False),
        ("report/slides/sixth-finger-bci.pdf", "sixth-finger-bci-slides.pdf", True),
    ],
    "report": [("report/build/main.pdf", "sixth-finger-bci-report.pdf", False)],
}
PUBLISHED = ["paper", "slides"]
FORMATS = {".pdf": "PDF", ".pptx": "PowerPoint"}
MAX_BYTES = 5_000_000
OUT_DIR = ("web", "public", "docs")
OUT_LIST = ("web", "src", "explain", "documents.json")


def main() -> None:
    root = find_root()
    out_dir = root.joinpath(*OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    listed = []
    for doc in PUBLISHED:
        for source, name, optional in DOCUMENTS[doc]:
            src = root / source
            if not src.exists():
                if optional:
                    continue
                raise SystemExit(f"{source} is missing: build it first")
            size = src.stat().st_size
            if size > MAX_BYTES:
                raise SystemExit(f"{source} is {size / 1e6:.1f} MB, over the 5 MB limit")
            shutil.copyfile(src, out_dir / name)
            listed.append({"doc": doc, "file": name, "format": FORMATS[src.suffix], "bytes": size})
    # A document taken off the list leaves the site too.
    kept = {item["file"] for item in listed}
    for files in DOCUMENTS.values():
        for _source, name, _optional in files:
            if name not in kept:
                (out_dir / name).unlink(missing_ok=True)
    root.joinpath(*OUT_LIST).write_text(json.dumps(listed, indent=1) + "\n")
    for item in listed:
        print(f"{'/'.join(OUT_DIR)}/{item['file']}  {item['bytes'] / 1e6:.1f} MB")
    print(f"wrote {'/'.join(OUT_LIST)}")


if __name__ == "__main__":
    main()
