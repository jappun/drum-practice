# Drum Practice

A local desktop app for drum practice: it plays a beat and lights up the notes, then you play it back on an electronic kit and get graded on accuracy.

Built with Python + PySide6 (Qt). Reads the kit over USB-MIDI. Developed using Yamaha DTX400K drumkit; any kit that sends General MIDI drum notes should work.

See [docs/PLAN_PHASES.md](docs/PLAN_PHASES.md) for the build plan.

TODO:
- [x] Phase 1: project setup + kit monitor
- [x] Phase 2: Hardcoded beat playsback with ui light up 
- [x] Phase 3: Core loop - play a beat back and get scored
- [ ] Phase 4: User-controlled practice settings
- [ ] Phase 5: Build enhanced beat library and picker
- [ ] Phase 6: Groove MIDI Dataset import
- [ ] Phase 7: Dynamic hits (ie ghost notes, accents)
- [ ] Phase 8: Users can add/edit beats
- [ ] Phase 9: Upload sheet music
- [ ] Phase 10: Setup wizard to learn any kit's MIDI outputs


## Setup

Requires Python 3.11+.

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
2. Pick a beat. **Listen** plays it on a loop, with the grid lighting up each note as it sounds.
3. **Start practice** runs count-in → the beat plays → count-in → your turn (silent, the grid keeps lighting) → your score. On the results grid, green is perfect (≤30 ms), amber is good (≤70 ms, notched on the early/late side), a red outline is a missed note and a red dot is an extra hit.

**Kit monitor** opens a window that shows the kit's connection status and lights up each pad as you hit it. It also logs the MIDI note number and velocity of every hit, plus other messages such as hi-hat pedal position.

## Beats

Beats live in `beats/` as JSON files, with one pattern string per drum and one character per 16th step:

```
"HH_CLOSED": "x-x- x-x- x-x- x-x-",
"SNARE":     "---- X--g ---- x---",
```

`x` normal, `X` accent, `g` ghost, `-` rest. Spaces and `|` are only for readability.

## Tests

```
pytest
```

## License

MIT. See [LICENSE](LICENSE).
