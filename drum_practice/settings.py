"""Per-user settings, stored as JSON in the user's app-data folder."""

import json
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import ClassVar


def app_dir() -> Path:
    """Where the app keeps per-user files (settings, scores)."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".config"
    return base / "Drum Practice"


class _JsonFile:
    """Load/save a dataclass as JSON in the app-data folder (FILENAME)."""

    FILENAME: ClassVar[str]

    @classmethod
    def load(cls, path: Path | None = None):
        path = path or app_dir() / cls.FILENAME
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: Path | None = None) -> None:
        path = path or app_dir() / self.FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")


@dataclass
class Settings(_JsonFile):
    FILENAME: ClassVar[str] = "settings.json"

    latency_offset: float = 0.0  # seconds subtracted from every hit
    calibrated: bool = False
    tempo: float = 90.0
    bars: int = 2
    count_in: bool = True
    metronome: bool = False  # click along during your turn
    beat_id: str = ""  # last beat picked, reopened on launch
    library_collapsed: bool = False


@dataclass
class DevSettings(_JsonFile):
    """Dev mode (--dev) only, in its own file so the regular app never sees it."""

    FILENAME: ClassVar[str] = "dev_settings.json"

    keyboard_latency_offset: float = 0.0
    keyboard_calibrated: bool = False
