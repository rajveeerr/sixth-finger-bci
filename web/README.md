# Demo frontend

A React app: the project explained in figures, and the demo, which shows the EEG
stream, what the model reads and a drawn hand with a robotic sixth finger.

```sh
npm ci
npm run dev        # http://localhost:5173, expects the server on :8000 (make server)
npm run test       # unit tests
npm run e2e        # browser tests (first time: npx playwright install chromium)
npm run build      # production build in dist/
```

The demo bundle (held-out trials, the ONNX model and precomputed predictions)
lives in `public/demo/`; it is produced by `make demo-bundle` in the project root.
A build with `VITE_SERVER_URL=none` decodes in the browser from the start (the
static site on Vercel); otherwise the page tries the server first and falls back
to the browser, then to the stored predictions.

## The page

`App.tsx` tells the project as the questions an examiner would ask, in order
(`explain/questions.ts`), one chapter each in `explain/chapters/`: the question as
its title, the answer in one sentence, the figure that shows it, and the evidence
folded under "How we know". The demo is three steps read left to right: what the
patient is told (`Told`), their brain signal (`EEGPanel`, `TrialStrip`) and what
the model reads, with the hand (`PredictionCard`, `hands/IsoHand.tsx`). The
figures live in `src/explain/`: isometric drawings on the drawing core in
`explain/iso/kit.ts` (the bench in `iso/chain.ts`, the head in `iso/head.ts`),
charts in `explain/charts.tsx`, the numbers the chapters say in words in
`explain/findings.ts`.

The numbers in those figures come from the results summaries. After any of them
changes, regenerate the page's copy (a Python test fails until you do):

```sh
uv run python scripts/make_web_explain_data.py   # writes src/explain/data.json
```
