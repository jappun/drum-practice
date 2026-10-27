# Drum Practice

A local desktop app for drum practice: it plays a beat, you play it back and get scored on accuracy.

Built with Python + PySide6 (Qt). Reads the kit over USB-MIDI. Developed using Yamaha DTX400K drumkit; any kit that sends General MIDI drum notes should work.

## My Build Process
See `docs/` for build notes made along the way. I started off by giving [BRAINSTORM.md](docs/BRAINSTORM.md) to Claude Code. I went back and forth on my specific vision until the agent was aware of all my specific requirements. Then, I let it build  [docs/PLAN_PHASES.md](docs/PLAN_PHASES.md) which I carefully read through and provided feedback on for edits or incorrect choices. I did this until the plan met my expectations.

Then I let Claude build a phase, and I manually approve its edits. I test the application between each phase before moving onto the next.

## TODO:
Following [docs/REVISION1_PLAN_PHASES.md](docs/REVISION1_PLAN_PHASES.md). Struck-through items were scrapped or replaced in the revision.

- [x] Phase 1: Project setup + kit monitor
- [x] Phase 2: Hardcoded beat playback with UI light-up
- [x] Phase 3: Core loop - play a beat back and get scored
- [x] Phase 4: User-controlled practice settings
- [x] Phase 5: Beat library and picker (~~genre, level filters~~, search)
- [x] ~~Phase 6: Groove MIDI Dataset import~~ (removed dataset in revision)
- [x] Phase 7: Users can add/edit beats
- [x] Phase 8: Fresh start: purple theme, your own library, search
- [ ] Phase 9: Rhythm beyond 16ths (triplets, 32nds, any time signature)
- [ ] Phase 10: Notation view (sheet music, with a grid view option)
- [ ] Phase 11: Beat from a photo (AI, works with Claude, GPT or Gemini)
- [ ] Phase 12: Songs from MusicXML
- [ ] Phase 13: Drum Hero mode
- [ ] Phase 14: Setup wizard to learn any kit's MIDI outputs
- [ ] Phase 15: Dynamic hits (ie ghost notes, accents)

Scrapped/replaced from the original plan:
- Upload sheet music (MIDI files) → songs from MusicXML (Phase 12)
- Flexible grid → triplets and 32nds folded into Phase 9


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
2. Pick a beat from the **Library** on the left. Type in the search box to find beats by name, or press **Surprise me** for a random beat from your whole library. Each beat shows your best score. **«** collapses the library to give the grid more room, and **»** brings it back. **Listen** plays the beat on a loop, with the grid lighting up each note as it sounds.
3. **Start practice** runs count-in → the beat plays → count-in → your turn (silent, the grid keeps lighting) → your score. On the results grid, green is perfect (≤30 ms), purple is good (≤70 ms, notched on the early/late side), a red outline is a missed note and a red dot is an extra hit.

The settings row underneath sets the **tempo** (drag the slider or type a number), how many **bars** to practise (the pattern repeats to fill them), whether there's a **count-in**, and whether a **click** plays during your turn. **Metronome** just plays a click at the current tempo. Settings are remembered between launches.

**Your own beats:** press **New beat** in the library, or **Edit** on a beat, to open the editor.
- **Notes:** click a cell to add a note with the current brush (Ghost, Normal or Accent). Click it again to remove it, or click with a different brush to change its strength. Drag along a row to paint several at once.
- **Details:** set the name, genre, level and tempo.
- **Rhythm:** set the bars (1–4), the time signature (pick one or type e.g. `7/8`) and the **Grid**: 16ths, 8th triplets, 16th triplets or 32nds. Click a beat's number above the grid to divide just that beat differently, e.g. a triplet fill in beat 4. When a change leaves notes between columns, they move to the nearest one and the editor tells you how many moved.
- **Saving:** your beats are saved in your app-data folder and marked "yours" in the library.
- **Examples** are read-only. **Duplicate & edit** makes your own copy. **Hide example** removes one from your library, and **Show hidden examples** at the bottom of the library brings them back.
- **Scores:** changing a beat's notes or length resets its best score.

**Kit monitor** opens a window that shows the kit's connection status and lights up each pad as you hit it. It also logs the MIDI note number and velocity of every hit, plus other messages such as hi-hat pedal position.

## Beats

Your library is your own beats, made in the editor and saved in your app-data folder, plus a few hand-made starter examples in `beats/examples/`. A beat is at most 4 bars; longer music will be a song (see [docs/REVISION1_PLAN_PHASES.md](docs/REVISION1_PLAN_PHASES.md)).

Beats are JSON files with one note per line. Each note's `at` is its exact position in quarter notes from the start, so triplets and 32nds are exact:

```
"notes": [
    {"at": "0", "drum": "KICK", "v": "X"},
    {"at": "2/3", "drum": "HH_CLOSED", "v": "g"},
    {"at": "1+3/4", "drum": "SNARE", "v": "x"}
]
```

- **Positions:** `"0"` is the start, `"3/4"` is the "a" of beat 1, and `"1+2/3"` is the last triplet of beat 2.
- **`v`:** `x` normal, `X` accent, `g` ghost.

Each beat file also sets:
- `name`, `genre` and `difficulty` (`beginner`, `intermediate` or `advanced`);
- `tempo` in quarter notes per minute, `time_signature` (e.g. `"4/4"` or `"6/8"`) and `bars`;
- `grid`: how the editor divides each beat (`"16ths"`, `"8th triplets"`, `"16th triplets"` or `"32nds"`), plus optional per-beat `divisions`.

Older beat files that use pattern strings (`"SNARE": "---- x--- | ..."`) still load; they're saved in the new format the next time you edit them. The file name is the beat's ID, and best scores are saved under it. You can rename a beat inside the file without losing its scores, but renaming the file itself starts its score history over.

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
