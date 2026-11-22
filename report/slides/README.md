# The final presentation

`sixth-finger-bci.pptx` is the deck for the final evaluation: a 15-minute talk, a 3-minute live
demo, then questions, with backup slides after the closing slide. It follows the order of the
questions on the project page (sixth-finger-bci.vercel.app). `outline.md` lists every slide with its
headline, figure and time.

## Build it

```sh
uv run --with python-pptx==1.0.2 python report/slides/build_slides.py
uv run --with python-pptx==1.0.2 python report/slides/build_slides.py --pdf   # also a PDF
```

`python-pptx` is added for the run only; it is not a dependency of the project. The script
writes `sixth-finger-bci.pptx` and `outline.md` and refuses to write anything if one of its checks
fails:

- every number on a slide is a macro of `paper/generated/numbers.tex`, written in the slide text
  as `{macroName}`; a digit typed by hand fails the build (the only exceptions are citation years,
  run and session names, axis ticks and question numbers);
- a rounded number is rounded from the macro, and a value that could round either way stops the
  build;
- the values printed in a page figure must equal the macros, through `web/src/explain/data.json`;
- no text under 18 pt, and no figure placed so small that its own smallest text prints under
  18 pt; text that would not fit its box fails;
- the main slides come to exactly 15:00; the file stays under 5 MB.

The speaker notes of every slide hold the time, two or three sentences to say, and every number
on the slide or in the notes with its macro and its results file under `results/`. Settings that
are not results (the 4 s window, the gate) name the file that fixes them.

## Change it

Edit the text in `build_slides.py` and build again, so the numbers stay tied to the paper. A
change made in PowerPoint is lost at the next build. The look is the page's: colours read from
`web/src/styles.css`, Inter for all text, Georgia italic for the question numbers.

## Present it

- Install Inter (free, rsms.me/inter) on the presenting laptop. Without it PowerPoint substitutes
  another font and some lines wrap differently.
- The demo slide (17) names the page to open, `sixth-finger-bci.vercel.app/live`; the backup video
  is in `docs/RUNBOOK.md`.
- Backup slides 22 to 29: the leak patient by patient, the same mistake in other datasets, the
  calibration curves of every method, the healthy grasp benchmark, the replay as if live, the
  demo patient, one trial, and the data audit.

## Look at it

```sh
uv run --with python-pptx==1.0.2 python report/slides/preview_slides.py
```

draws every slide at 1366 x 768, a projector's size, into `previews/` (not committed), with
`contact.png` showing all of them. It reads the `.pptx` back and lays each slide out again in
HTML with the page's Inter, photographed by the page's Playwright Chromium (`npm --prefix web ci`
first), so it works without LibreOffice, and lists any text that runs past its box.

## PDF

`--pdf` converts through LibreOffice (`soffice`) or, on a Mac, Keynote. On the Mac the deck was
built on, LibreOffice is not installed and Keynote's import of the `.pptx` did not return, so no
PDF is committed; export one from PowerPoint or Keynote (File, Export, PDF) on the presenting
laptop, or run `--pdf` where LibreOffice is installed.

## The college version

`college/Sixth-Finger-BCI-Final-PPT.pptx` (and its PDF) is the same talk in the college's own
template for the final presentation of 25 November 2026: its title slide with the MSIT logo, its
background and Times New Roman titles, and its order (title, contents, introduction, proposed
solution, dataset, experimental details, results and analysis, conclusion, questions, thank you),
with the live demo just before questions. Talk 15:00, demo 3:00; the speaker notes give the time,
what to say and every number's macro and results file, as above.

```sh
uv run --with python-pptx==1.0.2 python report/slides/college/build_college_ppt.py --pdf --previews
```

`college/build_college_ppt.py` starts from a copy of the template (`~/Downloads/Final PPT.pptx`,
or `--template <path>`), reuses its ten slides and adds the rest from its "Title and Content"
layout, so its master, layouts, logo and background stay as they are. Numbers come through the
macros of `build_slides.py`, and the build fails on text under 16 pt, text that would not fit
its box, a figure whose smallest text would print under 16 pt, or a digit typed by hand.
`--pdf` exports through LibreOffice with a private profile that holds the template's fonts and
fails unless the PDF embeds only Times New Roman and Wingdings 3; `--previews` draws its pages
into `college/previews/` (not committed).

This deck carries the students' enrolment numbers. It is not one of the documents
`scripts/copy_site_docs.py` copies to the site, and it must never be put there.
