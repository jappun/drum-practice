"""Turns a Beat into scheduled sounds, looping until stopped."""

from .audio import AudioEngine
from .model import Beat, Note
from .sounds import CHOKES

START_LEAD_SECONDS = 0.15  # gap between pressing Play and the first note
LOOKAHEAD_SECONDS = 0.5  # how far ahead loops are scheduled


def step_sample(beat: Beat, start_sample: int, step: int, sample_rate: int) -> int:
    """Absolute sample for a step, counting from `start_sample`. Steps past the
    end of the beat continue into later loops, computed from the start each
    time so rounding never accumulates drift."""
    return start_sample + round(step * beat.step_seconds() * sample_rate)


def beat_events(beat: Beat, start_sample: int, sample_rate: int, loop: int = 0) -> list[tuple[int, Note]]:
    offset = loop * beat.total_steps
    return [
        (step_sample(beat, start_sample, offset + n.step, sample_rate), n)
        for n in beat.notes
    ]


class BeatPlayer:
    def __init__(self, engine: AudioEngine, sounds: dict):
        self._engine = engine
        self._sounds = sounds
        self.beat: Beat | None = None
        self._start = 0
        self._loops_scheduled = 0

    @property
    def playing(self) -> bool:
        return self.beat is not None

    def play(self, beat: Beat) -> None:
        self.stop()
        sr = self._engine.sample_rate
        self.beat = beat
        # Measured from the mixer's render position, which runs ahead of what's
        # audible by the output latency, so the first note is never already due.
        self._start = int(self._engine.mixer.position + START_LEAD_SECONDS * sr)
        self._loops_scheduled = 0
        self.pump()

    def stop(self) -> None:
        self.beat = None
        self._engine.mixer.clear()

    def pump(self) -> None:
        """Schedule further loops so there's always LOOKAHEAD_SECONDS queued.
        Call regularly (the UI does it every frame)."""
        if self.beat is None:
            return
        sr = self._engine.sample_rate
        horizon = self._engine.mixer.position + LOOKAHEAD_SECONDS * sr
        while self._loop_start(self._loops_scheduled) < horizon:
            for sample, note in beat_events(self.beat, self._start, sr, self._loops_scheduled):
                self._engine.mixer.schedule(
                    sample,
                    self._sounds[note.drum],
                    gain=note.velocity / 127,
                    group=note.drum,
                    chokes=CHOKES.get(note.drum),
                )
            self._loops_scheduled += 1

    def current_step(self) -> float | None:
        """Fractional step being heard now, within the beat; None before the first note."""
        if self.beat is None:
            return None
        sr = self._engine.sample_rate
        elapsed = (self._engine.position_samples() - self._start) / sr
        if elapsed < 0:
            return None
        return (elapsed / self.beat.step_seconds()) % self.beat.total_steps

    def _loop_start(self, loop: int) -> int:
        return step_sample(self.beat, self._start, loop * self.beat.total_steps, self._engine.sample_rate)


def click_sample(start_sample: int, tempo: float, index: int, sample_rate: int) -> int:
    """Absolute sample of the `index`th click, computed from the start (no drift)."""
    return start_sample + round(index * 60.0 / tempo * sample_rate)


class MetronomePlayer:
    """Clicks on every beat, accenting beat 1, until stopped."""

    def __init__(self, engine: AudioEngine, clicks, beats_per_bar: int = 4):
        self._engine = engine
        self._accent, self._click = clicks
        self.beats_per_bar = beats_per_bar
        self.tempo: float | None = None
        self._start = 0
        self._scheduled = 0

    @property
    def playing(self) -> bool:
        return self.tempo is not None

    def play(self, tempo: float) -> None:
        self.stop()
        self.tempo = tempo
        self._start = int(self._engine.mixer.position + START_LEAD_SECONDS * self._engine.sample_rate)
        self._scheduled = 0
        self.pump()

    def stop(self) -> None:
        self.tempo = None
        self._engine.mixer.clear()

    def pump(self) -> None:
        if self.tempo is None:
            return
        sr = self._engine.sample_rate
        horizon = self._engine.mixer.position + LOOKAHEAD_SECONDS * sr
        while (sample := click_sample(self._start, self.tempo, self._scheduled, sr)) < horizon:
            accent = self._scheduled % self.beats_per_bar == 0
            self._engine.mixer.schedule(sample, self._accent if accent else self._click)
            self._scheduled += 1

    def current_beat(self) -> int | None:
        """1-based beat in the bar being heard now; None before the first click."""
        if self.tempo is None:
            return None
        elapsed = (self._engine.position_samples() - self._start) / self._engine.sample_rate
        if elapsed < 0:
            return None
        return int(elapsed * self.tempo / 60.0) % self.beats_per_bar + 1
