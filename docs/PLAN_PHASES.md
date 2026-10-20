# Drum Practice App — Phased Build Plan

## Context
`drum-practice` is a new local desktop app (repo initialised; only README, MIT LICENSE, .gitignore, BRAINSTORM.md exist). It plays a drum beat while lighting up notes on a grid, then the user plays it back on their Yamaha DTX kit and gets an accuracy grade. Requirements come from [BRAINSTORM.md](BRAINSTORM.md) plus Q&A:

- **Stack:** Python 3.11 + PySide6 (Qt) desktop app. `mido` + `python-rtmidi` for MIDI in, `sounddevice` + `numpy` for low-latency audio. Not browser-based.
- **Kit (verified connected):** macOS sees USB device "DTX drums" (YAMAHA, vendor 0x0499) and a CoreMIDI source named **"DTX drums"**. Pieces: kick, snare, hi-hat (+ pedal), 3 toms, crash, ride → maps to 10 classes: KICK, SNARE, HH_CLOSED, HH_OPEN, HH_PEDAL, TOM_HIGH, TOM_MID, TOM_LOW, CRASH, RIDE. (Groove MIDI uses 9 classes, merging the pedal into closed hi-hat; we keep it separate.)
- **Display:** grid/step view (rows = drums, columns = 16th steps), cells light up as played.
- **Grading:** timing + correct drum. Dynamics (velocity) is a later phase, gated on Phase 1 confirming the kit sends varied velocity.
- **Audio cues:** count-in ON by default; metronome toggleable; standalone metronome-only mode; settings must be minimal and obvious.
- **Options:** user picks n bars, difficulty (beginner/intermediate/advanced), genre.
- **Beats:** <5 hand-authored beats for early phases; later the Groove MIDI Dataset (CC BY 4.0, attribution required — accepted).
- **Beat selection:** library browser with genre/difficulty filters, a "Surprise me" random pick within filters, and best score shown per beat.
- **Advanced:** grid beat editor, then sheet-music/song import, as final phases.

**Phase gate rule:** each phase ships one distinct, user-visible capability; it's done only when automated tests pass AND the user verifies it by hand on the kit. Then commit (incremental, descriptive messages; push only when the user says).

## First step (before Phase 1)
Save this plan into the project as `docs/PLAN_PHASES.md` (new `docs/` folder), keeping the user's original notes untouched in `docs/BRAINSTORM.md`. Update the docs copy if the plan changes later.

## Architecture (set up in Phase 1, grows per phase)
```
.venv/            # project virtualenv (git-ignored)
requirements.txt  # pinned deps: `pip install -r requirements.txt`
drum_practice/
  kit.py          # DrumClass enum + DTX note-number → class map (from Phase 1 discovery)
  midi_in.py      # opens "DTX drums" port, timestamps hits with time.perf_counter()
  model.py        # Beat dataclass: name, genre, difficulty, tempo, time_sig, steps_per_beat, bars, notes[(step, drum, velocity)]
  audio.py        # sounddevice callback mixer: sample-accurate scheduling of drum + click sounds
  sounds.py       # numpy-synthesised kit/click sounds (no licensing issues); CC0 samples optional later
  grading.py      # pure functions: expected notes + recorded hits + latency offset → per-note results + score
  library.py      # load/save beats (JSON in beats/), filters, best scores (scores.json in user data dir)
  ui/             # PySide6 widgets: main window, grid view, settings bar, library browser, results
tests/            # pytest, core logic only (no Qt/hardware needed)
beats/            # beat JSON files
```
Core logic (model, grading, scheduling, import) stays free of Qt and hardware so it's testable headless.

---

