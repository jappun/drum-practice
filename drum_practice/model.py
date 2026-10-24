"""Beat data model and its JSON format.

In JSON, each drum's part is a pattern string with one character per step,
which keeps beat files readable and easy to write by hand:

    "-" or "." rest    "g" ghost    "x" normal    "X" accent

Spaces and "|" are ignored, so a bar of 16ths can be written as
"x-x- x-x- x-x- x-x- |".
"""

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from .kit import DRUM_ORDER, DrumClass

GHOST, NORMAL, ACCENT = 45, 100, 127
_CHAR_VELOCITY = {"g": GHOST, "x": NORMAL, "X": ACCENT}
_REST = "-."
_IGNORED = " |"


@dataclass(frozen=True)
class Note:
    step: int
    drum: DrumClass
    velocity: int = NORMAL

    def sort_key(self) -> tuple[int, int]:
        return self.step, DRUM_ORDER.index(self.drum)


@dataclass
class Beat:
    name: str
    genre: str
    difficulty: str
    tempo: float
    bars: int
    notes: list[Note]
    beats_per_bar: int = 4
    steps_per_beat: int = 4
    # Stable identity for scores: the file name, so renaming a beat keeps its history.
    id: str = field(default="", compare=False)

    @property
    def steps_per_bar(self) -> int:
        return self.beats_per_bar * self.steps_per_beat

    @property
    def total_steps(self) -> int:
        return self.bars * self.steps_per_bar

    def step_seconds(self, tempo: float | None = None) -> float:
        return 60.0 / (tempo or self.tempo) / self.steps_per_beat

    def notes_at(self, step: int) -> list[Note]:
        return [n for n in self.notes if n.step == step]

    def with_bars(self, bars: int) -> "Beat":
        """This beat stretched to `bars` bars: repeated if it's shorter,
        cut to the first `bars` bars if it's longer."""
        total = bars * self.steps_per_bar
        repeats = -(-bars // self.bars)  # ceiling division
        notes = [
            Note(n.step + k * self.total_steps, n.drum, n.velocity)
            for k in range(repeats)
            for n in self.notes
            if n.step + k * self.total_steps < total
        ]
        return replace(self, bars=bars, notes=sorted(notes, key=Note.sort_key))

    def with_tempo(self, tempo: float) -> "Beat":
        return replace(self, tempo=tempo)

    # --- JSON ---

    def to_dict(self) -> dict:
        pattern = {}
        for drum in DRUM_ORDER:
            cells = ["-"] * self.total_steps
            notes = [n for n in self.notes if n.drum is drum]
            if not notes:
                continue
            for n in notes:
                cells[n.step] = _velocity_char(n.velocity)
            pattern[drum.name] = self._format_pattern(cells)
        return {
            "name": self.name,
            "genre": self.genre,
            "difficulty": self.difficulty,
            "tempo": self.tempo,
            "bars": self.bars,
            "beats_per_bar": self.beats_per_bar,
            "steps_per_beat": self.steps_per_beat,
            "pattern": pattern,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Beat":
        beat = cls(
            name=data["name"],
            genre=data["genre"],
            difficulty=data["difficulty"],
            tempo=float(data["tempo"]),
            bars=int(data["bars"]),
            notes=[],
            beats_per_bar=int(data.get("beats_per_bar", 4)),
            steps_per_beat=int(data.get("steps_per_beat", 4)),
        )
        notes = []
        for drum_name, text in data["pattern"].items():
            drum = DrumClass[drum_name]
            cells = [c for c in text if c not in _IGNORED]
            if len(cells) != beat.total_steps:
                raise ValueError(
                    f"{beat.name}: {drum_name} has {len(cells)} steps, expected {beat.total_steps}"
                )
            for step, char in enumerate(cells):
                if char in _REST:
                    continue
                if char not in _CHAR_VELOCITY:
                    raise ValueError(f"{beat.name}: unknown pattern character {char!r}")
                notes.append(Note(step, drum, _CHAR_VELOCITY[char]))
        beat.notes = sorted(notes, key=Note.sort_key)
        return beat

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> "Beat":
        beat = cls.from_dict(json.loads(path.read_text()))
        beat.id = path.stem
        return beat

    def _format_pattern(self, cells: list[str]) -> str:
        bars = []
        for b in range(self.bars):
            bar = cells[b * self.steps_per_bar : (b + 1) * self.steps_per_bar]
            beats = [
                "".join(bar[i : i + self.steps_per_beat])
                for i in range(0, self.steps_per_bar, self.steps_per_beat)
            ]
            bars.append(" ".join(beats))
        return " | ".join(bars)


def _velocity_char(velocity: int) -> str:
    # Nearest of ghost / normal / accent; finer dynamics come in a later phase.
    return min(_CHAR_VELOCITY, key=lambda c: abs(_CHAR_VELOCITY[c] - velocity))


BEATS_DIR = Path(__file__).resolve().parent.parent / "beats"


def load_beats(directory: Path = BEATS_DIR) -> list[Beat]:
    return [Beat.load(p) for p in sorted(directory.rglob("*.json"))]
