"""Exact musical time: positions, time signatures and subdivisions.

Positions are exact fractions of a **quarter note** from the start of a beat
pattern (so a triplet is 1/3, the "a" of a beat is 3/4), and tempo is in
quarter notes per minute. Nothing here rounds, so triplets, 32nds and dotted
rhythms stay exact all the way to the audio scheduler.
"""

import re
from dataclasses import dataclass
from fractions import Fraction
from math import lcm

# --- positions as readable text ("1+2/3" = one and two-thirds quarters) ---

_MIXED = re.compile(r"^\s*(?:(\d+)\s*\+\s*)?(\d+)(?:\s*/\s*(\d+))?\s*$")


def parse_position(text: str) -> Fraction:
    """"2" → 2, "3/4" → 3/4, "1+2/3" → 5/3."""
    match = _MIXED.match(str(text))
    if not match:
        raise ValueError(f"not a position: {text!r} (use e.g. 2, 3/4 or 1+2/3)")
    whole, num, den = match.groups()
    if den is None:
        if whole is not None:
            raise ValueError(f"not a position: {text!r}")
        return Fraction(int(num))
    if int(den) == 0:
        raise ValueError(f"not a position: {text!r} (divides by zero)")
    return int(whole or 0) + Fraction(int(num), int(den))


def format_position(value: Fraction) -> str:
    """The inverse of parse_position, in its shortest form."""
    value = Fraction(value)
    whole, rest = divmod(value, 1)
    if rest == 0:
        return str(whole)
    frac = f"{rest.numerator}/{rest.denominator}"
    return frac if whole == 0 else f"{whole}+{frac}"


# --- time signatures ---


@dataclass(frozen=True)
class TimeSignature:
    numerator: int = 4
    denominator: int = 4

    def __post_init__(self):
        if self.numerator < 1 or self.denominator not in (1, 2, 4, 8, 16, 32):
            raise ValueError(f"unsupported time signature {self.numerator}/{self.denominator}")

    @classmethod
    def parse(cls, text: str) -> "TimeSignature":
        num, _, den = str(text).partition("/")
        return cls(int(num), int(den or 4))

    def __str__(self) -> str:
        return f"{self.numerator}/{self.denominator}"

    @property
    def compound(self) -> bool:
        """6/8, 9/8, 12/8…: felt in groups of three."""
        return self.denominator >= 8 and self.numerator % 3 == 0 and self.numerator > 3

    @property
    def bar_quarters(self) -> Fraction:
        return Fraction(self.numerator * 4, self.denominator)

    @property
    def beat_quarters(self) -> Fraction:
        """Length of one counted beat: a dotted note in compound time."""
        unit = Fraction(4, self.denominator)
        return unit * 3 if self.compound else unit

    @property
    def beats_per_bar(self) -> int:
        return int(self.bar_quarters / self.beat_quarters)


COMMON_TIME_SIGNATURES = ["2/4", "3/4", "4/4", "5/4", "6/8", "7/8", "9/8", "12/8"]


# --- subdivisions ---


@dataclass(frozen=True)
class Subdivision:
    """A note value the grid can be divided into, e.g. 16th notes."""

    name: str
    per_quarter: Fraction  # how many fit in a quarter note

    def columns(self, ts: TimeSignature) -> int | None:
        """Columns this gives one beat of `ts`, or None if it doesn't fit
        evenly (8th triplets don't divide a dotted-quarter beat)."""
        n = ts.beat_quarters * self.per_quarter
        return int(n) if n.denominator == 1 else None


SUBDIVISIONS = [
    Subdivision("16ths", Fraction(4)),
    Subdivision("8th triplets", Fraction(3)),
    Subdivision("16th triplets", Fraction(6)),
    Subdivision("32nds", Fraction(8)),
]
DEFAULT_SUBDIVISION = SUBDIVISIONS[0]


def subdivision_named(name: str) -> Subdivision:
    return next(s for s in SUBDIVISIONS if s.name == name)


def subdivision_for(columns: int, ts: TimeSignature) -> Subdivision | None:
    """The named subdivision that gives `columns` per beat, if any."""
    return next((s for s in SUBDIVISIONS if s.columns(ts) == columns), None)


def columns_to_fit(offsets: list[Fraction], beat_quarters: Fraction, at_least: int = 1) -> int:
    """The fewest columns (a multiple of `at_least`) that put every offset
    within a beat exactly on a column boundary. Offsets are in quarters from
    the beat's start."""
    n = at_least
    for offset in offsets:
        n = lcm(n, (offset / beat_quarters).denominator)
    return n
