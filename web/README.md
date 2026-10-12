# Demo frontend

React + three.js (via React Three Fiber) app that shows the EEG stream, the
decoded intent and a 3D hand with a robotic sixth finger.

```sh
npm ci
npm run dev        # http://localhost:5173, expects the server on :8000 (make server)
npm run test       # unit tests
npm run e2e        # browser tests (first time: npx playwright install chromium)
npm run build      # production build in dist/
```

The demo bundle (held-out trials, the ONNX model and precomputed predictions)
lives in `public/demo/`; it is produced by `make demo-bundle` in the project root.

## The page

The first screen is the instrument: Fig. 1 the EEG and the trial drawn to scale
(`EEGPanel`, `TrialStrip`), Fig. 2 the 3D hand (`components/Hand/`, loaded as its
own chunk), Fig. 3 the decision (`PredictionCard`), and the playback controls.
Below it, `src/explain/` explains the project in figures: Fig. 4 is the signal
chain as an isometric bench (`explain/iso/chain.ts` on the drawing core in
`explain/iso/kit.ts`), live with the stream; Figs. 5 to 12 are plots and diagrams.

The numbers in those figures come from the results summaries. After any of them
changes, regenerate the page's copy (a Python test fails until you do):

```sh
uv run python scripts/make_web_explain_data.py   # writes src/explain/data.json
```
