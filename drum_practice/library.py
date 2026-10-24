"""Choosing beats (filters, random pick) and remembering best scores."""

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from .model import Beat
from .settings import app_dir

DIFFICULTIES = ("beginner", "intermediate", "advanced")


def genres(beats: list[Beat]) -> list[str]:
    return sorted({b.genre for b in beats})


def filter_beats(beats: list[Beat], genre: str | None = None, difficulty: str | None = None) -> list[Beat]:
    """Beats matching the filters (None = any), easiest first, then by name."""
    matching = [
        b
        for b in beats
        if (genre is None or b.genre == genre) and (difficulty is None or b.difficulty == difficulty)
    ]
    return sorted(matching, key=_difficulty_then_name)


def surprise(
    beats: list[Beat],
    genre: str | None = None,
    difficulty: str | None = None,
    exclude_id: str | None = None,
    rng: random.Random | None = None,
) -> Beat | None:
    """A random beat within the filters, avoiding `exclude_id` (the current
    beat) when there's anything else to pick. None if nothing matches."""
    pool = filter_beats(beats, genre, difficulty)
    others = [b for b in pool if b.id != exclude_id]
    return (rng or random).choice(others or pool) if pool else None


def _difficulty_then_name(beat: Beat) -> tuple[int, str]:
    rank = DIFFICULTIES.index(beat.difficulty) if beat.difficulty in DIFFICULTIES else len(DIFFICULTIES)
    return rank, beat.name.lower()


@dataclass(frozen=True)
class Best:
    score: float
    tempo: float
    bars: int

    def beats(self, other: "Best") -> bool:
        """Higher score wins; on a tie, the faster tempo wins."""
        return (self.score, self.tempo) > (other.score, other.tempo)


class ScoreBook:
    """Best score per beat id, saved as JSON next to the settings."""

    def __init__(self, path: Path | None = None):
        self.path = path or app_dir() / "scores.json"
        self._best: dict[str, Best] = {}
        try:
            data = json.loads(self.path.read_text())
            self._best = {beat_id: Best(**entry) for beat_id, entry in data.items()}
        except (OSError, ValueError, TypeError):
            pass

    def best(self, beat_id: str) -> Best | None:
        return self._best.get(beat_id)

    def record(self, beat_id: str, score: float, tempo: float, bars: int) -> bool:
        """Store the run if it's a new best. Returns True when it is."""
        run = Best(round(score, 1), tempo, bars)
        current = self._best.get(beat_id)
        if current is not None and not run.beats(current):
            return False
        self._best[beat_id] = run
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({k: asdict(v) for k, v in self._best.items()}, indent=2) + "\n"
        )
        return True
