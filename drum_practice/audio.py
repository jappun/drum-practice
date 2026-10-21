"""Sample-accurate audio output.

`Mixer` is pure numpy: sounds are scheduled at absolute sample positions and
`render()` produces the next block, so it can be tested offline. `AudioEngine`
drives a Mixer from a sounddevice output stream and reports which sample is
currently coming out of the speakers, for syncing the UI.
"""

import heapq
import itertools
import threading
import time
from collections import deque
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

CHOKE_FADE_SECONDS = 0.008
# The mixer runs in Python, so it needs generous buffers: with the device's
# tiny default (~64 frames) the callback misses its deadline whenever the UI
# holds the interpreter for a few ms, which drops audio. Notes are scheduled
# ahead and the UI corrects for output delay, so the extra latency is harmless.
BLOCK_FRAMES = 1024
OUTPUT_LATENCY = 0.1
CLOCK_WINDOW = 500  # callbacks (~10 s) used to estimate the clock offset
MASTER_GAIN = 0.5


@dataclass
class _Voice:
    start: int  # absolute sample of data[0]
    data: np.ndarray
    group: object


class Mixer:
    def __init__(self, sample_rate: int):
        self.sample_rate = sample_rate
        self.position = 0  # absolute sample of the next block
        self._pending: list = []  # heap of (sample, seq, data, group, chokes)
        self._seq = itertools.count()
        self._active: list[_Voice] = []
        self._lock = threading.Lock()
        self._fade = int(CHOKE_FADE_SECONDS * sample_rate)

    def schedule(self, sample: int, sound: np.ndarray, gain: float = 1.0, group=None, chokes=None) -> None:
        """Play `sound` starting at absolute `sample`. A sound with `chokes` set
        cuts off any ringing voice in that group when it starts."""
        with self._lock:
            heapq.heappush(self._pending, (sample, next(self._seq), sound * gain, group, chokes))

    def clear(self) -> None:
        """Drop everything scheduled and fade out whatever is ringing."""
        with self._lock:
            self._pending.clear()
            for voice in self._active:
                self._choke(voice, self.position)

    def render(self, frames: int) -> np.ndarray:
        out = np.zeros(frames, dtype=np.float32)
        end = self.position + frames
        with self._lock:
            while self._pending and self._pending[0][0] < end:
                sample, _, data, group, chokes = heapq.heappop(self._pending)
                # A sound scheduled too late still plays whole, just shifted, so
                # its attack is never cut off.
                sample = max(sample, self.position)
                if chokes is not None:
                    for voice in self._active:
                        if voice.group == chokes and voice.start < sample:
                            self._choke(voice, sample)
                self._active.append(_Voice(sample, data, group))

            still_active = []
            for voice in self._active:
                src_from = max(0, self.position - voice.start)
                dst_from = max(0, voice.start - self.position)
                count = min(len(voice.data) - src_from, frames - dst_from)
                if count > 0:
                    out[dst_from : dst_from + count] += voice.data[src_from : src_from + count]
                if voice.start + len(voice.data) > end:
                    still_active.append(voice)
            self._active = still_active
        self.position = end
        return np.tanh(out * MASTER_GAIN)

    def _choke(self, voice: _Voice, at_sample: int) -> None:
        cut = max(0, at_sample - voice.start)
        if cut >= len(voice.data):
            return
        tail = voice.data[cut : cut + self._fade].copy()
        tail *= np.linspace(1.0, 0.0, len(tail), dtype=np.float32)
        voice.data = np.concatenate([voice.data[:cut], tail])


class AudioEngine:
    def __init__(self):
        device = sd.query_devices(kind="output")
        self.sample_rate = int(device["default_samplerate"])
        self.mixer = Mixer(self.sample_rate)
        self._clock_lock = threading.Lock()
        self._block_start = 0  # absolute sample at the start of the last block
        self._block_dac_time = None  # stream time when that sample reaches the speakers
        # perf_counter minus stream time. On macOS both run off the same host
        # clock, so this is ~0; the minimum over recent callbacks filters out
        # the jitter of when Python got to read perf_counter.
        self._clock_offsets: deque[float] = deque(maxlen=CLOCK_WINDOW)
        self.underruns = 0  # blocks the callback didn't fill in time (audible glitches)
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=2,
            dtype="float32",
            blocksize=BLOCK_FRAMES,
            latency=OUTPUT_LATENCY,
            callback=self._callback,
        )

    def start(self) -> None:
        self._stream.start()

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()

    @property
    def running(self) -> bool:
        with self._clock_lock:
            return self._block_dac_time is not None

    def sample_to_perf(self, sample: float) -> float:
        """The time.perf_counter() moment when `sample` comes out of the speakers."""
        block_start, block_perf = self._clock()
        return block_perf + (sample - block_start) / self.sample_rate

    def perf_to_sample(self, perf_time: float) -> float:
        block_start, block_perf = self._clock()
        return block_start + (perf_time - block_perf) * self.sample_rate

    def _clock(self) -> tuple[int, float]:
        """(sample at the start of the last block, perf time it is heard)."""
        with self._clock_lock:
            if self._block_dac_time is None:
                raise RuntimeError("audio stream hasn't started yet")
            return self._block_start, self._block_dac_time + min(self._clock_offsets)

    def position_samples(self) -> float:
        """The absolute sample being heard right now (includes output latency)."""
        if not self.running:
            return 0.0
        return self.perf_to_sample(time.perf_counter())

    def _callback(self, outdata, frames, time_info, status) -> None:
        now = time.perf_counter()
        if status.output_underflow:
            self.underruns += 1
        block_start = self.mixer.position
        mono = self.mixer.render(frames)
        outdata[:, 0] = mono
        outdata[:, 1] = mono
        dac_time = time_info.outputBufferDacTime or time_info.currentTime
        with self._clock_lock:
            self._clock_offsets.append(now - time_info.currentTime)
            self._block_start = block_start
            self._block_dac_time = dac_time
