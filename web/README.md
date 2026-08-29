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
