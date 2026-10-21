"""Latency calibration: tap along to clicks, measure how late hits arrive.

The offset covers everything between the sound and the recorded hit: output
latency the engine can't see (e.g. Bluetooth), USB-MIDI delay, and the
player's own habit of hitting slightly early or late.
"""

import statistics
from dataclasses import dataclass

LEAD_IN_CLICKS = 4  # heard but not measured, to settle into the pulse
MEASURED_CLICKS = 8
TEMPO = 90.0
MIN_MATCHED = 5
# Taps scattered more than this can't give a trustworthy offset. Measured as
# the median distance from the median, so one stray tap doesn't fail it.
MAX_SCATTER = 0.020


@dataclass(frozen=True)
class Measurement:
    offset: float  # median of (hit - click); positive = hits arrive late
    scatter: float  # median absolute deviation of (hit - click)
    matched: int  # clicks that got a hit

    @property
    def enough_taps(self) -> bool:
        return self.matched >= MIN_MATCHED

    @property
    def consistent(self) -> bool:
        return self.scatter <= MAX_SCATTER

    @property
    def usable(self) -> bool:
        return self.enough_taps and self.consistent


def click_samples(start: int, sample_rate: int) -> list[int]:
    interval = 60.0 / TEMPO * sample_rate
    return [start + round(i * interval) for i in range(LEAD_IN_CLICKS + MEASURED_CLICKS)]


def measure(click_times: list[float], hit_times: list[float]) -> Measurement:
    """Compare each click with the nearest hit within half a beat."""
    max_dev = 60.0 / TEMPO / 2
    deltas = []
    for click in click_times:
        near = [h - click for h in hit_times if abs(h - click) < max_dev]
        if near:
            deltas.append(min(near, key=abs))
    if not deltas:
        return Measurement(offset=0.0, scatter=0.0, matched=0)
    offset = statistics.median(deltas)
    scatter = statistics.median(abs(d - offset) for d in deltas)
    return Measurement(offset, scatter, len(deltas))
