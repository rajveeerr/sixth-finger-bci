# Project report

University minor project report (LaTeX). Build from the repository root with
`make report`, or `make -C report docx` for a Word copy (needs pandoc).

Numbers come from `../paper/generated/numbers.tex` (write `\pct{\macro}` for a
percentage), references from `../paper/references.bib`, figures from `../docs/figures/`
(the page's drawings as `web/<name>.pdf`) and `../paper/figures/`. `figures/approach.tex`
is a TikZ drawing made for Chapter 3; `figures/external/` holds the credited photos.

Format, from MSIT's project report guidelines and front-pages template: A4; margins 1 in
top, bottom and right and 1.5 in left; Times 12 pt, justified, at Word's 1.5 line spacing
(20.7 pt); page numbers at the bottom centre, roman from the declaration (ii) and arabic from
Chapter 1. The front pages follow the template: cover, declaration, certificate,
acknowledgement, abstract, abbreviations, lists of figures and tables, then the contents.
References use `msit.bst`, the guidelines' formats in cited order. The head of department is
the `\HODName` macro in `main.tex`.

Enrolment numbers are not in the repository. For the printed copy, `frontmatter/ids.local.tex`
(ignored by git) redefines `\StudentOne` to `\StudentThree` as "Name (Enrolment No.)";
`make report` then prints them on the cover, declaration and certificate. `make -C report
public` builds the edition for the site, which prints names only, and `make site-docs` copies
that one.
