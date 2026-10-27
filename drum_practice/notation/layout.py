"""Engraving a beat as drum notation. Pure: notes in, glyph positions out.

Coordinates:
- **Vertical** positions are staff steps (half a staff space): 0 is the
  bottom line, 8 the top line, odd numbers are spaces.
- **Horizontal** positions are `X(quarters, offset)`: a time in the beat plus
  a nudge in staff spaces. Spacing is proportional to time, like the grid,
  so a playhead lines up with the notes. The renderer turns X into pixels.

Engraving follows common drum-book practice: hands (cymbals, snare, toms)
are voice 1 with stems up, feet (kick, hi-hat pedal) voice 2 with stems
down. Rhythms are worked out per beat: each note lasts until the next note
in its voice (drums don't sustain, so a length that isn't a single note
value becomes a note plus rests rather than a tie), gaps become rests, notes
are beamed within the beat, and a beat that isn't a natural division of the
meter (e.g. triplets in 4/4) gets a tuplet number.
"""

from dataclasses import dataclass, field
from fractions import Fraction

from ..kit import DrumClass
from ..model import Beat, Note
from ..rhythm import TimeSignature, columns_to_fit

UP, DOWN = 1, -1  # voice / stem direction

FEET = {DrumClass.KICK, DrumClass.HH_PEDAL}
STAFF_POSITION = {
    DrumClass.CRASH: 10,  # ledger line above
    DrumClass.HH_OPEN: 9,  # space above the staff
    DrumClass.HH_CLOSED: 9,
    DrumClass.RIDE: 8,  # top line
    DrumClass.TOM_HIGH: 7,
    DrumClass.TOM_MID: 6,
    DrumClass.SNARE: 5,  # third space
    DrumClass.TOM_LOW: 3,
    DrumClass.KICK: 1,  # bottom space
    DrumClass.HH_PEDAL: -1,  # space below the staff
}
X_HEADS = {DrumClass.CRASH, DrumClass.RIDE, DrumClass.HH_OPEN, DrumClass.HH_CLOSED, DrumClass.HH_PEDAL}

STEM_LENGTH = 7  # staff steps (3.5 spaces)
REST_POSITION = {UP: 6, DOWN: 2}  # usual spot for rests above / below the middle in two-voice writing
# How far each rest glyph reaches above and below its position, in staff
# steps (measured from Bravura), so rests can be moved clear of the other voice.
REST_EXTENT = {
    "whole": (0.1, 1.2),  # hangs from its line
    "half": (1.2, 0.2),  # sits on its line
    "quarter": (3.0, 3.2),
    "8th": (1.4, 2.2),
    "16th": (1.5, 4.1),
    "32nd": (3.4, 4.0),
    "64th": (4.6, 5.2),
}
REST_CLEARANCE = 1  # staff steps kept between a rest and the other voice's noteheads
NOTEHEAD_WIDTH = 1.18  # staff spaces (Bravura's black notehead)
DOT_GAP = 0.4  # space between a notehead (centred on its time) and its dot


def voice_of(drum: DrumClass) -> int:
    return DOWN if drum in FEET else UP


# Note values in quarters, longest first, and their glyph names.
_VALUES = [Fraction(4), Fraction(2), Fraction(1), Fraction(1, 2), Fraction(1, 4), Fraction(1, 8), Fraction(1, 16)]
_NAMES = {
    Fraction(4): "whole",
    Fraction(2): "half",
    Fraction(1): "quarter",
    Fraction(1, 2): "8th",
    Fraction(1, 4): "16th",
    Fraction(1, 8): "32nd",
    Fraction(1, 16): "64th",
}


def beams_for(value: Fraction) -> int:
    """Beams (or flags) a note value has: 8th 1, 16th 2, 32nd 3…"""
    count = 0
    while value < 1:
        value *= 2
        count += 1
    return count


def note_value(length: Fraction) -> tuple[Fraction, int] | None:
    """(value, dots) for a length that is one written note, else None."""
    for value in _VALUES:
        if length == value:
            return value, 0
        if length == value * Fraction(3, 2):
            return value, 1
    return None


