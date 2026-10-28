"""Choosing beats (search, random pick) and remembering best scores."""

import json
import random
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .model import Beat
from .settings import app_dir

DIFFICULTIES = ("beginner", "intermediate", "advanced")


def genres(beats: list[Beat]) -> list[str]:
    return sorted({b.genre for b in beats})


def search_beats(beats: list[Beat], query: str = "") -> list[Beat]:
    """Beats whose name contains every word of the query (any case), in
    natural name order. An empty query matches everything."""
    words = query.lower().split()
    matching = [b for b in beats if all(w in b.name.lower() for w in words)]
    return sorted(matching, key=_natural_name)


def surprise(
    beats: list[Beat],
    exclude_id: str | None = None,
    rng: random.Random | None = None,
) -> Beat | None:
    """A random beat from the whole library (the search doesn't narrow it),
    avoiding `exclude_id` (the current beat) when there's anything else to
    pick. None if the library is empty."""
    others = [b for b in beats if b.id != exclude_id]
    return (rng or random).choice(others or beats) if beats else None


def _natural_name(beat: Beat) -> tuple:
    # Natural order, so "Groove 2" comes before "Groove 10".
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", beat.name.lower()))


EXAMPLE_ID_PREFIX = "example_"


def is_example(beat: Beat) -> bool:
    return beat.id.startswith(EXAMPLE_ID_PREFIX)


def visible_beats(beats: list[Beat], hidden_examples: list[str]) -> list[Beat]:
    """The library minus any example beats the user has hidden."""
    hidden = set(hidden_examples)
    return [b for b in beats if not (is_example(b) and b.id in hidden)]


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

    def forget_prefix(self, prefix: str) -> None:
        """Drop every best score whose beat id starts with `prefix`."""
        stale = [k for k in self._best if k.startswith(prefix)]
        for k in stale:
            del self._best[k]
        if stale:
            self._save()

    def forget(self, beat_id: str) -> None:
        """Drop a beat's best score (it was deleted, or its notes changed)."""
        if self._best.pop(beat_id, None) is not None:
            self._save()

    def record(self, beat_id: str, score: float, tempo: float, bars: int) -> bool:
        """Store the run if it's a new best. Returns True when it is."""
        run = Best(round(score, 1), tempo, bars)
        current = self._best.get(beat_id)
        if current is not None and not run.beats(current):
            return False
        self._best[beat_id] = run
        self._save()
        return True

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({k: asdict(v) for k, v in self._best.items()}, indent=2) + "\n"
        )


USER_ID_PREFIX = "user_"


def is_user_beat(beat: Beat) -> bool:
    return beat.id.startswith(USER_ID_PREFIX)


class UserBeats:
    """Beats the user made in the editor, one JSON file each in the app-data
    folder (separate from the bundled library, which is read-only)."""

    def __init__(self, directory: Path | None = None):
        self.directory = directory or app_dir() / "my_beats"

    def load(self) -> list[Beat]:
        if not self.directory.exists():
            return []
        beats = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                beats.append(Beat.load(path))
            except (OSError, ValueError, KeyError):
                continue  # a damaged file shouldn't stop the app from starting
        return beats

    def save(self, beat: Beat) -> Beat:
        """Write the beat, giving it an id the first time. Returns the saved beat."""
        if not is_user_beat(beat):
            beat = replace(beat, id=self._new_id(beat.name))
        self.directory.mkdir(parents=True, exist_ok=True)
        beat.save(self.directory / f"{beat.id}.json")
        return beat

    def delete(self, beat_id: str) -> None:
        (self.directory / f"{beat_id}.json").unlink(missing_ok=True)
        self._photo_path(beat_id).unlink(missing_ok=True)

    # A beat imported from a photo keeps the photo, to show beside the editor.

    def save_photo(self, beat_id: str, image: bytes) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._photo_path(beat_id).write_bytes(image)

    def photo(self, beat_id: str) -> bytes | None:
        path = self._photo_path(beat_id)
        return path.read_bytes() if path.exists() else None

    def _photo_path(self, beat_id: str) -> Path:
        return self.directory / f"{beat_id}.photo"

    def _new_id(self, name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "beat"
        n = 1
        while (self.directory / f"{USER_ID_PREFIX}{slug}_{n}.json").exists():
            n += 1
        return f"{USER_ID_PREFIX}{slug}_{n}"
