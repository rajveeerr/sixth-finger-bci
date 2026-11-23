# Paper

IEEE conference paper (IEEEtran). Build with `make paper` from the repository
root (Tectonic) or upload this folder to Overleaf.

- `main.tex` – document skeleton
- `sections/` – one file per section
- `generated/numbers.tex` – every reported number, generated from `results/summary/`; never edited by hand
- `figures/` – figure PDFs copied from `docs/figures/`
- `references.bib` – verified references
- `college/` – the same study in the college's IEEE format (one column, eight sections with
  an ablation study, 20 pages); `make paper-college` writes `paper/build/college.pdf` from the
  same numbers, references and figures
- `college/sixth-finger-bci-ieee.docx` – the college paper as an editable Word file, set on
  IEEE's own Word template (conference template, A4 file from ieee.org, turned to one column and
  the LaTeX paper's sizes). Built by
  `uv run --with python-docx==1.2.0 --with pymupdf==1.26.5 python paper/college/build_docx.py`
  from the same sources: Tectonic compiles `college/main.tex` for the section, figure, table,
  equation and citation numbers (`.aux`) and the reference list (`.bbl`); every number comes from
  `generated/numbers.tex` and a missing or TBD macro stops the build. Equations are Word
  equations, tables Word tables, and each figure is typeset by LaTeX alone on a page, cropped and
  rasterised at 600 dpi at its printed width. `--pdf` renders it with LibreOffice to
  `build/college-docx.pdf`; `--check` compares its text with `build/college.pdf` in runs of eight
  words. The template is read from `~/Downloads/conference-template-a4.docx` or downloaded
  (`--template PATH` otherwise).
