"""The practice sequence: count-in → demo → count-in → your turn.

`Timeline` is pure sample arithmetic, so it's testable offline; the whole
sequence is short, so it's scheduled into the mixer in one go.
"""

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

import numpy as np

from .audio import Mixer
from .grading import Expected
from .model import Beat
from .sounds import CHOKES


class Stage(Enum):
    COUNT_IN = "Count-in"
    DEMO = "Listen"
    PLAY = "Your turn"
    DONE = "Done"


@dataclass(frozen=True)
class Segment:
    stage: Stage
    start: int  # absolute sample
    end: int


@dataclass(frozen=True)
class Click:
    sample: int
    accent: bool


class Timeline:
    def __init__(
        self,
        beat: Beat,
        start: int,
        sample_rate: int,
        count_in: bool = True,
        metronome: bool = False,
    ):
        self.beat = beat
        self.sample_rate = sample_rate
        self.metronome = metronome  # click on every beat of your turn
        self.quarter_samples = 60.0 / beat.tempo * sample_rate
        plan = []  # (stage, length in quarters)
        if count_in:
            plan.append((Stage.COUNT_IN, beat.bar_quarters))
        plan.append((Stage.DEMO, beat.total_quarters))
        if count_in:
            plan.append((Stage.COUNT_IN, beat.bar_quarters))
        plan.append((Stage.PLAY, beat.total_quarters))

        self.segments: list[Segment] = []
        so_far = Fraction(0)
        for stage, length in plan:
            # Every boundary is computed exactly from the start, so nothing drifts.
            seg_start = start + round(so_far * self.quarter_samples)
            so_far += length
            self.segments.append(Segment(stage, seg_start, start + round(so_far * self.quarter_samples)))

    @property
    def end(self) -> int:
        return self.segments[-1].end

    def segment(self, stage: Stage) -> Segment:
        """The last segment with this stage (for PLAY and DEMO there's only one)."""
        return [s for s in self.segments if s.stage is stage][-1]

    def stage_at(self, sample: float) -> tuple[Stage, float]:
        """(stage, quarters into that stage) for an absolute sample."""
        for seg in self.segments:
            if sample < seg.end:
                return seg.stage, max(0.0, (sample - seg.start) / self.quarter_samples)
        return Stage.DONE, 0.0

    def clicks(self) -> list[Click]:
        beat = self.beat
        out = []
        for seg in self.segments:
            if seg.stage is Stage.COUNT_IN or (seg.stage is Stage.PLAY and self.metronome):
                length = beat.bar_quarters if seg.stage is Stage.COUNT_IN else beat.total_quarters
                beats = int(length / beat.beat_quarters)
                for b in range(beats):
                    sample = seg.start + round(b * beat.beat_quarters * self.quarter_samples)
                    out.append(Click(sample, accent=b % beat.beats_per_bar == 0))
        return out

    def note_sample(self, stage: Stage, at: Fraction) -> int:
        return self.segment(stage).start + round(at * self.quarter_samples)

    def expected(self, sample_to_time) -> list[Expected]:
        """The notes to play in the PLAY segment, timed with `sample_to_time`."""
        return [
            Expected(sample_to_time(self.note_sample(Stage.PLAY, n.at)), n.drum, n.at)
            for n in self.beat.notes
        ]

    def schedule(self, mixer: Mixer, kit: dict, clicks: tuple[np.ndarray, np.ndarray]) -> None:
        """Queue the clicks and the demo; the beat itself is silent in the PLAY segment."""
        accent_click, click = clicks
        for c in self.clicks():
            mixer.schedule(c.sample, accent_click if c.accent else click)
        for n in self.beat.notes:
            mixer.schedule(
                self.note_sample(Stage.DEMO, n.at),
                kit[n.drum],
                gain=n.velocity / 127,
                group=n.drum,
                chokes=CHOKES.get(n.drum),
            )
