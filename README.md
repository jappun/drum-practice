# drum practice

A local desktop app for drum practice: it plays a beat and lights up the notes, then you play it back on an electronic kit and get graded on accuracy.

Built with Python + PySide6 (Qt). Reads the kit over USB-MIDI. Developed against a Yamaha DTX kit; any kit that sends General MIDI drum notes should work.

See [docs/PLAN_PHASES.md](docs/PLAN_PHASES.md) for the build plan.

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

Pick a beat and press **Play**. It plays on a loop and the grid lights up each note as it sounds. **Kit monitor** opens a window that shows the kit's connection status and lights up each pad as you hit it. It also logs the MIDI note number and velocity of every hit, plus other messages such as hi-hat pedal position.

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
