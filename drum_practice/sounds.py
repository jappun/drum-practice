"""Drum and click sounds synthesised with numpy, so there are no sample licences."""

import numpy as np

from .kit import DrumClass

_rng = np.random.default_rng(7)


def _env(n: int, sr: int, decay: float) -> np.ndarray:
    return np.exp(-np.arange(n) / (decay * sr))


def _noise(n: int) -> np.ndarray:
    return _rng.uniform(-1, 1, n)


def _highpass(x: np.ndarray, amount: int = 1) -> np.ndarray:
    for _ in range(amount):
        x = np.diff(x, prepend=0.0)
    return x / (np.max(np.abs(x)) or 1)


def _sweep(sr: int, length: float, f_start: float, f_end: float, sweep: float) -> np.ndarray:
    t = np.arange(int(length * sr)) / sr
    freq = f_end + (f_start - f_end) * np.exp(-t / sweep)
    return np.sin(2 * np.pi * np.cumsum(freq) / sr)


def _kick(sr: int) -> np.ndarray:
    n = int(0.45 * sr)
    body = _sweep(sr, 0.45, 160, 48, 0.03) * _env(n, sr, 0.12)
    click = _highpass(_noise(n)) * _env(n, sr, 0.003) * 0.4
    return body + click


def _snare(sr: int) -> np.ndarray:
    n = int(0.3 * sr)
    tone = _sweep(sr, 0.3, 240, 180, 0.02) * _env(n, sr, 0.05) * 0.6
    rattle = _highpass(_noise(n)) * _env(n, sr, 0.08)
    return tone + rattle


def _tom(sr: int, pitch: float) -> np.ndarray:
    n = int(0.6 * sr)
    return _sweep(sr, 0.6, pitch * 1.6, pitch, 0.04) * _env(n, sr, 0.18)


def _metal(sr: int, length: float, decay: float, partials: list[float], noise_mix: float) -> np.ndarray:
    n = int(length * sr)
    t = np.arange(n) / sr
    tone = sum(np.sign(np.sin(2 * np.pi * f * t)) for f in partials) / len(partials)
    x = (1 - noise_mix) * tone + noise_mix * _noise(n)
    return _highpass(x, 2) * _env(n, sr, decay)


_HAT_PARTIALS = [317, 541, 783, 1031, 1373, 1709]


def _click(sr: int, freq: float) -> np.ndarray:
    n = int(0.05 * sr)
    t = np.arange(n) / sr
    return np.sin(2 * np.pi * freq * t) * _env(n, sr, 0.008)


def build_kit(sr: int) -> dict[DrumClass, np.ndarray]:
    sounds = {
        DrumClass.KICK: _kick(sr),
        DrumClass.SNARE: _snare(sr),
        DrumClass.HH_CLOSED: _metal(sr, 0.12, 0.025, _HAT_PARTIALS, 0.5) * 0.6,
        DrumClass.HH_OPEN: _metal(sr, 0.9, 0.3, _HAT_PARTIALS, 0.5) * 0.6,
        DrumClass.HH_PEDAL: _metal(sr, 0.08, 0.015, _HAT_PARTIALS, 0.3) * 0.45,
        DrumClass.TOM_HIGH: _tom(sr, 210),
        DrumClass.TOM_MID: _tom(sr, 160),
        DrumClass.TOM_LOW: _tom(sr, 110),
        DrumClass.CRASH: _metal(sr, 2.0, 0.6, [233, 397, 541, 709, 1091, 1427], 0.7) * 0.7,
        DrumClass.RIDE: _metal(sr, 1.5, 0.45, [431, 617, 1193, 1777], 0.25) * 0.4,
    }
    return {drum: s.astype(np.float32) for drum, s in sounds.items()}


def build_clicks(sr: int) -> tuple[np.ndarray, np.ndarray]:
    """(accent click for beat 1, normal click)."""
    return _click(sr, 1600).astype(np.float32), _click(sr, 1100).astype(np.float32)


# Hits on these drums cut off a ringing open hi-hat, like closing a real one.
CHOKES = {
    DrumClass.HH_CLOSED: DrumClass.HH_OPEN,
    DrumClass.HH_PEDAL: DrumClass.HH_OPEN,
}
