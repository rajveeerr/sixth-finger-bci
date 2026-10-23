# The final presentation

Written by `build_slides.py`; do not edit by hand. Every number in a headline is filled
from `paper/generated/numbers.tex`. The talk is 15 minutes and the demo 3 more; the
backup slides follow the closing slide. Figures are under `docs/figures/`; a cut one
shows only its drawing, its words set on the slide.

| # | Question | Headline | Figure | Time |
|---|---|---|---|---|
| 1 |  | Sixth-Finger BCI | `hand_poses.png` (cut) | 0:20 |
| 2 | 1 What problem does it solve? | A stroke often leaves one hand too weak to grip; a robotic sixth finger worn on that wrist can grip for it | `hand_poses.png` (cut) | 0:50 |
| 3 | 2 What are the sixth finger and a BCI? | A brain-computer interface: an EEG cap reads the brain, and a model moves the finger when the wearer imagines it | `web/system.png` (cut) | 1:00 |
| 4 | 2 What are the sixth finger and a BCI? | The model looks for a rhythm over the hand area that weakens when a person imagines moving, by about as much for both | `web/rhythm-measured.png` | 0:40 |
| 5 | 3 Whose data is it? | We recorded no brain signals: we used a public recording of 24 stroke patients | drawn on the slide | 0:50 |
| 6 | 4 The paper reports 85%. Is that right? | The paper's 85%: how often its method told an imagined hand from an imagined sixth finger | `hand_poses.png` (cut) | 0:40 |
| 7 | 4 The paper reports 85%. Is that right? | Too high: the method's first step studied the test trials too, an exam seen in advance | `web/leak.png` | 1:00 |
| 8 | 4 The paper reports 85%. Is that right? | Tested fairly, the same method scores 58.5%: barely better than guessing, and lower for all 22 patients | `web/dial-published.png` (cut) | 0:45 |
| 9 | 5 What are CSP, LDA and EEGNet? | CSP and LDA are the paper's two-step method; EEGNet, the model in our demo, learns both steps from examples | `web/sensors.png`, `web/model.png` (cut) | 0:50 |
| 10 | 6 How much practice does a new patient need? | Learning from other patients, a new patient starts at 56.1% after 30 s of practice; from nothing, 39.6% | `web/dial-use.png` (cut) | 0:50 |
| 11 | 6 How much practice does a new patient need? | Then it levels off, and starting from nothing overtakes it: 61.2% against 57.8% after 9.3 min | `web/setup.png` | 1:00 |
| 12 | 7 Can the sixth finger be a command of its own? | As a “move now” switch it works: told from rest 84% of the time, but from the hand only 65.6% | `web/switch-patients.png` | 0:50 |
| 13 | 7 Can the sixth finger be a command of its own? | Acting only when it is sure, the switch is right 89% of the time, on 76.5% of the decisions | `web/switch-sure.png` | 0:35 |
| 14 | 7 Can the sixth finger be a command of its own? | But imagining the hand switches it on too, 62.7% of the time: it is not yet a command apart from the hand | `web/switch-on.png` | 0:45 |
| 15 | 8 Does it work on another day, and live? | On another day the model needs a top-up: unchanged it falls to 44.9%, and 2.3 min of practice restores 59.7% | drawn on the slide | 0:45 |
| 16 | 8 Does it work on another day, and live? | Played as if live, it catches 64.9% of imagined movements but switches on by mistake 1.24 times a minute at rest | drawn on the slide | 0:45 |
| 17 | Demo Can we see it work? | A recording the model never learned from, played at real speed: when the patient imagines moving, the finger bends | `hand_poses.png` (cut) | 3:00 demo |
| 18 | 9 What is built, and what is not? | Built: the model, its server and this page. Not built: the live headset link and the robotic finger | `web/path.png` (cut) | 0:50 |
| 19 | 10 What did we add? | What is new is a fair test of what was already there, fixed in advance and open to check | drawn on the slide | 0:50 |
| 20 | 11 What is next? | Next: a study with a live headset, a real finger, and a switch that rarely fires at rest | `web/path.png` (cut), `hand_poses.png` (cut) | 0:40 |
| 21 |  | Thank you. Questions? | `hand_poses.png` (cut) | 0:15 |
| 22 | Backup  The leak, patient by patient | Patient by patient, the fair score is lower for all 22, by 5.4 to 46.2 points | `web/leak-slope.png` (cut) | backup |
| 23 | Backup  The same mistake elsewhere | The same mistake raised the score in every other dataset we tried, by 8.6 to 42.8 points | drawn on the slide | backup |
| 24 | Backup  Calibration, method by method | Methods that learned from other patients start higher; with enough practice the patient's own models catch up | drawn on the slide | backup |
| 25 | Backup  A benchmark in healthy people | Two grasps of one hand are hard to tell apart even in 15 healthy people: 48.7 to 53.9% a week later | drawn on the slide | backup |
| 26 | Backup  The replay as if live | As if live, the methods catch 60.0 to 66.1% of imagining, at 0.38 to 1.24 false starts a minute | drawn on the slide | backup |
| 27 | Backup  The demo patient | The demo patient was picked by a rule fixed in advance, as typical: 65.3% against the group's median 67.3% | drawn on the slide | backup |
| 28 | Backup  One trial | One trial as the patient saw it: rest, get ready, imagine; the model reads one piece of rest and one of imagining | `web/trial.png` | backup |
| 29 | Backup  Was the data sound? | Before any test we compared every pair of the 268 runs and set aside what was wrong in the shared recordings | drawn on the slide | backup |
