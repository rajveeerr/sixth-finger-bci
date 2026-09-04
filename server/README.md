---
title: Sixth-Finger BCI server
emoji: 🧠
colorFrom: blue
colorTo: red
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Sixth-Finger BCI inference server

Streams held-out EEG trials and the decoder's predictions over a WebSocket to
the demo frontend.

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | status, model checksum, active streams |
| `GET /api/info` | bundle, channels, classes, model and limits |
| `GET /api/trials` | trials in the bundle with their labels |
| `WS /ws/stream?mode=trial\|continuous&speed=1&start=0&loop=true` | EEG chunks, phases and predictions |

Run locally from the repository root with `make server` (port 8000).

Environment variables: `BUNDLE_DIR`, `ALLOWED_ORIGINS` (comma-separated, default `*`),
`MAX_SPEED`, `MAX_STREAMS`, `PORT`.

EEG data: Wang et al., Scientific Data 13, 1109 (2026), CC BY 4.0. Research
prototype, not a medical device.
