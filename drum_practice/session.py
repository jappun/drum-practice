"""The practice sequence: count-in → demo → count-in → your turn.

`Timeline` is pure sample arithmetic, so it's testable offline; the whole
sequence is short, so it's scheduled into the mixer in one go.
"""

from dataclasses import dataclass
from enum import Enum

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
    def __init__(self, beat: Beat, start: int, sample_rate: int, count_in: bool = True):
        self.beat = beat
        self.sample_rate = sample_rate
        self.step_samples = beat.step_seconds() * sample_rate
        bar = beat.steps_per_bar
        plan = []
        if count_in:
            plan.append((Stage.COUNT_IN, bar))
        plan.append((Stage.DEMO, beat.total_steps))
        if count_in:
            plan.append((Stage.COUNT_IN, bar))
        plan.append((Stage.PLAY, beat.total_steps))

        self.segments: list[Segment] = []
        steps_so_far = 0
        for stage, length in plan:
            # Every boundary is computed from the start, so rounding never drifts.
            seg_start = start + round(steps_so_far * self.step_samples)
            steps_so_far += length
            self.segments.append(Segment(stage, seg_start, start + round(steps_so_far * self.step_samples)))

    @property
    def end(self) -> int:
        return self.segments[-1].end

    def segment(self, stage: Stage) -> Segment:
        """The last segment with this stage (for PLAY and DEMO there's only one)."""
        return [s for s in self.segments if s.stage is stage][-1]

    def stage_at(self, sample: float) -> tuple[Stage, float]:
        """(stage, fractional step into that stage) for an absolute sample."""
        for seg in self.segments:
            if sample < seg.end:
                return seg.stage, max(0.0, (sample - seg.start) / self.step_samples)
        return Stage.DONE, 0.0

    def clicks(self) -> list[Click]:
        beat = self.beat
        out = []
        for seg in self.segments:
            if seg.stage is not Stage.COUNT_IN:
                continue
            for b in range(beat.beats_per_bar):
                sample = seg.start + round(b * beat.steps_per_beat * self.step_samples)
                out.append(Click(sample, accent=b == 0))
        return out

    def note_sample(self, stage: Stage, step: int) -> int:
        return self.segment(stage).start + round(step * self.step_samples)

    def expected(self, sample_to_time) -> list[Expected]:
        """The notes to play in the PLAY segment, timed with `sample_to_time`."""
        return [
            Expected(sample_to_time(self.note_sample(Stage.PLAY, n.step)), n.drum, n.step)
            for n in self.beat.notes
        ]

    def schedule(self, mixer: Mixer, kit: dict, clicks: tuple[np.ndarray, np.ndarray]) -> None:
        """Queue the count-in clicks and the demo; the PLAY segment stays silent."""
        accent_click, click = clicks
        for c in self.clicks():
            mixer.schedule(c.sample, accent_click if c.accent else click)
        for n in self.beat.notes:
            mixer.schedule(
                self.note_sample(Stage.DEMO, n.step),
                kit[n.drum],
                gain=n.velocity / 127,
                group=n.drum,
                chokes=CHOKES.get(n.drum),
            )
