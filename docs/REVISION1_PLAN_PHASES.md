# Drum Practice — Revision 1 Plan

**This is the source of truth for the build from here on.** It replaces [PLAN_PHASES.md](PLAN_PHASES.md), which is kept for history. Revision notes: [REVISION.md](REVISION.md).

## Context
Testing after Phase 7 changed the direction:
- **Beats are user-made, not from a dataset.** The Groove MIDI import simplified real drumming too much. The library becomes your own beats, plus a few starter examples.
- **Rhythm isn't a 16th grid.** Beats need triplets, 32nds, dotted rhythms and rests. **Sheet-music notation** becomes the main view (like [rock-beats.png](rock-beats.png)), and the step grid stays as an optional "grid view".
- **New ways to get music in:**
  - **a photo of a beat** (JPG/PNG), e.g. one groove from a drum book, read by an AI vision model;
  - **a full song** as MusicXML.
- **Two searchable libraries,** Beats and Songs, replace the genre and level filters. **Surprise me** stays and picks from whichever library you're in.
- **Beats are short; anything long is a song.** A beat is at most `MAX_BEAT_BARS` = 4 bars. Longer music, from any source, is a song and lives in the Songs library.
- **Long music scrolls into view,** and there's a **Drum Hero** game mode: Guitar Hero for drums, built to teach.
- **Accent colour is purple** `#8742f5` instead of orange.

Decisions from Q&A:

| Topic | Decision |
|---|---|
| Photo reading | AI vision through a **model-agnostic provider interface**: Claude, GPT and Gemini, each with your own API key set in the app's Settings and stored in the macOS Keychain. An evaluation script compares the providers on your own photos. Without a key the photo is shown beside the editor for entering notes by hand. A small **hosted service** (you hold the keys; users pay for the app) can replace user keys later behind the same interface. |
| Drum Hero layout | **Horizontal lanes**, one per drum. Notes slide in from the right to a hit line on the left. |
| Drum Hero vs practice | **Separate game mode.** Practice (count-in → demo → your turn → results) stays the teaching tool. Hero is played live with instant feedback, streaks, a multiplier and stars. |
| Starter content | **3–5 small hand-made example beats** (and later one short example song). You can delete them. |

**The phase gate rule is unchanged:** each phase ships one distinct, user-visible capability. It's done only when automated tests pass and you verify it by hand on the kit. Then it's committed; nothing is pushed unless you ask.

---

## What happens to each phase of PLAN_PHASES.md

| Old phase | Status | In this plan |
|---|---|---|
| 1 — Stack + live hit monitor | ✅ Completed, **kept** | Unchanged |
| 2 — Play a beat, see it | ✅ Completed, **kept** | Its step grid becomes the optional grid view (Phase 9) |
| 3 — Graded playback (core loop) | ✅ Completed, **kept** | Grading, calibration and the pedal rule are already time-based, so they carry over |
| 4 — Practice settings + metronome | ✅ Completed, **kept** | Unchanged; Bars is revisited for songs (Phase 12) |
| 5 — Beat library + picker | ✅ Completed, **partly kept** | Library panel, best scores, **Surprise me** and the collapsible sidebar stay. Genre/level filters are **removed** in favour of search (Phase 8). Surprise me gains songs in Phase 12 |
| 6 — Groove MIDI Dataset import | ✅ Completed, **removed** | Code, beats, script and attribution are deleted in Phase 8 |
| 7 — Beat editor | ✅ Completed, **kept and reworked** | Grid editing stays; it gains other subdivisions (Phase 9) and a live notation preview (Phase 10) |
| 8 — Song import (MIDI + MusicXML) | ⏳ Not started, **replaced** | Becomes **Phase 12 — Songs from MusicXML** (MusicXML only, for now) |
| 9 — Kit setup wizard | ⏳ Not started, **kept unchanged** | Becomes **Phase 14** (content unchanged) |
| 10 — Dynamics | ⏳ Not started, **kept unchanged** | Becomes **Phase 15** (content unchanged) |
| 11 — Flexible grid | ⏳ Not started, **folded in** | Its core (triplets, 32nds, finer grid) becomes **Phase 9**. Re-importing Groove MIDI is dropped with the dataset, and the swing setting is deferred (see Future) |

---