## Phase 1 — Stack + live hit monitor
**Purpose:** prove the stack works with the kit, and learn exactly what the DTX sends.
- Project setup: create a venv (`python3 -m venv .venv`) and a pinned `requirements.txt` (PySide6, mido, python-rtmidi, sounddevice, numpy, pytest) so anyone can `pip install -r requirements.txt`; update `.gitignore` for Python (`.venv/`, `__pycache__/`, `.pytest_cache/`, etc.); README gets setup + run instructions (`source .venv/bin/activate`, `pip install -r requirements.txt`, `python -m drum_practice`). Package lives at repo root (`drum_practice/`), so it runs without an install step.
- PySide6 window listing the MIDI port status and a live log of hits: note number, mapped drum name, velocity, timestamp. Hit pads light up on a simple kit diagram/row of labels.
- Discover and record the DTX note map in `kit.py` (incl. hi-hat open/closed/pedal and any rim/edge zones).
- **Automated:** unit test for note→drum mapping; test that unknown notes are reported, not crashed on.
- **Human:** hit each of the 10 inputs → correct label every time; hit soft vs hard → velocity changes (decides whether Phase 7 is feasible); unplug/replug → status updates.
- **Hi-hat behaviour checks (inform Phase 3's pedal rule):** does closing the pedal send a chick note (expected 44)? Does moving the pedal send position messages (expected CC #4)? Is there a separate foot-splash note? Where is the module's open/half-open/closed threshold for stick hits?

## Phase 2 — One beat: play it and see it
**Purpose:** the app plays a hard-coded beat out loud with the grid lighting in sync.
- `Beat` model + 2–3 hand-authored beats (e.g. basic rock 8ths, rock with fill-ish tom hit, simple funk) as JSON. At least one mixes open and closed hi-hats (e.g. open on the "&" of 4, closing on 1) to exercise the pedal rule in Phase 3.
- Audio engine with sample-accurate scheduling in the sounddevice callback; synthesised sounds.
- Grid view: drum rows, 16th columns, moving playhead; cells flash when their note sounds.
- Fixed tempo (e.g. 90 BPM), Play/Stop button.
- **Automated:** offline-render a beat and assert onsets land at the expected sample positions (±1 ms); JSON load/save round-trip.
- **Human:** beat sounds steady and correct; lights match what you hear.

## Phase 3 — Play it back and get graded (core loop)
**Purpose:** the full core loop on one beat: listen → play silently along → score.
- One "Start" press runs the default sequence: **count-in → demo (beat plays with lights) → count-in → your playback** (silent, playhead + lights still run, MIDI hits recorded) → results. Seamless, in tempo, with the on-screen status showing which stage you're in.
- Latency calibration: tap along to 8 clicks; median offset is stored and applied to hits.
- Grading: each expected note matches the nearest unused hit of the same drum within a window (Perfect ≤30 ms, Good ≤70 ms, else Miss); unmatched hits = extras (penalty). Score % plus counts.
- Hi-hat pedal second pass: after normal matching, each leftover pedal hit is checked (window = 40 ms, a named constant):
  - **A:** within 40 ms of a recorded **closed** hi-hat stick hit → ignore (hand and foot closing together).
  - **B:** else, if the most recent hi-hat stick hit before it was **open**, landed more than 40 ms earlier, and hasn't already used its one close → ignore (the normal close after an open hat). Each open hit excuses at most one close.
  - Otherwise it's an extra. (A chick right after an open hit is a choke, and it counts as an extra.)
- Results view: grid marks each note hit/early/late/missed, plus extra hits.
- **Automated:** grading tests on synthetic hit lists (perfect, uniformly shifted, missing notes, wrong drum, extras, double hits); pedal-rule tests (chick with a closed hit → ignored; chick closing an open hat → ignored; second chick after one open hit → extra; chick within 40 ms after an open hit → extra; lone chick → extra; written pedal note → graded normally); calibration math test; sequence timeline test (count-in, demo, count-in, playback boundaries land on the right bars).
- **Human:** play it well → high score; deliberately skip/miss/add notes → score drops and results show exactly where; play the open/closed hi-hat beat cleanly → pedal closes don't lower the score.

## Phase 4 — Practice settings + metronome mode
**Purpose:** the user controls how they practise, from one simple settings bar.
- Controls: tempo (BPM slider), bars n (loop/extend the beat to n bars), count-in (on by default; applies before both demo and playback), metronome during your turn (toggle), metronome-only mode (Start/Stop click with tempo, no beat).
- Settings persist between launches.
- **Automated:** n-bar expansion tests (pattern repeat/truncate, step indices); tempo change → scheduling times scale; settings persistence.
- **Human:** each setting is understandable at a glance and does what it says; metronome-only mode works on its own.

## Phase 5 — Beat library + picker
**Purpose:** choose what to practise.
- Grow the hand-authored set to ~8–10 beats across 2–3 genres and all 3 difficulties.
- Library browser: list with genre + difficulty filters, "Surprise me" random pick within filters, best score per beat (stored locally).
- **Automated:** filter logic, random pick respects filters, best-score update rules.
- **Human:** filter, pick, practise, see best score update after a better run.

## Phase 6 — Groove MIDI Dataset import
**Purpose:** a large real library from a properly licensed source.
- Offline import script (`scripts/import_gmd.py`): download GMD, keep 4/4 "beat" (not fill) performances, map Roland notes → the 10 classes, quantise to the 16th grid (reject clips whose quantisation error is too high, e.g. swung/triplet feel, or support 12/8 later), slice into bar-aligned segments, compute difficulty from note density, syncopation, limb independence and tempo, tag genre from GMD metadata.
- Output beat JSON into the library; add CC BY 4.0 attribution in README and an About dialog.
- **Automated:** quantisation, note mapping, difficulty-score tests on small fixture MIDI files; importer is idempotent.
- **Human:** library now has many beats per genre; spot-check a few: they sound musical and difficulty labels feel right.

## Phase 7 — Dynamics (only if Phase 1 confirmed velocity)
**Purpose:** accents and ghost notes matter.
- Grid shows velocity (cell shading / accent marks); playback uses velocity.
- Optional "score dynamics" setting: per-velocity calibration (your soft/hard range), accent/ghost matching added to the grade.
- **Automated:** velocity bucketing + dynamics scoring tests.
- **Human:** accents audibly/visibly differ; playing them flat lowers the dynamics score.

## Phase 8 — Beat editor
**Purpose:** create and edit your own beats.
- Editable grid: click/drag to toggle notes, pick drum row, set bars/tempo/genre/difficulty/name; save to library; edit/duplicate existing beats.
- **Automated:** edit operations on the model; saved beats load identically.
- **Human:** build a beat from scratch, practise it, edit it, and it's still in the library after restart.

## Phase 9 — Song import (whole-song scoring)
**Purpose:** practise against a full song chart.
- Import a drum part from a MIDI file (GM drum map) and from MusicXML (what MuseScore exports, so regular sheet music can be encoded there first).
- Long-form view: grid scrolls horizontally; section-by-section results; option to practise a bar range.
- **Automated:** import fixtures (MIDI + MusicXML) → expected note lists; tempo/time-signature changes handled or rejected cleanly.
- **Human:** import a song exported from MuseScore, play it through, review per-section results.

## Phase 10 — Kit setup wizard (any kit)
**Purpose:** make the app work with any e-kit, not just the developer's DTX.
- Setup screen that walks through each of the 10 drums ("hit your snare now…"), records the note numbers each pad sends, and saves a per-user kit profile. The General MIDI map stays the default for anything not set up.
- Lets the user pick the MIDI input port, and re-run or edit the mapping any time.
- **Automated:** profile save/load; profile overrides GM; unassigned drums fall back to GM.
- **Human:** set a pad on the module to a non-GM note, run the wizard → that pad is mapped correctly without code changes.

---

## Verification (each phase)
1. Inside the venv, `pip install -r requirements.txt` works from clean and `pytest` passes (core logic, headless).
2. `python -m drum_practice` launches; I check what I can without the kit (UI loads, audio renders, offline grading tests).
3. You run the phase's human checklist on the DTX kit.
4. On sign-off: commit the phase (e.g. "Phase 2: beat playback with synced grid"), smaller commits within a phase are fine. Push only when asked.
