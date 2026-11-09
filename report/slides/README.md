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