## Architecture changes
```
drum_practice/
  rhythm.py       # NEW (Ph 9): exact note timing as fractions of a beat, time signatures, tuplets
  model.py        # Beat v2: notes with exact onsets and durations; loads old v1 pattern-string beats
  notation/       # NEW (Ph 10): drum-staff layout (pure, testable) + Qt renderer using the Bravura music font
  ai/             # NEW (Ph 11): provider-agnostic AI layer
    providers.py  #   Claude / OpenAI / Gemini clients behind one interface (later: hosted service)
    transcribe.py #   photo → Beat: prompt, JSON schema, validation
    keys.py       #   API keys in the macOS Keychain (via `keyring`)
  songs/          # NEW (Ph 12): MusicXML import, song model with sections
  hero/           # NEW (Ph 13): live game scoring (streaks, multiplier, stars)
  ui/             # + notation view, view toggle, settings dialog, photo import, songs library, hero highway
beats/examples/   # starter beats (replaces beats/gmd/)
assets/fonts/     # Bravura (SIL Open Font License) for notation glyphs
```
Core logic (rhythm, layout, transcription parsing, MusicXML, hero scoring) stays free of Qt, hardware and network, so it's testable headless. AI provider calls are tested against recorded responses and never hit the network in tests.

---

## Phase 8 — Fresh start: purple, your library, search
**Purpose:** the app becomes your own library, with the new look.
- **Accent colour:** `#8742f5` everywhere orange was used (buttons, notes, playhead, toggles, links). Derive the lit/hover shade from it.
- **Remove the Groove MIDI Dataset:** `gmd.py`, `scripts/import_gmd.py`, `beats/gmd/`, its tests, the About credit and README sections, and `.cache/`. Best scores for removed beats are dropped.
- **Starter beats:** 3–5 small hand-made examples in `beats/examples/`, editable as duplicates. Deleting one hides it, and there's a "restore examples" option.
- **Library:** the genre and level filters are replaced by a **search box** that filters by name as you type. **Surprise me** stays: it picks a random beat from what the search shows, avoiding the current one. The list keeps best scores, "yours" tags, New beat and the collapsible sidebar. When the library is empty it shows "Make or import your first beat".
- **Beat length cap:** `MAX_BEAT_BARS = 4` is defined once and used by the editor (as today) and by every import from Phase 11 on.
- **Automated:** search matching (case-insensitive, partial, natural order); Surprise me respects the search and avoids the current beat; hiding/restoring examples; no GMD code or data left; theme has no orange.
- **Human:** the app looks right in purple; search finds beats as you type; Surprise me picks among the matches; examples can be practised, duplicated and hidden.

## Phase 9 — Rhythm beyond 16ths (new beat model + grid view)
**Purpose:** beats can contain triplets, 32nds and dotted rhythms, and play and grade correctly.
- **Timing:** each note has an exact onset as a fraction of a beat from the start (e.g. 1/3 for a triplet, 3/4 for the "a"), plus a notated duration. Beats have a **time signature** (any n/d, e.g. 3/4, 6/8, 7/8), not just 4/4.
- **JSON format v2:** a readable list of notes, e.g. `{"at": "1+2/3", "drum": "SNARE", "v": "x"}`. **Old v1 pattern-string beats** (your saved beats) load and convert automatically.
- **Playback, practice and grading** schedule from exact onsets. Grading is already time-based, so its windows are unchanged.
- **Grid view:** a per-beat subdivision of 16ths, 8th-note triplets, 16th triplets or 32nds. Mixed rhythms use the finest shared grid, grouped by beat. Columns are drawn proportionally so the timing stays visually true.
- **Editor:** choose the grid subdivision and time signature; clicking and dragging work at any subdivision.
- **Automated:**
  - onset arithmetic and tuplets;
  - v1→v2 migration (every existing user beat converts losslessly);
  - JSON v2 round trip;
  - scheduling to ±1 ms for triplets and 32nds;
  - grading on non-16th beats;
  - finest-grid selection.
- **Human:** build a shuffle (triplet) beat and a 32nd-note fill in the editor. They sound right, light up on time and grade fairly on the kit.

## Phase 10 — Notation view
**Purpose:** beats look like real drum sheet music, with the grid as an option.
- **Rendering:** a drum staff drawn in Qt with the **Bravura** SMuFL font (SIL OFL, free to bundle), using the standard drum key from drum books:
  - hi-hat ✕ above the staff, open hi-hat ✕ with "o", pedal ✕ below;
  - snare in the 3rd space, kick in the bottom space;
  - toms on their lines and spaces;
  - crash ✕ on a ledger line, ride ✕ on the top line.
- **Engraving:**
  - two voices, hands with stems up and feet with stems down;
  - beams grouped by beat; flags, dots, rests and tuplet brackets/numbers;
  - time signature, bar lines and repeat signs for loops.
