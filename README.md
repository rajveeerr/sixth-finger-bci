# Sixth-Finger BCI

**EEG-Based Adaptive Brain–Computer Interface for Novel Artificial Limb Control**

B.Tech Minor Project, Electronics and Communication Engineering (AI & ML),
Maharaja Surajmal Institute of Technology, Delhi (GGSIPU).

Team: Rajveer Singh, Vivek Yadav, Ansh Dahiya. Guide: Dr. Suman Lata.

---

## What this project does

A person imagines a movement. Their EEG is recorded. A decoder recognises which
movement was imagined, and a drawn hand on screen performs it, including an extra
robotic "sixth finger" that does not exist on the human body.

Live demo: https://sixthfinger.rajveers.com (the demo alone at `/live`). The model runs on
the site's server, or in the browser if that cannot be reached or the reader chooses it, on
held-out trials of one patient.

The research question behind the demo:

> Can knowledge learned from conventional motor-imagery EEG reduce the amount
> of calibration data a decoder needs to learn a **novel** artificial motor
> command?

We study this on the public longitudinal dataset of Wang et al. (Scientific
Data, 2026): 24 stroke patients performing affected-hand motor imagery,
sixth-finger motor imagery and rest, recorded before training, after training
and at follow-up.

## Repository layout

| Path | Contents |
|------|----------|
| `src/sixthfinger/` | Python package: data loading, preprocessing, models, transfer learning, evaluation |
| `configs/` | Experiment configurations (YAML) |
| `scripts/` | Command-line entry points for each pipeline stage |
| `tests/` | Unit tests, including data-leakage checks |
| `notebooks/` | Exploratory analysis (outputs stripped) |
| `server/` | FastAPI inference service that streams predictions over WebSocket |
| `web/` | React demo page: the project explained, live EEG view and the hand |
| `paper/` | Research paper (LaTeX, IEEE format) |
| `report/` | Project report |
| `docs/` | Runbook, dataset card, results and figures |

## Quick start

```sh
make setup        # Python env (uv), web deps, git hooks
make data         # download and verify the dataset (about 3.5 GB)
make test         # unit tests and leakage checks
make demo         # inference server + demo page on http://localhost:5173
```

Every command, what it should print and how to tell that it worked is in
[`docs/RUNBOOK.md`](docs/RUNBOOK.md).

## Dataset and attribution

Wang, Z., Liu, Y., Huang, S. et al. *A multi-paradigm and longitudinal EEG
dataset including the "sixth-finger" and "affected-hand" motor imagery of
stroke patients.* Scientific Data 13, 1109 (2026).
https://doi.org/10.1038/s41597-026-07787-y. Data: figshare,
https://doi.org/10.6084/m9.figshare.30509165, licensed CC BY 4.0.

The demo ships a small number of held-out trials from this dataset, unmodified
apart from windowing, under the same licence.

## Scope

This is a research prototype. It does not read arbitrary thoughts, it is not a
medical device and it makes no clinical claims.
