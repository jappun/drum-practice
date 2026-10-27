"""Beat data model and its JSON format.

Notes sit at exact positions (see `rhythm`): quarter notes from the start,
as fractions, so triplets and 32nds are exact. Format 2 stores a readable
list of notes:

    {"at": "1+2/3", "drum": "SNARE", "v": "x"}

with "v" one of  "g" ghost, "x" normal, "X" accent.

Format 1 beats (one pattern string per drum on a 16th grid, e.g.
"x-x- x-x- |") still load and are converted; they're saved as format 2.
"""

import json
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path

from .kit import DRUM_ORDER, DrumClass
from .rhythm import (
    DEFAULT_SUBDIVISION,
    TimeSignature,
    columns_to_fit,
    format_position,
    parse_position,
    subdivision_for,
    subdivision_named,
)

GHOST, NORMAL, ACCENT = 45, 100, 127
MAX_BEAT_BARS = 4  # longer music is a song, not a beat
FORMAT = 2
_CHAR_VELOCITY = {"g": GHOST, "x": NORMAL, "X": ACCENT}
_REST = "-."
_IGNORED = " |"


@dataclass(frozen=True)
class Note:
    at: Fraction  # quarter notes from the start of the beat pattern
    drum: DrumClass
    velocity: int = NORMAL
    length: Fraction | None = None  # notated duration, if known; else notation decides

    def sort_key(self) -> tuple[Fraction, int]:
        return self.at, DRUM_ORDER.index(self.drum)


def default_grid(ts: TimeSignature) -> int:
    """Columns per beat for 16th notes in this time signature."""
    return DEFAULT_SUBDIVISION.columns(ts) or 1


