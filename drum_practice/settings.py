"""Per-user settings, stored as JSON in the user's app-data folder."""

import json
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path


def default_path() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".config"
    return base / "Drum Practice" / "settings.json"


@dataclass
class Settings:
    latency_offset: float = 0.0  # seconds subtracted from every hit
    calibrated: bool = False
    tempo: float = 90.0
    bars: int = 2
    count_in: bool = True
    metronome: bool = False  # click along during your turn

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or default_path()
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: Path | None = None) -> None:
        path = path or default_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")
