# Drum Practice App

A local desktop app for drum practice: it plays a beat, you play it back and get scored on accuracy.

Built with Python + PySide6 (Qt). Reads the kit over USB-MIDI. Developed using Yamaha DTX400K drumkit; any kit that sends General MIDI drum notes should work.

To try the app, skip to [Setup](#setup).

## My Build Process
See `docs/` for build notes made along the way. I started off by giving [BRAINSTORM.md](docs/BRAINSTORM.md) to Claude Code. I went back and forth on my vision until the agent was aware of all my specific requirements. Then, I let it build  [docs/PLAN_PHASES.md](docs/PLAN_PHASES.md) which I carefully read through and provided feedback on for edits or incorrect choices. I did this until the plan met my expectations.

Then I let Claude build a phase, and I manually approve its edits. I test the application between each phase before moving onto the next.

I stopped at Phase 7 in [docs/PLAN_PHASES.md](docs/PLAN_PHASES.md), at which point I did a second brainstorm in [REVISION.md](docs/REVISON.md). I went through the same process and landed at [docs/REVISION1_PLAN_PHASES.md](docs/REVISON1_PLAN_PHASES.md). I'm currently building this out. 

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
- [x] Phase 9: Rhythm beyond 16ths (triplets, 32nds, any time signature)
- [x] Phase 10: Notation view (sheet music, with a grid view option)
- [x] Phase 11: Beat from a photo (AI, works with Claude, GPT or Gemini)
- [ ] Phase 12: Songs from MusicXML
- [ ] Phase 13: Drum Hero mode
- [ ] Phase 14: Setup wizard to learn any kit's MIDI outputs
- [ ] Phase 15: Dynamic hits (ie ghost notes, accents)
- [ ] Phase 16: Package and publish

Scrapped/replaced from the original plan:
- Upload sheet music (MIDI files) → songs from MusicXML (Phase 12)
- Flexible grid → triplets and 32nds folded into Phase 9


## Setup

Requires Python 3.11+.
Until phase 14 is complete, the application will assume your kit outputs are in line with General MIDI mapping.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run
If you don't have a kit, [use your keyboard in dev mode](#run-in-dev-mode). Otherwise connect your kit over USB and switch it on, then:

```
python -m drum_practice
```

**Important Note:** Phase 14 is not complete. Your kit outputs needs to be set to General Midi Mapping.

## Practice Basics

1. **Settings → Calibrate** (once): tap any pad on each click, and the app measures the delay between sound and hit so it can correct for it.
2. Pick a beat from the **Library** on the left. Switch between Grid (⌘2) and Notation (⌘1) depening on your preference. You can **Listen** to your selected beat or get started right away with **Start practice**.
3. Basic Rock is a good example beat to get comfortable using the app with and understand results. Play around with the metronome settings (count in, tempo, etc.) to find what you prefer and understand. Best scores are saved. 
4. **Add your own beats**: You can fork off of the example beats (Duplicate and Edit button), or create a whole new beat. You can also upload a beat from a photo (PNG or JPG) and transcribe it using the grid. 
    - You can also get AI transcribe it for you. You have your pick of any Google, Open AI or Anthropic model, but you'll need your own API key. The AI will highlight areas it was unsure about and needs your review (you should probably always review its work anyway). If you want to use this option, I recommend [evaluating different providers](#comparing-ai-providers).

## Run in Dev Mode

To run dev board and use your keyboard instead of a kit:
```
python -m drum_practice --dev
```

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

Dev mode also prints the AI's raw reply to the terminal after each photo is read.

Without `--dev`, the keyboard does nothing

## Comparing AI providers

To see which provider reads your book best, put cropped photos and their hand-checked answers in a folder, then run:

```
python scripts/eval_transcribers.py path/to/folder
```

Each photo (`groove-a.png`) needs an answer next to it (`groove-a.json`): a beat file saved from the app, or `{"beats": [...]}` for a photo with several grooves. The script runs every provider that has a key, then reports note accuracy (missed and invented notes), speed, tokens and cost. Cost is shown only where prices are known. It sends the photos and costs money, so you'll be asked for confirmation first.

## Tests

```
pytest
```

## Credits

Music notation is drawn with the [Bravura](https://github.com/steinbergmedia/bravura) font, © Steinberg Media Technologies, licensed under the SIL Open Font License 1.1 (see [assets/fonts/Bravura-OFL.txt](assets/fonts/Bravura-OFL.txt)).

## License

MIT. See [LICENSE](LICENSE).