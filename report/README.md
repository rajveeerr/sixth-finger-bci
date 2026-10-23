# Project report

University minor project report (LaTeX). Build from the repository root with
`make report`, or `make -C report docx` for a Word copy (needs pandoc).

Numbers come from `../paper/generated/numbers.tex` (write `\pct{\macro}` for a
percentage), references from `../paper/references.bib`, figures from `../docs/figures/`
(the page's drawings as `web/<name>.pdf`) and `../paper/figures/`. `figures/approach.tex`
is a TikZ drawing made for Chapter 3; `figures/external/` holds the credited photos.

Format: A4, Times 12 pt, 1.5 spacing, margins left 1.5 in and 1 in elsewhere, roman
numbers for the front matter (none printed on the cover, declaration, certificate and
acknowledgement), arabic from Chapter 1, IEEE references. The contents, the lists and
the references are single-spaced. This follows GGSIPU's
published thesis format; MSIT's own rules still need confirming with the department.

Roll and enrolment numbers are not in the repository. For the printed copy, put the cover's
table of names and numbers in `frontmatter/ids.local.tex` (ignored by git); `make report`
then prints them. `make -C report public` builds the edition for the site, which prints names
only, and `make site-docs` copies that one.