def longest_value_within(length: Fraction) -> tuple[Fraction, int]:
    """The longest single written note (dots allowed) not longer than `length`."""
    best = None
    for value in _VALUES:
        for dots, size in ((1, value * Fraction(3, 2)), (0, value)):
            if size <= length and (best is None or size > best[2]):
                best = (value, dots, size)
    if best is None:
        return _VALUES[-1], 0
    return best[0], best[1]


def split_into_values(length: Fraction) -> list[tuple[Fraction, int]]:
    """Written values that add up to `length`, longest first (for rests)."""
    parts = []
    while length > 0:
        value, dots = longest_value_within(length)
        size = value * (Fraction(3, 2) if dots else 1)
        if size > length:  # shorter than a 64th: stop rather than loop forever
            break
        parts.append((value, dots))
        length -= size
    return parts


def written_division(compound: bool, columns: int) -> tuple[int, int | None]:
    """How to write a beat whose notes need `columns` equal steps.

    A meter divides a beat naturally into powers of two (simple time: 1, 2,
    4, 8…) or three times those (compound: 3, 6, 12…). If one of those is a
    multiple of `columns`, the beat is written on it with no tuplet (a lone
    note in 6/8 is a dotted quarter, three steps of 8ths). Otherwise it needs
    a tuplet: `columns` notes written as the nearest natural division (8th
    triplets in 4/4 are three 8ths under a "3").

    Returns (written division, tuplet number or None)."""
    naturals = [(3 if compound else 1) * 2**k for k in range(8)]
    for n in naturals:
        if n % columns == 0:
            return n, None
    fitting = [n for n in naturals if n <= columns]
    return (max(fitting) if fitting else min(naturals)), columns


