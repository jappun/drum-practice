"""Dev mode only: the laptop keyboard standing in for drum pads.

Only used when the app is launched with --dev. Keys become ordinary `Hit`s,
so everything downstream (recording, grading, results) is the real code path.
"""

from .kit import NOTE_MAP, DrumClass

KEY_MAP: dict[str, DrumClass] = {
    " ": DrumClass.KICK,
    "f": DrumClass.SNARE,
    "j": DrumClass.HH_CLOSED,
    "u": DrumClass.HH_OPEN,
    "c": DrumClass.HH_PEDAL,
    "g": DrumClass.TOM_HIGH,
    "h": DrumClass.TOM_MID,
    "b": DrumClass.TOM_LOW,
    "i": DrumClass.CRASH,
    "o": DrumClass.RIDE,
}


def drum_for_key(text: str) -> DrumClass | None:
    """The drum for a key's typed text, or None if the key isn't mapped."""
    return KEY_MAP.get(text.lower()) if len(text) == 1 else None


def key_label(drum: DrumClass) -> str:
    """How to show a drum's key to the user, e.g. "F" or "Space"."""
    key = next(k for k, d in KEY_MAP.items() if d is drum)
    return "Space" if key == " " else key.upper()


def note_for(drum: DrumClass) -> int:
    """A General MIDI note for the drum, so keyboard hits look like kit hits."""
    return next(note for note, d in NOTE_MAP.items() if d is drum)
