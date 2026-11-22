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
