# The paper for Proceedings on Engineering Sciences

The same paper as `paper/main.tex`, set in the journal's Word template: its header and logos,
two columns, its paragraph styles, author-year citations and the closing author blocks.

```sh
uv run --with python-docx==1.2.0 python paper/pes/build_pes.py --pdf
```

- Needs the journal's template, by default `~/Downloads/PES 2026.docx` (`--template PATH`
  otherwise). Only its layout is kept; its sample paper is removed.
- Text from `paper/main.tex` and `paper/sections/`, every number from
  `paper/generated/numbers.tex`, references from `paper/references.bib`. The build stops on a
  macro that is missing or still TBD, a citation not in the bibliography, or an anchor for an
  added figure or equation that the paper no longer has.
- Figures from `docs/figures/web/` and `docs/figures/` (PNG). Wide drawings span both columns.
- `--pdf` converts with LibreOffice
  (`/Applications/LibreOffice.app/Contents/MacOS/soffice --headless --convert-to pdf`). Run
  headless, LibreOffice does not see the Mac's fonts, so the script gives a fresh profile its own
  copy of Times New Roman; the PDF then embeds Times New Roman, with Caladea and Liberation Serif
  standing in for Cambria and Cambria Math in the running head and the equations, as in the
  journal's own sample PDF.
- `--overlap FILE...` lists every run of eight or more words the result shares with each file
  (a `.docx` or plain text).

Still to fill in before submission: the three student authors' e-mail addresses (red in the
author blocks), and the journal's volume, issue, pages and DOI (red in the header, as in the
template).
