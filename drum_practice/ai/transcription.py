"""Photo → beats: what we ask the model for, and turning its answer into Beats.

This part is the same for every provider: the instructions, the JSON schema
the reply must follow, and the checks that turn a reply into beats. Notes
come back as bar / beat / subdivision positions (easier for a vision model
to read off a page than fractions), and are converted to exact positions.
"""

import json
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from ..kit import DrumClass
from ..model import ACCENT, GHOST, MAX_BEAT_BARS, NORMAL, Beat, Note, default_grid
from ..rhythm import TimeSignature, subdivision_for

PROMPT_VERSION = "2026-10-29"  # bump when the instructions or schema change (eval results are per version)

DrumName = Literal[
    "KICK", "SNARE", "HH_CLOSED", "HH_OPEN", "HH_PEDAL", "TOM_HIGH", "TOM_MID", "TOM_LOW", "CRASH", "RIDE"
]
ALLOWED_DIVISIONS = (1, 2, 3, 4, 6, 8)
UnsureReason = Literal["timing", "drum", "dynamics", "unclear", "missing"]
REASON_TEXT = {
    "timing": "may be in the wrong place in the beat",
    "drum": "may be the wrong drum",
    "dynamics": "accent or ghost may be wrong",
    "unclear": "hard to read in the photo",
    "missing": "a note may be missing",
}
MAX_UNSURE_LINES = 5


class NoteReading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bar: int  # 1-based, within the groove
    beat: int  # 1-based, counted beats of the time signature (6/8 has 2)
    division: int  # how many equal parts this beat is split into for this note: 1, 2, 3, 4, 6 or 8
    index: int  # which part, 0-based (0 = on the beat)
    drum: DrumName
    accent: bool
    ghost: bool


class GrooveReading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str  # e.g. "A", or "" if unlabelled
    time_signature: str  # e.g. "4/4"
    bars: int
    tempo: int | None  # BPM if printed, else null
    notes: list[NoteReading]


class UnsureSpot(BaseModel):
    """One place the model couldn't read confidently. Structured, so the app
    writes the message (short and the same every time) rather than the model."""

    model_config = ConfigDict(extra="forbid")

    groove: str  # its label, or "" if unlabelled
    bar: int
    beat: int
    drum: DrumName | None  # null if it's about the whole beat
    reason: UnsureReason


class PhotoReading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grooves: list[GrooveReading]
    unsure: list[UnsureSpot]  # empty when everything was clear


def json_schema() -> dict:
    """The reply schema, strict: every field required, no extra fields."""
    return PhotoReading.model_json_schema()


INSTRUCTIONS = f"""You read drum notation from a photo (usually a page or a crop of a drum book) and
transcribe it exactly. Reply only with JSON matching the schema.

Drum key (standard drum-book notation, percussion clef):
- KICK: notehead in the bottom space, usually stems down.
- SNARE: notehead in the third space from the bottom.
- HH_CLOSED: x notehead just above the top line. HH_OPEN: same x with a small "o" above it.
- HH_PEDAL: x notehead below the bottom line, stems down (hi-hat played with the foot).
- RIDE: x notehead on the top line. CRASH: x notehead on a ledger line above the staff.
- TOM_HIGH: top space. TOM_MID: fourth line from the bottom. TOM_LOW (floor tom): second space from the bottom.

Positions: for each notehead give bar (1-based within its groove), beat (1-based; count beats the way the
time signature is felt: 4/4 has 4, 3/4 has 3, 6/8 and 12/8 count dotted quarters so 6/8 has 2), and the
position inside that beat as index out of division equal parts (division one of {list(ALLOWED_DIVISIONS)};
index 0 is on the beat). Examples in 4/4: the "&" is index 1 of 2; the "e" is 1 of 4 and the "a" 3 of 4;
the middle triplet note is 1 of 3; a 32nd note after the "&" is 5 of 8. Notes struck together each get
their own entry. Rests are not notes.

Marks: accent (">") sets accent true; a note in parentheses is a ghost note (ghost true).

Grooves: a page often shows several separate grooves, each labelled (A, B, C…) and each usually 1 or 2 bars
inside repeat signs. Return each one as its own groove with its label; don't join them. Give the time
signature written for each groove (the first one usually applies to all), the number of bars it has, and
the tempo in BPM if a single number is printed (null otherwise; use the lower end of a range).

Checking: a person will check your transcription against the photo, and "unsure" tells them where to look.
Before answering, go back over the photo beat by beat and compare it with what you wrote. Add one entry to
"unsure" for every spot where your reading could be wrong, transcribing your best reading anyway. Spots
that are easy to get wrong and usually deserve an entry:
- 32nd notes, triplets and other tuplets, dotted notes, and notes right after a rest (the position may be off);
- noteheads close to a line or space boundary, or between two drums (it may be the wrong drum);
- small, blurry, cropped or overlapping marks, accents and ghost-note parentheses;
- beats that look emptier than the beats around them (a note may be missing).
Each entry gives the groove label, bar, beat, the drum (null if it's about the whole beat) and the reason:
"timing" (where in the beat it falls), "drum" (which drum it is), "dynamics" (accent or ghost), "unclear"
(hard to read) or "missing" (a note may be missing). Flagging a spot that turns out right costs the person
a glance; missing a wrong one costs them a wrong groove, so when in doubt, flag it. Leave "unsure" empty
only if every note is clearly printed and simple to place.
"""


# --- turning a reply into beats ---


class ReplyError(ValueError):
    """The model's reply wasn't valid JSON, or didn't follow the rules."""


