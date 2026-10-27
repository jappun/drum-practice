"""Scores a recorded performance against the beat. Pure functions, no I/O.

Times are seconds on one shared clock (perf_counter), with the player's
latency offset already removed from the hits.
"""

from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction

from .kit import DrumClass

PERFECT_WINDOW = 0.030
GOOD_WINDOW = 0.070
PEDAL_WINDOW = 0.040  # hi-hat pedal second pass, see `_pedal_pass`

GOOD_CREDIT = 0.6  # a Good counts as 0.6 of a Perfect
EXTRA_PENALTY = 0.5  # each extra hit costs half a note


class Verdict(Enum):
    PERFECT = "Perfect"
    GOOD = "Good"
    MISS = "Miss"


@dataclass(frozen=True)
class Expected:
    time: float
    drum: DrumClass
    at: Fraction  # position in the beat, for display


@dataclass(frozen=True)
class Played:
    time: float
    drum: DrumClass


@dataclass(frozen=True)
class NoteResult:
    expected: Expected
    verdict: Verdict
    offset: float | None = None  # hit minus expected; negative = early

    @property
    def early(self) -> bool:
        return self.offset is not None and self.offset < 0


@dataclass
class Result:
    notes: list[NoteResult]
    extras: list[Played] = field(default_factory=list)
    ignored: list[Played] = field(default_factory=list)  # pedal closes excused by the pedal rule

    def count(self, verdict: Verdict) -> int:
        return sum(1 for n in self.notes if n.verdict is verdict)

    @property
    def score(self) -> float:
        """0–100."""
        total = len(self.notes)
        if total == 0:
            return 0.0 if self.extras else 100.0
        points = (
            self.count(Verdict.PERFECT)
            + GOOD_CREDIT * self.count(Verdict.GOOD)
            - EXTRA_PENALTY * len(self.extras)
        )
        return max(0.0, min(1.0, points / total)) * 100

    @property
    def mean_offset(self) -> float | None:
        """Average timing of matched notes; negative means rushing."""
        offsets = [n.offset for n in self.notes if n.offset is not None]
        return sum(offsets) / len(offsets) if offsets else None


def grade(expected: list[Expected], played: list[Played]) -> Result:
    played = sorted(played, key=lambda p: p.time)

    # Pair each expected note with the closest unused hit on the same drum,
    # taking the tightest pairs first so a stray hit can't steal a note.
    pairs = sorted(
        (abs(p.time - e.time), ei, pi)
        for ei, e in enumerate(expected)
        for pi, p in enumerate(played)
        if p.drum is e.drum and abs(p.time - e.time) <= GOOD_WINDOW
    )
    match: dict[int, int] = {}
    used: set[int] = set()
    for _, ei, pi in pairs:
        if ei not in match and pi not in used:
            match[ei] = pi
            used.add(pi)

    notes = []
    for ei, e in enumerate(expected):
        if ei in match:
            offset = played[match[ei]].time - e.time
            verdict = Verdict.PERFECT if abs(offset) <= PERFECT_WINDOW else Verdict.GOOD
            notes.append(NoteResult(e, verdict, offset))
        else:
            notes.append(NoteResult(e, Verdict.MISS))

    leftovers = [p for pi, p in enumerate(played) if pi not in used]
    extras, ignored = _pedal_pass(leftovers, played)
    return Result(notes, extras, ignored)


def _pedal_pass(leftovers: list[Played], played: list[Played]) -> tuple[list[Played], list[Played]]:
    """Excuse leftover pedal chicks that are just the hi-hat closing:

    A. within PEDAL_WINDOW of a closed hi-hat stick hit (hand and foot together);
    B. otherwise, closing after an open stick hit that landed more than
       PEDAL_WINDOW earlier. Each open hit excuses one close. A chick sooner
       than that chokes the open hat, so it stays an extra.
    """
    sticks = [p for p in played if p.drum in (DrumClass.HH_CLOSED, DrumClass.HH_OPEN)]
    closes_used: set[int] = set()  # indexes into `sticks` of open hits already closed
    extras, ignored = [], []
    for hit in leftovers:
        if hit.drum is not DrumClass.HH_PEDAL:
            extras.append(hit)
            continue

        if any(
            s.drum is DrumClass.HH_CLOSED and abs(s.time - hit.time) <= PEDAL_WINDOW
            for s in sticks
        ):
            ignored.append(hit)
            continue

        earlier = [i for i, s in enumerate(sticks) if s.time < hit.time]
        if earlier:
            last = earlier[-1]
            stick = sticks[last]
            if stick.drum is DrumClass.HH_OPEN and last not in closes_used:
                closes_used.add(last)  # the hat is closed now either way
                if hit.time - stick.time > PEDAL_WINDOW:
                    ignored.append(hit)
                    continue
        extras.append(hit)
    return extras, ignored
