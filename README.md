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

The current build (Phase 1) is a kit monitor. It shows the connection status and lights up each pad as you hit it. It also logs the MIDI note number and velocity of every hit, plus other messages such as hi-hat pedal position.

## Tests

```
pytest
```

## License

MIT. See [LICENSE](LICENSE).