- **Layout is pure and tested separately from drawing:** notes in → glyph positions out.
- **Playback highlighting:** the sounding notes light up and a playhead moves across.
- **Results:** perfect, good (early/late), missed and extra marks drawn on noteheads.
- **View toggle:** **Notation / Grid**, remembered. Notation is the default.
- **Editor:** a live notation preview above the grid while editing. Editing stays in the grid, so what you click is exactly what you get.
- **Automated:**
  - layout tests: staff positions per drum, stem directions, beaming groups, rests filling bars, tuplet grouping, accidental-free percussion clef;
  - a snapshot test of a few reference beats.
- **Human:** the example beats and a couple of grooves from your book (entered by hand) look like the book. Highlighting and results read clearly.

## Phase 11 — Beat from a photo (AI, model-agnostic)
**Purpose:** photograph a groove in a book and practise it a minute later.
- **Settings dialog** (new "Settings" button):
  - choose an AI provider: **Claude**, **OpenAI (GPT)** or **Google Gemini**;
  - paste an API key per provider, stored in the **macOS Keychain** (`keyring`), never in plain files;
  - a "Test key" button.
- **Import flow:**
  1. **Import photo…** accepts JPG, JPEG and PNG.
  2. Crop to the bar(s) you want.
  3. Choose the provider.
  4. The app sends **only the cropped image** with a prompt describing the drum key and a strict JSON schema of Phase 9 notes, and the reply is validated.
  5. The result opens **in the editor with the photo shown alongside**, to check and fix before saving.
     - **Several labelled grooves in one photo** (e.g. A–L on a book page): the reader returns each separately, and the app offers to save each as its own beat. It doesn't join them into one long piece.
     - **Longer than `MAX_BEAT_BARS`:** "This looks like a song (N bars). Songs arrive in a later update." You can keep the first 4 bars as a beat, or cancel. From Phase 12 this becomes "save it to the Songs library instead".
  6. Errors are explained (no key, offline, unreadable image, invalid reply), and the photo stays usable for manual entry.
- **No key, or the AI is turned off:** the photo is still shown beside the editor for entering notes by hand.
- **Provider interface:** one `Transcriber` interface (image + instructions → Beat), so providers are interchangeable and a **hosted service** can plug in later without UI changes. Prompts and schemas are versioned in one place.
- **Evaluation:** `scripts/eval_transcribers.py` runs a folder of your photos with hand-checked answers through each configured provider. It reports note-level accuracy (right drum at the right time, missed, invented), cost and speed, so you can choose a default from evidence.
- **Privacy:** a one-line notice that the cropped image is sent to the chosen provider. Nothing is sent without a key and a click.
- **Automated:**
  - reply parsing and validation against recorded provider responses (good, partial, malformed, wrong drums), with no network;
  - the schema matches the Phase 9 model;
  - multiple grooves in one reply are split into separate beats;
  - the beat length cap (over 4 bars → "looks like a song", with keep-first-4 or cancel);
  - keychain access is mocked;
  - accuracy scoring in the evaluation script.
- **Human:** photograph 5–10 grooves from your book, import them with each provider you have a key for, fix them in the editor and practise them. Use the eval script to pick a default.

## Phase 12 — Songs from MusicXML
**Purpose:** practise against a whole song.
- **Import** `.musicxml`, `.xml` and compressed `.mxl` (what MuseScore exports):
  - find the drum (percussion) part;
  - map its instruments and noteheads to the 10 drum classes, with MuseScore's default drum set built in and a "which drum is this?" prompt for anything unknown;
  - handle tempo marks, time-signature changes, tuplets and dotted rhythms;
  - expand repeats and voltas into play order;
  - read rehearsal marks as **sections** (verse, chorus…).
- **Songs library:** a second library tab, **Songs**, searchable by name like Beats, with best scores per song and per section. Import, rename and delete. **Surprise me** in the Songs tab picks a random song.
- **Beat or song, by length:** anything longer than `MAX_BEAT_BARS`, whether from a photo, MusicXML or the editor, is a **song**. The app tells you "This looks like a song, so it's been added to your Songs library" and saves it there. A MusicXML file of 4 bars or fewer is offered as a **beat** instead (you can choose to keep it as a song).
- **Long music scrolls into view:** the notation and grid views follow the playhead with a smooth, continuous scroll, so upcoming notes slide in from the right. No page flipping. (Shared with Phase 13.)
- **Practice a song:** the whole song or a chosen section or bar range, with loop and tempo % for slow practice. The existing practice loop runs on the selection. Results are given per section.
- **Example:** one short public-domain or self-written example song in MusicXML.
- **Automated:**
  - MusicXML fixtures (MuseScore export, repeats/voltas, tempo and time-signature changes, tuplets, compressed `.mxl`) → expected notes and sections;
  - drum mapping;
  - unknown-instrument handling;
  - beat-vs-song routing by length (from photo and MusicXML, both directions);
  - Surprise me picks songs in the Songs tab and beats in the Beats tab;
  - scroll-position maths;
  - per-section grading.