def beam_groups(ts: TimeSignature) -> list[int]:
    """How many beats each beam group spans, per bar. Odd x/8 meters beam in
    twos with a three at the end (7/8 = 2+2+3), 3/8 beams the whole bar, and
    everything else beams beat by beat."""
    if not ts.compound and ts.denominator == 8:
        n = ts.numerator
        if n == 3:
            return [3]
        groups = [2] * (n // 2)
        if n % 2:
            groups[-1] = 3
        return groups
    return [1] * ts.beats_per_bar


# --- the layout ---


@dataclass(frozen=True)
class X:
    quarters: Fraction  # time in the beat
    offset: float = 0.0  # nudge, in staff spaces


@dataclass(frozen=True)
class Head:
    """A notehead (or rest/flag/dot/articulation glyph)."""

    kind: str  # e.g. "head:black", "head:x", "rest:16th", "flag:8th:up", "dot", "open"
    x: X
    position: float
    voice: int
    note: Note | None = None  # the note a notehead belongs to (for highlighting/results)


@dataclass(frozen=True)
class Stem:
    x: X  # the notehead column; the renderer attaches it to the notehead's side
    start: float  # staff position at the notehead end
    end: float  # staff position at the tip
    voice: int


@dataclass(frozen=True)
class BeamSegment:
    start: X
    end: X
    position: float  # staff position of the primary beam (at the stem tips)
    level: int  # 1 = 8th beam, 2 = 16th…
    voice: int
    stub: int = 0  # 0 for a full segment, -1/+1 for a partial beam pointing left/right


@dataclass(frozen=True)
class Tuplet:
    start: X
    end: X
    number: int
    position: float  # staff position just beyond the stem tips
    voice: int


@dataclass(frozen=True)
class Event:
    """One written note or rest in a voice."""

    at: Fraction  # where it starts (real time, quarters)
    value: Fraction  # written value in quarters (inside a tuplet this differs from the real length)
    dots: int
    notes: tuple[Note, ...] = ()  # empty for a rest
    scale: Fraction = Fraction(1)  # real length / written length (e.g. 2/3 in a triplet)

    @property
    def is_rest(self) -> bool:
        return not self.notes

    @property
    def length(self) -> Fraction:
        """How long it really lasts, in quarters."""
        return self.value * (Fraction(3, 2) if self.dots else 1) * self.scale


@dataclass
class Layout:
    beat: Beat
    heads: list[Head] = field(default_factory=list)
    stems: list[Stem] = field(default_factory=list)
    beams: list[BeamSegment] = field(default_factory=list)
    tuplets: list[Tuplet] = field(default_factory=list)
    ledgers: list[tuple[X, int]] = field(default_factory=list)  # (notehead x, staff position)
    events: dict[int, list[list[Event]]] = field(default_factory=dict)  # voice -> per beat events

    @property
    def bar_lines(self) -> list[tuple[Fraction, str]]:
        """(quarters, kind): a repeat at each end (beats loop), single lines between bars."""
        b = self.beat
        lines = [(Fraction(0), "repeat-start")]
        lines += [(i * b.bar_quarters, "single") for i in range(1, b.bars)]
        lines.append((b.total_quarters, "repeat-end"))
        return lines

    def describe(self) -> str:
        """A stable text form of the layout, for snapshot tests."""
        lines = [f"{self.beat.name} | {self.beat.time_signature} | {self.beat.bars} bar(s)"]
        for voice in (UP, DOWN):
            label = "hands" if voice == UP else "feet"
            for index, events in enumerate(self.events.get(voice, [])):
                parts = []
                for e in events:
                    value = _NAMES[e.value] + "." * e.dots
                    what = "rest" if e.is_rest else "+".join(n.drum.name for n in e.notes)
                    parts.append(f"{_q(e.at)} {value} {what}")
                lines.append(f"  {label} beat {index + 1}: " + "; ".join(parts))
        for t in self.tuplets:
            lines.append(f"  tuplet {t.number} {_q(t.start.quarters)}..{_q(t.end.quarters)} {'up' if t.voice == UP else 'down'}")
        groups = sorted({(s.voice, s.position, _q(s.start.quarters), _q(s.end.quarters), s.level, s.stub) for s in self.beams})
        for voice, _, start, end, level, stub in groups:
            kind = "beam" if stub == 0 else f"stub{'<' if stub < 0 else '>'}"
            lines.append(f"  {kind} L{level} {start}..{end} {'up' if voice == UP else 'down'}")
        return "\n".join(lines) + "\n"


def _q(value: Fraction) -> str:
    return str(value)


def layout_beat(beat: Beat) -> Layout:
    layout = Layout(beat)
    for voice in (UP, DOWN):
        voice_notes = [n for n in beat.notes if voice_of(n.drum) == voice]
        per_beat = []
        for bar in range(beat.bars):
            bar_notes = [n for n in voice_notes if bar * beat.bar_quarters <= n.at < (bar + 1) * beat.bar_quarters]
            if not bar_notes:
                # A silent bar gets one whole-bar rest, written as a whole rest.
                start = bar * beat.bar_quarters
                rest = Event(start, Fraction(4), 0, scale=beat.bar_quarters / 4)
                per_beat.extend([[rest]] + [[] for _ in range(beat.beats_per_bar - 1)])
                _place_bar_rest(layout, start, beat.bar_quarters, voice)
                continue
            engraved = [
                _engrave_beat(beat, bar * beat.beats_per_bar + i, bar_notes) for i in range(beat.beats_per_bar)
            ]
            per_beat.extend(events for events, _ in engraved)
            first = 0
            for span in beam_groups(beat.time_signature):
                _place_group(layout, engraved[first : first + span], voice)
                first += span
        layout.events[voice] = per_beat
    return layout


def _engrave_beat(beat: Beat, index: int, notes: list[Note]) -> tuple[list[Event], int | None]:
    """The written events of one beat of one voice, and its tuplet number if any."""
    start = index * beat.beat_quarters
    end = start + beat.beat_quarters
    inside = [n for n in notes if start <= n.at < end]
    onsets = sorted({n.at for n in inside})
    if not onsets:
        return [Event(start, value, dots) for value, dots in split_into_values(beat.beat_quarters)], None

    columns = columns_to_fit([at - start for at in onsets], beat.beat_quarters, at_least=1)
    natural, tuplet = written_division(beat.time_signature.compound, columns)
    if tuplet is None:
        columns = natural  # write it on the meter's own (finer) grid
    # Real length of one column, and the written length it's shown as.
    real_unit = beat.beat_quarters / columns
    written_unit = beat.beat_quarters / natural if tuplet else real_unit

    events: list[Event] = []

    scale = real_unit / written_unit

    def add_rests(at: Fraction, written: Fraction) -> None:
        for value, dots in split_into_values(written):
            rest = Event(at, value, dots, scale=scale)
            events.append(rest)
            at += rest.length

    first = int((onsets[0] - start) / real_unit)
    if first:
        add_rests(start, first * written_unit)
    for i, at in enumerate(onsets):
        column = int((at - start) / real_unit)
        next_column = int((onsets[i + 1] - start) / real_unit) if i + 1 < len(onsets) else columns
        units = next_column - column
        chord = tuple(sorted((n for n in inside if n.at == at), key=lambda n: STAFF_POSITION[n.drum]))
        written = units * written_unit
        exact = note_value(written)
        value, dots = exact if exact else longest_value_within(written)
        note = Event(at, value, dots, chord, scale=scale)
        events.append(note)
        used = value * (Fraction(3, 2) if dots else 1)
        if used < written:  # drums don't sustain: fill the rest of the gap with rests
            add_rests(at + note.length, written - used)
    return events, tuplet


def rest_position(layout: Layout, voice: int, start: Fraction, length: Fraction, value: str) -> int:
    """Where a rest goes: its usual spot, unless the other voice has notes
    during it, in which case it moves clear of them (feet rests below the
    hands, hand rests above the feet), as engravers do."""
    usual = REST_POSITION[voice] + (2 if value == "whole" else 0)
    others = [
        STAFF_POSITION[n.drum]
        for n in layout.beat.notes
        if voice_of(n.drum) != voice and start <= n.at < start + length
    ]
    if not others:
        return usual
    above, below = REST_EXTENT[value]
    if voice == DOWN:
        limit = min(others) - 1 - REST_CLEARANCE - above  # notehead reaches one step below its position
        position = min(usual, int(limit // 1))
    else:
        limit = max(others) + 1 + REST_CLEARANCE + below
        position = max(usual, -int(-limit // 1))
    if value in ("whole", "half") and position % 2:
        position += -1 if voice == DOWN else 1  # these sit on a line
    return position


def _place_bar_rest(layout: Layout, start: Fraction, bar_quarters: Fraction, voice: int) -> None:
    # Centred in the bar; a whole rest hangs from a line.
    position = rest_position(layout, voice, start, bar_quarters, "whole")
    layout.heads.append(Head("rest:whole", X(start + bar_quarters / 2, -0.56), position, voice))


def _place_group(layout: Layout, beats: list[tuple[list[Event], int | None]], voice: int) -> None:
    """Place the notes, rests, stems and beams of a beam group (one or more
    beats), and each beat's tuplet number."""
    events = [e for beat_events, _ in beats for e in beat_events]
    notes = [e for e in events if not e.is_rest]
    # Beams don't cross into or out of a tuplet beat.
    breaks = set()
    for k, (beat_events, tuplet) in enumerate(beats):
        if k and beat_events and (tuplet or beats[k - 1][1]):
            breaks.add(id(beat_events[0]))

    # Rests.
    for e in events:
        if e.is_rest:
            position = rest_position(layout, voice, e.at, e.length, _NAMES[e.value])
            layout.heads.append(Head(f"rest:{_NAMES[e.value]}", X(e.at), position, voice))
            if e.dots:
                dot = position + 1 if position % 2 == 0 else position  # dots sit in a space
                layout.heads.append(Head("dot", X(e.at, NOTEHEAD_WIDTH / 2 + DOT_GAP), dot, voice))

    # Beam groups: runs of beamable notes (8th or shorter) not broken by a rest.
    groups: list[list[Event]] = []
    run: list[Event] = []
    for e in events:
        if id(e) in breaks and run:
            groups.append(run)
            run = []
        if not e.is_rest and e.value < 1:
            run.append(e)
        else:
            if run:
                groups.append(run)
            run = []
    if run:
        groups.append(run)
    beamed = {id(e) for g in groups if len(g) > 1 for e in g}

    # Stem tips: shared by a beam group, else per note.
    tips: dict[int, float] = {}
    for g in groups:
        if len(g) > 1:
            if voice == UP:
                tip = max(STAFF_POSITION[n.drum] for e in g for n in e.notes) + STEM_LENGTH
            else:
                tip = min(STAFF_POSITION[n.drum] for e in g for n in e.notes) - STEM_LENGTH
            for e in g:
                tips[id(e)] = tip

    for e in notes:
        positions = [STAFF_POSITION[n.drum] for n in e.notes]
        hollow = e.value >= 2
        for n in e.notes:
            pos = STAFF_POSITION[n.drum]
            shape = "x" if n.drum in X_HEADS else "black"
            layout.heads.append(Head(f"head:{shape}{':half' if hollow else ''}", X(e.at), pos, voice, n))
            for ledger in _ledgers(pos):
                layout.ledgers.append((X(e.at), ledger))
            if e.dots:
                dot_pos = pos + 1 if pos % 2 == 0 else pos  # dots sit in a space
                layout.heads.append(Head("dot", X(e.at, NOTEHEAD_WIDTH / 2 + DOT_GAP), dot_pos, voice))
        if e.value >= 4:
            continue  # a whole note has no stem
        base = min(positions) if voice == UP else max(positions)
        far = max(positions) if voice == UP else min(positions)
        tip = tips.get(id(e), far + voice * STEM_LENGTH)
        layout.stems.append(Stem(X(e.at), base, tip, voice))
        if id(e) not in beamed and e.value < 1:
            direction = "up" if voice == UP else "down"
            layout.heads.append(Head(f"flag:{_NAMES[e.value]}:{direction}", X(e.at), tip, voice))
        if any(n.drum is DrumClass.HH_OPEN for n in e.notes):
            above = max(tip, max(positions)) + 2 if voice == UP else max(positions) + 3
            layout.heads.append(Head("open", X(e.at), above, voice))

    # Beams, level by level, with stubs for notes that need more beams than their neighbours.
    for g in groups:
        if len(g) < 2:
            continue
        tip = tips[id(g[0])]
        top_level = max(beams_for(e.value) for e in g)
        for level in range(1, top_level + 1):
            i = 0
            while i < len(g):
                if beams_for(g[i].value) < level:
                    i += 1
                    continue
                j = i
                while j + 1 < len(g) and beams_for(g[j + 1].value) >= level:
                    j += 1
                if j > i:
                    layout.beams.append(BeamSegment(X(g[i].at), X(g[j].at), tip, level, voice))
                else:
                    # A lone note at this level: a short beam towards its neighbour in time.
                    stub = -1 if i == len(g) - 1 else 1
                    layout.beams.append(BeamSegment(X(g[i].at), X(g[i].at), tip, level, voice, stub))
                i = j + 1

    for beat_events, tuplet in beats:
        beat_notes = [e for e in beat_events if not e.is_rest]
        if not tuplet or not beat_notes:
            continue
        tip_extreme = (max if voice == UP else min)(
            tips.get(id(e), (max if voice == UP else min)(STAFF_POSITION[n.drum] for n in e.notes) + voice * STEM_LENGTH)
            for e in beat_notes
        )
        layout.tuplets.append(
            Tuplet(X(beat_events[0].at), X(beat_events[-1].at), tuplet, tip_extreme + voice * 2, voice)
        )


def _ledgers(position: int) -> list[int]:
    """Ledger lines a notehead at `position` needs (lines are even positions)."""
    if position >= 10:
        return list(range(10, position + 1, 2))
    if position <= -2:
        return list(range(-2, position - 1, -2))
    return []
