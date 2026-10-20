# Yamaha DTX DTX400K drums Notes

What Phase 1 found about the development kit. Later phases rely on these facts.

## Connection
- Shows up as the USB-MIDI port **"DTX drums"** (YAMAHA, USB vendor 0x0499). No driver is needed.
- The kit switches itself off when idle, and the port disappears until it's switched back on.

## Note map (module set to General MIDI numbers)
| Drum | Note |
|---|---|
| Kick | 36 |
| Snare | 38 |
| Hi-hat closed | 42 |
| Hi-hat pedal (chick) | 44 |
| Hi-hat open | 46 |
| Tom 1 (high) | 48 |
| Tom 2 (mid) | 47 |
| Tom 3 (floor) | 43 |
| Crash | 49 |
| Ride | 51 |

- Out of the box, the module sent **5** for the snare and **2** for Tom 1. Both were changed to the GM numbers above in the module's settings.
- There are no rim, edge or bell zones. Each pad sends one note.

## Velocity
- Velocity varies with how hard you hit, from about 10 to 127 on every pad. Soft hits that you mean to play can be as low as about 10.
- The hi-hat pedal chick always arrives at **velocity 100**, however hard you close it. Pedal dynamics can't be graded.

## Hi-hat pedal
- Pedal position arrives as control change #4: **0 = open, about 124–127 = closed**. Values in between only appear briefly while the pedal is moving. In practice the pedal acts like an open/closed switch, with no half-open state.
- Stick hits register as open (46) unless the pedal is fully closed. A partly pressed pedal counts as open.
- Every close sends exactly one chick note (44), fast or slow. It fires at the moment the pedal reaches closed (position about 98 → chick → 126/127). On a slow close, the chick lands when the pedal bottoms out, not when you start pressing.
- Opening the pedal sends only position messages, never a note.
- No foot-splash note was seen.

## Crosstalk
- Hitting Tom 1, and sometimes the snare, made Tom 2 fire softly (note 47, velocity 9–31).
- **Fix:** module crosstalk raised from the default 45 to **60** on Tom 1 and Tom 2, plus a physical adjustment of the toms. Stray hits now only happen when hitting right at the edge of a tom, which isn't a normal place to hit.
- The app doesn't filter vibration for now. Stray hits (9–15) overlap with real soft hits (10+), so a velocity floor would drop genuine notes. Revisit this if strays show up during grading.
