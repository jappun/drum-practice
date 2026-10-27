"""Drum classes and the MIDI note map for the kit.

Every incoming note is reduced to one of ten drum classes. The hi-hat pedal
("chick") is its own class, not merged into closed hi-hat, since it's notated
separately in drum charts.
"""

from enum import Enum


class DrumClass(Enum):
    KICK = "Kick"
    SNARE = "Snare"
    HH_CLOSED = "Hi-hat (closed)"
    HH_OPEN = "Hi-hat (open)"
    HH_PEDAL = "Hi-hat (pedal)"
    TOM_HIGH = "Tom 1 (high)"
    TOM_MID = "Tom 2 (mid)"
    TOM_LOW = "Tom 3 (floor)"
    CRASH = "Crash"
    RIDE = "Ride"

    @property
    def label(self) -> str:
        return self.value


# Display order, top to bottom, for grids and pad rows.
DRUM_ORDER = [
    DrumClass.CRASH,
    DrumClass.RIDE,
    DrumClass.HH_OPEN,
    DrumClass.HH_CLOSED,
    DrumClass.TOM_HIGH,
    DrumClass.TOM_MID,
    DrumClass.SNARE,
    DrumClass.TOM_LOW,
    DrumClass.KICK,
    DrumClass.HH_PEDAL,
]

# General MIDI drum notes plus common Roland extras (rims, edges, bell), so
# most kits work out of the box.
NOTE_MAP: dict[int, DrumClass] = {
    35: DrumClass.KICK,
    36: DrumClass.KICK,
    37: DrumClass.SNARE,  # side stick
    38: DrumClass.SNARE,
    40: DrumClass.SNARE,  # rim shot
    22: DrumClass.HH_CLOSED,  # closed edge
    42: DrumClass.HH_CLOSED,
    26: DrumClass.HH_OPEN,  # open edge
    46: DrumClass.HH_OPEN,
    44: DrumClass.HH_PEDAL,
    48: DrumClass.TOM_HIGH,
    50: DrumClass.TOM_HIGH,
    45: DrumClass.TOM_MID,
    47: DrumClass.TOM_MID,
    41: DrumClass.TOM_LOW,
    43: DrumClass.TOM_LOW,
    58: DrumClass.TOM_LOW,
    49: DrumClass.CRASH,
    52: DrumClass.CRASH,
    55: DrumClass.CRASH,
    57: DrumClass.CRASH,
    51: DrumClass.RIDE,
    53: DrumClass.RIDE,  # bell
    59: DrumClass.RIDE,
}


def classify(note: int) -> DrumClass | None:
    """Return the drum class for a MIDI note, or None if it isn't mapped."""
    return NOTE_MAP.get(note)
