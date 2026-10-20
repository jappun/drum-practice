"""MIDI input from the e-kit, with reconnect support.

Qt-free: the UI polls `poll_connection()` on a timer and receives hits via
the `on_hit` callback, which runs on rtmidi's thread.
"""

import time
from dataclasses import dataclass
from typing import Callable

import mido

from .kit import DrumClass, classify

DEFAULT_PORT = "DTX drums"


@dataclass(frozen=True)
class Hit:
    note: int
    velocity: int
    time: float  # time.perf_counter() seconds
    drum: DrumClass | None


@dataclass(frozen=True)
class RawMessage:
    """Any non-note message (e.g. hi-hat pedal CC), kept for discovery."""

    text: str
    time: float


def message_to_event(msg: mido.Message, now: float) -> Hit | RawMessage | None:
    """Turn a mido message into a Hit, a RawMessage, or None to ignore it."""
    if msg.type == "note_on" and msg.velocity > 0:
        return Hit(msg.note, msg.velocity, now, classify(msg.note))
    if msg.type in ("note_off", "note_on", "clock", "active_sensing"):
        return None
    return RawMessage(str(msg), now)


class MidiInput:
    def __init__(
        self,
        on_hit: Callable[[Hit], None],
        on_raw: Callable[[RawMessage], None] | None = None,
        port_name: str = DEFAULT_PORT,
    ):
        self._on_hit = on_hit
        self._on_raw = on_raw
        self._port_name = port_name
        self._port = None

    @property
    def connected(self) -> bool:
        return self._port is not None

    @property
    def port_name(self) -> str:
        return self._port_name

    def poll_connection(self) -> bool:
        """Open the port if it appeared, drop it if it vanished. Returns connected."""
        available = self._port_name in mido.get_input_names()
        if available and self._port is None:
            try:
                self._port = mido.open_input(self._port_name, callback=self._callback)
            except OSError:
                self._port = None
        elif not available and self._port is not None:
            self.close()
        return self.connected

    def close(self) -> None:
        if self._port is not None:
            try:
                self._port.close()
            finally:
                self._port = None

    def _callback(self, msg: mido.Message) -> None:
        event = message_to_event(msg, time.perf_counter())
        if isinstance(event, Hit):
            self._on_hit(event)
        elif isinstance(event, RawMessage) and self._on_raw:
            self._on_raw(event)
