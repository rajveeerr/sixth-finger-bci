% References in the format of MSIT's project report guidelines, in the order cited:
%   book        Author(s). Book title. Location: Publisher, year, pp.
%   article     Author(s). "Article title." Journal, vol., pp., date.
%   proceedings Author(s). "Article title," in Proc. Conference, year, pp.
%   patent      Author(s). "Title." Country Patent number, date.
%   web         Author(s). "Title." Internet: URL, date [date accessed].
% Entries with neither journal nor proceedings (software, datasets, preprints) are cited
% as web pages; \BibAccessed is the date the bibliography's links were last checked.

ENTRY
  { address archiveprefix author booktitle doi eprint journal month nationality note
    number pages publisher series title type url volume year }
  {}
  { label }

INTEGERS { nameptr namesleft numnames }

STRINGS { s t }

FUNCTION {not} { { #0 } { #1 } if$ }
FUNCTION {and} { 'skip$ { pop$ #0 } if$ }
FUNCTION {or} { { pop$ #1 } 'skip$ if$ }

% More than six authors are cut to the first and "et al.", as IEEE does.
FUNCTION {format.names}
{ 's :=
  s num.names$ 'numnames :=
  numnames #6 >
    { s #1 "{f{.}.~}{vv~}{ll}{, jj}" format.name$ " et~al." * }
    { #1 'nameptr :=
      numnames 'namesleft :=
      ""
        { namesleft #0 > }
        { s nameptr "{f{.}.~}{vv~}{ll}{, jj}" format.name$ 't :=
          nameptr #1 >
            { t "others" =
                { " et~al." * }
                { namesleft #1 =
                    { numnames #2 > { "," * } 'skip$ if$ " and " * t * }
                    { ", " * t * }
                  if$
                }
              if$
            }
            { t * }
          if$
          nameptr #1 + 'nameptr :=
          namesleft #1 - 'namesleft :=
        }
      while$
    }
  if$
}

FUNCTION {authors.block}
{ author empty$ { "" } { author format.names add.period$ " " * } if$ }

FUNCTION {date}
{ month empty$ { year } { month " " * year * } if$ }

FUNCTION {multi.page.check}
{ 't :=
  #0 'nameptr :=
    { t empty$ not }
    { t #1 #1 substring$ duplicate$ "-" = swap$ duplicate$ "," = swap$ "+" = or or
        { #1 'nameptr := "" 't := }
        { t #2 global.max$ substring$ 't := }
      if$
    }
  while$
  nameptr
}

FUNCTION {pages.part}
{ pages multi.page.check { "pp.~" pages * } { "p.~" pages * } if$ }

% A single number of three digits or fewer is a page; anything else is an article number.
FUNCTION {article.pages.part}
{ pages multi.page.check
    { "pp.~" pages * }
    { pages text.length$ #4 < pages purify$ pages = and
        { "p.~" pages * }
        { "art.~no.~" pages * }
      if$
    }
  if$
}

% "Proceedings of the X" becomes "Proc. X"; any other name is prefixed with "Proc.".
FUNCTION {proc.name}
{ booktitle 's :=
  s #1 #19 substring$ "Proceedings of the " =
    { "Proc. " s #20 global.max$ substring$ * }
    { s #1 #15 substring$ "Proceedings of " =
        { "Proc. " s #16 global.max$ substring$ * }
        { "Proc. " s * }
      if$
    }
  if$
}

FUNCTION {web.address}
{ url empty$
    { doi empty$
        { eprint empty$ { "" } { "https://arxiv.org/abs/" eprint * } if$ }
        { "https://doi.org/" doi * }
      if$
    }
    { url }
  if$
}

FUNCTION {begin.bib}
{ preamble$ empty$ 'skip$ { preamble$ write$ newline$ } if$
  "\providecommand{\url}[1]{\texttt{#1}}" write$ newline$
  "\providecommand{\BibAccessed}{}" write$ newline$
  "\begin{thebibliography}{99}" write$ newline$
}

FUNCTION {end.bib}
{ newline$ "\end{thebibliography}" write$ newline$ }

FUNCTION {begin.entry}
{ newline$ "\bibitem{" cite$ * "}" * write$ newline$ }

FUNCTION {emit} { write$ newline$ }

FUNCTION {article}
{ begin.entry
  authors.block "``" * title add.period$ * "'' " * journal *
  volume empty$ 'skip$ { ", vol.~" * volume * } if$
  pages empty$ 'skip$ { ", " * article.pages.part * } if$
  ", " * date * "." *
  emit
}

FUNCTION {book}
{ begin.entry
  authors.block title add.period$ * " " *
  address empty$ 'skip$ { address * ": " * } if$
  publisher empty$ 'skip$ { publisher * ", " * } if$
  year *
  pages empty$ 'skip$ { ", " * pages.part * } if$
  "." *
  emit
}

FUNCTION {inproceedings}
{ begin.entry
  authors.block "``" * title * ",'' in " * proc.name *
  volume empty$ 'skip$ { ", vol.~" * volume * } if$
  ", " * year *
  pages empty$ 'skip$ { ", " * pages.part * } if$
  "." *
  emit
}

FUNCTION {patent}
{ begin.entry
  authors.block "``" * title add.period$ * "'' " *
  nationality empty$ 'skip$ { nationality * " " * } if$
  "Patent " * number * ", " * date * "." *
  emit
}

FUNCTION {misc}
{ begin.entry
  authors.block "``" * title add.period$ * "'' " *
  note empty$ 'skip$ { note add.period$ * " " * } if$
  "Internet: \url{" * web.address * "}, " * year * " [\BibAccessed]." *
  emit
}

FUNCTION {conference} { inproceedings }
FUNCTION {incollection} { inproceedings }
FUNCTION {online} { misc }
FUNCTION {electronic} { misc }
FUNCTION {manual} { misc }
FUNCTION {techreport} { misc }
FUNCTION {phdthesis} { misc }
FUNCTION {mastersthesis} { misc }
FUNCTION {unpublished} { misc }
FUNCTION {standard} { misc }
FUNCTION {default.type} { misc }

MACRO {jan} {"Jan."}
MACRO {feb} {"Feb."}
MACRO {mar} {"Mar."}
MACRO {apr} {"Apr."}
MACRO {may} {"May"}
MACRO {jun} {"Jun."}
MACRO {jul} {"Jul."}
MACRO {aug} {"Aug."}
MACRO {sep} {"Sep."}
MACRO {oct} {"Oct."}
MACRO {nov} {"Nov."}
MACRO {dec} {"Dec."}

READ

EXECUTE {begin.bib}

ITERATE {call.type$}

EXECUTE {end.bib}