@dataclass
class GrooveResult:
    beat: Beat
    label: str
    bars_read: int  # how long the groove really is (may exceed MAX_BEAT_BARS)
    problems: list[str] = field(default_factory=list)  # notes we had to drop, and why

    @property
    def too_long(self) -> bool:
        return self.bars_read > MAX_BEAT_BARS


@dataclass
class PhotoResult:
    grooves: list[GrooveResult]
    unsure: list[UnsureSpot]


def parse_reply(text: str) -> PhotoReading:
    try:
        return PhotoReading.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as error:
        raise ReplyError(f"The reply wasn't in the expected format: {str(error)[:300]}") from error


def to_beats(reading: PhotoReading, name: str = "From photo", default_tempo: float = 90.0) -> PhotoResult:
    if not reading.grooves:
        raise ReplyError("No drum notation was found in the photo.")
    results = []
    for i, groove in enumerate(reading.grooves):
        label = groove.label.strip()
        title = f"{name} {label}" if label else (name if len(reading.grooves) == 1 else f"{name} {i + 1}")
        results.append(_groove_to_beat(groove, title, label, default_tempo))
    return PhotoResult(results, list(reading.unsure))


def describe_unsure(spots: list[UnsureSpot], several_grooves: bool) -> str:
    """One short line per drum and reason, e.g. "Snare, bar 1 beats 2 and 4: rhythm"."""
    groups: dict[tuple[str, str | None, str], list[tuple[int, int]]] = {}
    for spot in spots:
        groups.setdefault((spot.groove.strip(), spot.drum, spot.reason), []).append((spot.bar, spot.beat))
    lines = []
    for (groove, drum, reason), places in groups.items():
        who = DrumClass[drum].label if drum else "Notes"
        if several_grooves and groove:
            who = f"Groove {groove}: {who}"
        lines.append(f"• {who}, {_places(places)}: {REASON_TEXT[reason]}")
    if not lines:
        return ""
    more = len(lines) - MAX_UNSURE_LINES
    if more > 0:
        lines = lines[:MAX_UNSURE_LINES] + [f"…and {more} more"]
    return "AI import was unsure about:\n" + "\n".join(lines)


def unsure_cells(spots: list[UnsureSpot], beat: Beat) -> set[tuple[int, DrumClass | None]]:
    """Where to highlight a beat for checking: (beat index from the start, drum
    or None for the whole beat). Spots outside the beat are left out."""
    cells = set()
    for spot in spots:
        if 1 <= spot.bar <= beat.bars and 1 <= spot.beat <= beat.beats_per_bar:
            index = (spot.bar - 1) * beat.beats_per_bar + spot.beat - 1
            cells.add((index, DrumClass[spot.drum] if spot.drum else None))
    return cells


def _places(places: list[tuple[int, int]]) -> str:
    """[(1, 2), (1, 4), (2, 1)] → "bar 1 beats 2 and 4, bar 2 beat 1"."""
    by_bar: dict[int, list[int]] = {}
    for bar, beat in sorted(set(places)):
        by_bar.setdefault(bar, []).append(beat)
    parts = []
    for bar, beats in by_bar.items():
        numbers = [str(b) for b in beats]
        listed = numbers[0] if len(numbers) == 1 else ", ".join(numbers[:-1]) + " and " + numbers[-1]
        parts.append(f"bar {bar} beat{'s' if len(numbers) > 1 else ''} {listed}")
    return ", ".join(parts)


def _groove_to_beat(groove: GrooveReading, title: str, label: str, default_tempo: float) -> GrooveResult:
    try:
        ts = TimeSignature.parse(groove.time_signature)
    except ValueError:
        raise ReplyError(f"Groove {label or title}: unusable time signature {groove.time_signature!r}.")
    bars_read = max(1, groove.bars, max((n.bar for n in groove.notes), default=1))
    bars = min(bars_read, MAX_BEAT_BARS)
    beat = Beat(
        name=title,
        genre="From photo",
        difficulty="beginner",
        tempo=float(groove.tempo) if groove.tempo and 20 <= groove.tempo <= 300 else default_tempo,
        bars=bars,
        notes=[],
        time_signature=ts,
        grid=default_grid(ts),
    )
    problems: list[str] = []
    notes: dict[tuple[Fraction, DrumClass], Note] = {}
    divisions: dict[int, int] = {}
    for n in groove.notes:
        where = f"bar {n.bar}, beat {n.beat}"
        if not 1 <= n.bar <= bars_read or not 1 <= n.beat <= ts.beats_per_bar:
            problems.append(f"{where}: outside a {groove.bars}-bar {ts} groove")
            continue
        if n.division not in ALLOWED_DIVISIONS or not 0 <= n.index < n.division:
            problems.append(f"{where}: position {n.index} of {n.division} doesn't make sense")
            continue
        if n.bar > bars:
            continue  # past the beat-length cap; reported through too_long instead
        beat_index = (n.bar - 1) * ts.beats_per_bar + (n.beat - 1)
        at = beat_index * ts.beat_quarters + Fraction(n.index, n.division) * ts.beat_quarters
        velocity = ACCENT if n.accent else GHOST if n.ghost else NORMAL
        notes[(at, DrumClass[n.drum])] = Note(at, DrumClass[n.drum], velocity)
        # A beat read in a division the default grid can't hold (e.g. triplets
        # in 16ths) gets that division, so the editor's grid matches the page.
        if subdivision_for(n.division, ts) and beat.grid % n.division and n.index:
            divisions[beat_index] = n.division
    beat.notes = sorted(notes.values(), key=Note.sort_key)
    beat.divisions = divisions
    if not beat.notes:
        problems.append("no notes could be read")
    return GrooveResult(beat, label, bars_read, problems)
