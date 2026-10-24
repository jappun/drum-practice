# Drum Practice

A local desktop app for drum practice: it plays a beat, you play it back and get scored on accuracy.

Built with Python + PySide6 (Qt). Reads the kit over USB-MIDI. Developed using Yamaha DTX400K drumkit; any kit that sends General MIDI drum notes should work.

## My Build Process
See `docs/` for build notes made along the way. I started off by giving [BRAINSTORM.md](docs/BRAINSTORM.md) to Claude Code. I went back and forth on my specific vision until the agent was aware of all my specific requirements. Then, I let it build  [docs/PLAN_PHASES.md](docs/PLAN_PHASES.md) which I carefully read through and provided feedback on for edits or incorrect choices. I did this until the plan met my expectations.

Then I let Claude build a phase, and I manually approve its edits. I test the application between each phase before moving onto the next.

## TODO:
- [x] Phase 1: project setup + kit monitor
- [x] Phase 2: Hardcoded beat playsback with ui light up 
- [x] Phase 3: Core loop - play a beat back and get scored
- [ ] Phase 4: User-controlled practice settings
- [ ] Phase 5: Build enhanced beat library and picker
- [ ] Phase 6: Groove MIDI Dataset import
- [ ] Phase 7: Users can add/edit beats
- [ ] Phase 8: Upload sheet music
- [ ] Phase 9: Setup wizard to learn any kit's MIDI outputs
- [ ] Phase 10: Dynamic hits (ie ghost notes, accents)


## Setup

Requires Python 3.11+.
Until phase 9 is complete, the application will assume your kit outputs are in line with General MIDI mapping.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

Connect the kit over USB and switch it on, then:

```
python -m drum_practice
```

1. **Calibrate** (once): tap any pad on each click, and the app measures the delay between sound and hit so it can correct for it.
2. Pick a beat from the **Library** on the left. You can filter it by genre and level, or press **Surprise me** for a random beat that matches the filters. Each beat shows your best score. **«** collapses the library to give the grid more room, and **»** brings it back. **Listen** plays the beat on a loop, with the grid lighting up each note as it sounds.
3. **Start practice** runs count-in → the beat plays → count-in → your turn (silent, the grid keeps lighting) → your score. On the results grid, green is perfect (≤30 ms), amber is good (≤70 ms, notched on the early/late side), a red outline is a missed note and a red dot is an extra hit.

The settings row underneath sets the **tempo** (drag the slider or type a number), how many **bars** to practise (the pattern repeats to fill them), whether there's a **count-in**, and whether a **click** plays during your turn. **Metronome** just plays a click at the current tempo. Settings are remembered between launches.

**Kit monitor** opens a window that shows the kit's connection status and lights up each pad as you hit it. It also logs the MIDI note number and velocity of every hit, plus other messages such as hi-hat pedal position.

## Beats

The library's 384 beats come from the [Groove MIDI Dataset](https://magenta.tensorflow.org/datasets/groove) by Google LLC, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (Gillick et al., "Learning to Groove with Inverse Sequence Transformations", ICML 2019). Each beat is a 2-bar section of a real drummer's performance, snapped to a 16th-note grid. Swung and triplet-feel performances are left out, since the grid can't show them yet. See [beats/gmd/ATTRIBUTION.md](beats/gmd/ATTRIBUTION.md) for exactly what was changed.

To rebuild them from the dataset (the script downloads it, 3 MB, and checks its checksum):

```
python scripts/import_gmd.py
```

Beats live in `beats/` as JSON files, with one pattern string per drum and one character per 16th step:

```
"HH_CLOSED": "x-x- x-x- x-x- x-x-",
"SNARE":     "---- X--g ---- x---",
```

`x` normal, `X` accent, `g` ghost, `-` rest. Spaces and `|` are only for readability.

Each beat file also sets `name`, `genre`, `difficulty` (`beginner`, `intermediate` or `advanced`), `tempo` and `bars`. The file name is the beat's ID, and best scores are saved under it. You can rename a beat inside the file without losing its scores, but renaming the file itself starts its score history over.

## Dev mode (keyboard drums)

For development without the kit:

```
python -m drum_practice --dev
```

The laptop keyboard plays the drums, and the grid shows each drum's key next to its name:

| Key | Drum | Key | Drum |
|---|---|---|---|
| Space | Kick | G | Tom 1 |
| F | Snare | H | Tom 2 |
| J | Hi-hat closed | B | Floor tom |
| U | Hi-hat open | I | Crash |
| C | Hi-hat pedal | O | Ride |

How it differs from the regular app:
- Dev mode has its own calibration, saved separately in `dev_settings.json`. Calibrate once by tapping a key.
- Keyboard timing is less precise than the kit's, and some laptop keyboards can't register three keys pressed at once.
- Treat dev-mode scores as rough. Final testing should be on the kit.

Without `--dev`, the keyboard does nothing and the app is unchanged.

## Tests

```
pytest
```

## License

MIT. See [LICENSE](LICENSE).
