# Figures from the web page

The drawings and charts of the project page (`web/`), each cut out on its own for the paper,
the report and the slides. They are made by one command and never edited by hand:

```sh
npm --prefix web run figures             # build the site, export every figure
npm --prefix web run figures -- leak     # only some
```

`web/scripts/export-figures.mjs` builds the site, opens it in Playwright's Chromium with the
demo switched off, and for each figure keeps only that element on the page, at a fixed width and
at rest: no pointer, no hover card, no animation, no slider or toggle. It writes:

- `<name>.pdf`: vector, from Chromium's print to PDF, the page sized to the figure. Fonts are
  embedded as TrueType (Inter, cut into one static font per weight, because Chromium writes a
  variable font as Type 3, which IEEE's PDF checks refuse). The soft shadows under the drawn
  objects are the only raster parts.
- `<name>.png`: the same at 3x, white background, for slides.
- `<name>.svg`: only where the figure is one SVG; computed styles written in and Inter embedded,
  so it looks the same outside the page.

The PDFs the paper is likely to use are copied to `paper/figures/web/` on every run (the list is
`IN_PAPER` in the script); the report finds all of them as `web/<name>.pdf` through its
`\graphicspath`. Every number comes from `web/src/explain/data.json`, which
`scripts/make_web_explain_data.py` writes from `results/summary/`.

## Sizes and legibility

Each figure is laid out at a fixed width in CSS pixels and has a target: one column of the IEEE
paper (3.5 in) or its full width (7.16 in, `figure*`). The script checks that its smallest text
is at least 7 pt at that width and at least 24 px on a 1920 px slide, and fails otherwise. The
lettering drawn on the model box ("EEGNet") is part of the drawing and not checked.

```latex
\includegraphics[width=\columnwidth]{figures/web/leak.pdf}    % paper, column
\includegraphics[width=\textwidth]{figures/web/system.pdf}    % paper, figure*
\includegraphics[width=0.6\textwidth]{web/setup.pdf}          % report
```

## The figures

Size is the file in CSS px (1 px = 0.75 pt in the PDF); the PNG is three times that.

| Name | Files | Size, target | What it shows | Drawn from | Where on the page |
|---|---|---|---|---|---|
| `system` | pdf, png | 696 x 278, full | The whole system on one bench: cap, amplifier, the 4 s frame, the model with its three lamps, the robotic finger, numbered and named | A drawing; part names in `iso/chain.ts` | 1, What is this? |
| `trial` | pdf, png | 462 x 194, column | One trial as the patient sees it: rest (a cross, 7 s), get ready (1 s), imagine (6 s), with the two 4 s pieces the model reads bracketed on the time strip | Timings as the dataset paper gives them (`PatientSees.tsx`) | 3, Did you record the brain signals? (What is in it) |
| `session` | pdf, png | 772 x 185, full | Trials, runs and sessions: 4 runs of 20 trials, runs 1 and 2 to learn, 3 and 4 to test; three sessions over time | Study design (`Session.tsx`) | 3, under the answer |
| `sensors` | pdf, png, svg | 245 x 310, column | The 40 sensors on a template head; the seven over the movement strip in white | `electrodes` (MNE template positions), `head.json` | 3, What is in it |
| `rhythm` | pdf, png, svg | 719 x 238, column | The rhythm over the hand area while imagining, with its resting size in grey behind it | `erd.sixth_finger.mean` (`eda_erd_values.csv`); the wave is a drawing, its fall the measured average | 1, What does the model look for? |
| `rhythm-measured` | pdf, png, svg | 445 x 244, column | How much that rhythm fell in each patient, hand and sixth finger | `erd` (`eda_erd_values.csv`) | 5, Why can't it tell the hand from the sixth finger? |
| `model` | pdf, png | 778 x 255, full | EEGNet as five stations: 4 s from 40 sensors, rhythms, sensors, combining, the three lamps | `demo.parameters`, `demo.model_bytes` (`demo_model.json`); steps read from `model.onnx` (`iso/model.ts`) | 2, Can we see it work? (How the model works) |
| `leak` | pdf, png | 452 x 275, column | The paper's way and the fair test on one round of 20 trials: only the bracket of what the first step learns from differs | `leak.published`, `leak.mean_replica`, `leak.mean_leakfree` (`rq1_*.csv`) | 4, The paper reports 85%. Is that right? |
| `leak-slope` | pdf, png | 375 x 292, column | Each patient scored the published way and fairly, one line each, the average in black | `leak.replica`, `leak.leakfree`, `leak.published` | 4, Is it lower for every patient? |
| `elsewhere` | pdf, png | 772 x 436, full | The same mistake in other data: leaky (grey ring) and fair (black dot) for two motor datasets and two depression datasets | `elsewhere` (`rq1b_table.csv`, `rq5_table.csv`), `leak` | 4, Does the same mistake happen elsewhere? |
| `switch-patients` | pdf, png, svg | 427 x 244, column | Each patient's dot for sixth finger or rest, and for hand or sixth finger | `sixth.rest`, `sixth.which` (`ex4_sf_command_*.csv`) | 5, Can the sixth finger be a command of its own? |
| `switch-on` | pdf, png | 452 x 93, column | What switches the finger on, every decision: resting, imagining the hand, imagining the sixth finger | `sixth.fires.*.all` (`ex4_sf_command_table.csv`) | 5, What switches it on? |
| `switch-on-sure` | pdf, png | 452 x 93, column | The same, only when sure | `sixth.fires.*.sure` | 5, the toggle's other side |
| `switch-sure` | pdf, png, svg | 437 x 250, column | Acting only when sure: accuracy against the share of decisions taken, 95% band, each patient's own threshold as a diamond | `sixth.coverage`, `sixth.sure` (`ex4_sf_command_coverage.csv`) | 5, What if it acts only when sure? |
| `path` | pdf, png | 1012 x 395, full | A patient's path: cap on, practice, therapy, practice again; each part drawn solid (built here) or dashed (needed), with what passes between them | A drawing; parts and arrows in `Journey.tsx` | 6, How would a patient use it, and which parts are built? |
| `path-lanes` | pdf, png | 512 x 274, column | The path's setup-time lanes: practice to scale and the score it reaches, starting from nothing or from other patients | `calibration`, `later.post` via `findings.ts` (`calib_curves.csv`, `rq4_longitudinal_table.csv`) | 6, under the path |
| `setup` | pdf, png, svg | 439 x 245, column | Practice time against accuracy, learned from other patients (solid) and from nothing (dashed), 95% bands | `calibration.transfer`, `calibration.scratch` (`calib_curves.csv`) | 6, How much practice does a new patient need? |
| `later` | pdf, png | 452 x 125, column | The first day's model on the same day, two weeks and a month later, unchanged | `later` (`rq4_longitudinal_table.csv`) | 6, Does it still work another day? |
| `later-adjusted` | pdf, png | 452 x 125, column | The same after 5 practice trials of each movement on the new day | `later.*.re_setup` | 6, the toggle's other side |
| `dial-published` | pdf, png, svg | 261 x 193, slides | The fair score (black needle) against the paper's way, rebuilt (grey); the hatched arc is guessing | `leak.mean_leakfree`, `leak.mean_replica` | 4, beside the answer |
| `dial-command` | pdf, png, svg | 261 x 193, slides | Sixth finger or rest (black) against hand or sixth finger (grey) | `sixth.rest.mean`, `sixth.which.mean` | 5, beside the answer |
| `dial-use` | pdf, png, svg | 261 x 193, slides | After the shortest practice, from other patients (black) against from nothing (grey) | `calibration.transfer[0]`, `calibration.scratch[0]` | 6, beside the answer |

The dials' SVG is the dial alone; their two-line reading is in the PDF and PNG.

The report (12 pt body, 5.77 in text width) uses its own cuts of the five wide figures, laid out
narrower so that their words stay at 8 pt or more across the text width: `system-report`,
`session-report`, `model-report`, `elsewhere-report` and `path-report` (pdf, png). They are the
same drawings; `system-report` enlarges the numbered pins and `path-report` wraps the arrows'
words so the two labels keep apart.

## Document variants

The page's look never changes. The exporter adds its own stylesheet
(`web/scripts/export-figures.css`) under a class only it sets, and through it every figure loses
its caption, hint and controls (they go in the document's caption) and keeps its own drawing.
Beyond that:

- `trial`: each screen's words on one line, 13.5 px.
- `leak`: the key keeps only its names, the paragraph under it goes; laid out at phone width so
  the labels sit above the squares.
- `path`: the sentences go, the lanes move to `path-lanes`, labels grow to 15 to 18 px.
- `path-lanes`: only the two steps with practice, as two columns, labels 15 px.
- `rhythm`: shown while imagining (the page starts at rest), the resting wave a shade darker.
- `elsewhere`: the note on depression goes, axis labels 13 px.
- Charts: no point ringed as if picked, no slider guide line, no outlined text.

When the page changes, run the command again and look at the PNGs before committing.