@dataclass
class Beat:
    name: str
    genre: str
    difficulty: str
    tempo: float  # quarter notes per minute
    bars: int
    notes: list[Note]
    time_signature: TimeSignature = field(default_factory=TimeSignature)
    grid: int = 4  # columns per beat in the editor, unless overridden below
    divisions: dict[int, int] = field(default_factory=dict)  # beat index -> columns
    # Stable identity for scores: the file name, so renaming a beat keeps its history.
    id: str = field(default="", compare=False)

    # --- lengths ---

    @property
    def bar_quarters(self) -> Fraction:
        return self.time_signature.bar_quarters

    @property
    def beat_quarters(self) -> Fraction:
        return self.time_signature.beat_quarters

    @property
    def beats_per_bar(self) -> int:
        return self.time_signature.beats_per_bar

    @property
    def total_beats(self) -> int:
        return self.bars * self.beats_per_bar

    @property
    def total_quarters(self) -> Fraction:
        return self.bars * self.bar_quarters

    def seconds(self, quarters: Fraction | float) -> float:
        """Seconds from the start to a position, at this beat's tempo."""
        return float(quarters) * 60.0 / self.tempo

    @property
    def duration_seconds(self) -> float:
        return self.seconds(self.total_quarters)

    # --- the grid ---

    def beat_index(self, at: Fraction) -> int:
        return int(at // self.beat_quarters)

    def chosen_columns(self, beat: int) -> int:
        """Columns the user picked for a beat (or the beat's default)."""
        return self.divisions.get(beat, self.grid)

    def columns_in_beat(self, beat: int) -> int:
        """Columns to show for a beat: what was picked, made finer if a note
        in that beat doesn't land on one of them (so nothing is hidden)."""
        start = beat * self.beat_quarters
        offsets = [n.at - start for n in self.notes if self.beat_index(n.at) == beat]
        return columns_to_fit(offsets, self.beat_quarters, at_least=self.chosen_columns(beat))

    def column_length(self, beat: int) -> Fraction:
        return self.beat_quarters / self.columns_in_beat(beat)

    # --- reshaping for practice ---

    def with_bars(self, bars: int) -> "Beat":
        """This beat stretched to `bars` bars: repeated if it's shorter,
        cut to the first `bars` bars if it's longer."""
        end = bars * self.bar_quarters
        repeats = -(-bars // self.bars)  # ceiling division
        notes = [
            replace(n, at=n.at + k * self.total_quarters)
            for k in range(repeats)
            for n in self.notes
            if n.at + k * self.total_quarters < end
        ]
        total_beats = bars * self.beats_per_bar
        divisions = {
            i + k * self.total_beats: cols
            for k in range(repeats)
            for i, cols in self.divisions.items()
            if i + k * self.total_beats < total_beats
        }
        return replace(self, bars=bars, notes=sorted(notes, key=Note.sort_key), divisions=divisions)

    def with_tempo(self, tempo: float) -> "Beat":
        return replace(self, tempo=tempo)

    # --- JSON ---

    def to_dict(self) -> dict:
        ts = self.time_signature
        notes = []
        for n in self.notes:
            entry = {"at": format_position(n.at), "drum": n.drum.name, "v": _velocity_char(n.velocity)}
            if n.length is not None:
                entry["len"] = format_position(n.length)
            notes.append(entry)
        data = {
            "format": FORMAT,
            "name": self.name,
            "genre": self.genre,
            "difficulty": self.difficulty,
            "tempo": self.tempo,
            "time_signature": str(ts),
            "bars": self.bars,
            "grid": _columns_name(self.grid, ts),
        }
        if self.divisions:
            data["divisions"] = {str(i): _columns_name(c, ts) for i, c in sorted(self.divisions.items())}
        data["notes"] = notes
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Beat":
        if "pattern" in data:
            return _from_format_1(data)
        ts = TimeSignature.parse(data.get("time_signature", "4/4"))
        beat = cls(
            name=data["name"],
            genre=data["genre"],
            difficulty=data["difficulty"],
            tempo=float(data["tempo"]),
            bars=int(data["bars"]),
            notes=[],
            time_signature=ts,
            grid=_parse_columns(data.get("grid", default_grid(ts)), ts),
            divisions={int(i): _parse_columns(c, ts) for i, c in data.get("divisions", {}).items()},
        )
        notes = []
        for entry in data["notes"]:
            at = parse_position(entry["at"])
            if not 0 <= at < beat.total_quarters:
                raise ValueError(f"{beat.name}: note at {entry['at']} is outside the beat")
            drum = DrumClass[entry["drum"]]
            char = entry.get("v", "x")
            if char not in _CHAR_VELOCITY:
                raise ValueError(f"{beat.name}: unknown velocity mark {char!r}")
            length = parse_position(entry["len"]) if "len" in entry else None
            notes.append(Note(at, drum, _CHAR_VELOCITY[char], length))
        beat.notes = sorted(notes, key=Note.sort_key)
        return beat

    def save(self, path: Path) -> None:
        path.write_text(_dumps(self.to_dict()))

    @classmethod
    def load(cls, path: Path) -> "Beat":
        beat = cls.from_dict(json.loads(path.read_text()))
        beat.id = path.stem
        return beat


def _from_format_1(data: dict) -> Beat:
    """Convert a format-1 beat (pattern strings on a step grid)."""
    beats_per_bar = int(data.get("beats_per_bar", 4))
    steps_per_beat = int(data.get("steps_per_beat", 4))
    bars = int(data["bars"])
    total_steps = bars * beats_per_bar * steps_per_beat
    notes = []
    for drum_name, text in data["pattern"].items():
        drum = DrumClass[drum_name]
        cells = [c for c in text if c not in _IGNORED]
        if len(cells) != total_steps:
            raise ValueError(f"{data['name']}: {drum_name} has {len(cells)} steps, expected {total_steps}")
        for step, char in enumerate(cells):
            if char in _REST:
                continue
            if char not in _CHAR_VELOCITY:
                raise ValueError(f"{data['name']}: unknown pattern character {char!r}")
            notes.append(Note(Fraction(step, steps_per_beat), drum, _CHAR_VELOCITY[char]))
    return Beat(
        name=data["name"],
        genre=data["genre"],
        difficulty=data["difficulty"],
        tempo=float(data["tempo"]),
        bars=bars,
        notes=sorted(notes, key=Note.sort_key),
        time_signature=TimeSignature(beats_per_bar, 4),
        grid=steps_per_beat,
    )


def _dumps(data: dict) -> str:
    """JSON with one note per line, so a beat file reads like a list."""
    data = dict(data)
    notes = data.pop("notes")
    head = json.dumps(data, indent=2)[: -len("\n}")]
    if not notes:
        return head + ',\n  "notes": []\n}\n'
    lines = ",\n".join("    " + json.dumps(n) for n in notes)
    return head + ',\n  "notes": [\n' + lines + "\n  ]\n}\n"


def _columns_name(columns: int, ts: TimeSignature) -> str | int:
    """A subdivision's name ("16ths") when there is one, else the column count."""
    sub = subdivision_for(columns, ts)
    return sub.name if sub else columns


def _parse_columns(value: str | int, ts: TimeSignature) -> int:
    if isinstance(value, int):
        return value
    if value.isdigit():
        return int(value)
    columns = subdivision_named(value).columns(ts)
    if columns is None:
        raise ValueError(f"{value} doesn't fit a beat of {ts}")
    return columns


def _velocity_char(velocity: int) -> str:
    # Nearest of ghost / normal / accent; finer dynamics come in a later phase.
    return min(_CHAR_VELOCITY, key=lambda c: abs(_CHAR_VELOCITY[c] - velocity))


BEATS_DIR = Path(__file__).resolve().parent.parent / "beats"


def load_beats(directory: Path = BEATS_DIR) -> list[Beat]:
    return [Beat.load(p) for p in sorted(directory.rglob("*.json"))]