- **Human:** export a song's drum part from MuseScore, import it, scroll through it while it plays, practise a section at 70% tempo, and review the per-section results.

## Phase 13 — Drum Hero mode
**Purpose:** a game that makes practice fun, Guitar Hero for drums, and still teaches.
- **Highway:**
  - horizontal lanes, one per drum used, labelled (and keyed in `--dev` mode);
  - notes slide right → left to a **hit line**;
  - a lane flashes when you hit it.
  - Uses the Phase 12 scroll engine and works for beats (looped n times) and songs.
- **Live feedback:**
  - each note is judged the moment it passes, with **Perfect / Good / Miss** pop-ups using Phase 3's windows and pedal rule, scored incrementally;
  - extra hits show as a flash on their lane.
- **Game scoring:**
  - points per note;
  - a **streak** counter;
  - a **multiplier** that grows with the streak (×2 at 10, ×3 at 20, ×4 at 30) and resets on a miss;
  - a **star rating** of 1–5 at the end, from accuracy;
  - a results screen with the longest streak and accuracy;
  - **high scores** per beat or song, separate from practice best scores.
- **Teaching options:**
  - speed (50–100% tempo);
  - "lead-in" bars;
  - the drum sounds can be audible (play along) or silent (you're the drummer);
  - pause and restart.
- **Mode switch:** **Practice | Drum Hero**. Calibration applies to both.
- **Automated:**
  - incremental live grading matches the end-of-run grading on the same hits;
  - streak/multiplier/star maths;
  - note-to-screen position maths at different speeds;
  - pause/resume timing.
- **Human:** play a beat and a song section in Hero mode on the kit. The notes reach the hit line exactly when they should sound, judgements feel fair and instant, and it's fun.

## Phase 14 — Kit setup wizard (any kit)
*(Was Phase 9 in PLAN_PHASES.md; unchanged.)*

**Purpose:** make the app work with any e-kit, not just the developer's DTX.
- Setup screen that walks through each of the 10 drums ("hit your snare now…"), records the note numbers each pad sends, and saves a per-user kit profile. The General MIDI map stays the default for anything not set up.
- Lets the user pick the MIDI input port, and re-run or edit the mapping any time.
- **Automated:** profile save/load; profile overrides GM; unassigned drums fall back to GM.
- **Human:** set a pad on the module to a non-GM note, run the wizard → that pad is mapped correctly without code changes.

## Phase 15 — Dynamics
*(Was Phase 10 in PLAN_PHASES.md; unchanged.)*

**Purpose:** accents and ghost notes matter.
- Grid shows velocity (cell shading / accent marks); playback uses velocity.
- Optional "score dynamics" setting: per-velocity calibration (your soft/hard range), accent/ghost matching added to the grade.
- Hi-hat pedal hits are left out of dynamics scoring: the DTX sends every chick at velocity 100 (see `docs/KIT_NOTES.md`).
- **Automated:** velocity bucketing + dynamics scoring tests.
- **Human:** accents audibly/visibly differ; playing them flat lowers the dynamics score.

---

## Future (not scheduled yet)
Ideas to keep in mind so today's design doesn't block them:
- **Hosted AI service and a paid app:**
  - a small server that holds the provider keys, so users don't need their own;
  - accounts, usage limits and billing;
  - the Phase 11 `Transcriber` interface gets a "hosted" provider, with no UI rework.
- **More AI features,** e.g. a **personal learning path:** suggest the next beat and tempo from your scores and common mistakes (rushing, missed kicks…). They would reuse the `ai/` provider layer and the stored practice history, so keep score history (not just best scores) from Phase 12 on.
- **Swing setting** (from old Phase 11): shuffle a straight beat without rewriting it as triplets.
- **MIDI file import** for songs (dropped from old Phase 8; MusicXML is enough for now).
- **Before charging for the app:**
  - review the licence (it's currently MIT, which lets anyone resell it) and the bundled assets (Bravura is OFL, which is fine);
  - consider that a hosted service would store user-uploaded transcriptions of copyrighted books, which raises content-rights questions.

---

## Verification (each phase)
1. Inside the venv, `pip install -r requirements.txt` works from clean and `pytest` passes: core logic is headless, and AI calls use recorded responses.
2. `python -m drum_practice` launches. I check what I can without the kit (UI loads, audio renders, offline grading, screenshots), using `--dev` keyboard mode where useful.
3. You run the phase's human checklist on the DTX kit.
4. On sign-off: commit the phase (smaller commits within a phase are fine). Nothing is pushed unless you ask.
