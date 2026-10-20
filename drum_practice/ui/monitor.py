"""Phase 1 live hit monitor: port status, pad lights, hit log, note discovery."""

import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..kit import DRUM_ORDER, DrumClass
from ..midi_in import Hit, MidiInput, RawMessage
from . import theme

MAX_LOG_ROWS = 500
MAX_RAW_ROWS = 200
FLASH_MS = 180


class _MidiBridge(QObject):
    """Moves MIDI events from rtmidi's thread onto the Qt main thread."""

    hit = Signal(object)
    raw = Signal(object)


class PadTile(QFrame):
    def __init__(self, drum: DrumClass):
        super().__init__()
        self.drum = drum
        self.setMinimumWidth(96)
        self.setFixedHeight(92)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        self._name = QLabel(drum.label)
        self._name.setWordWrap(True)
        self._name.setAlignment(Qt.AlignCenter)
        self._detail = QLabel("–")
        self._detail.setAlignment(Qt.AlignCenter)
        for label in (self._name, self._detail):
            label.setStyleSheet("background: transparent;")
        layout.addWidget(self._name)
        layout.addWidget(self._detail)
        self._timer = QTimer(self, singleShot=True, interval=FLASH_MS)
        self._timer.timeout.connect(self._idle)
        self._idle()

    def flash(self, hit: Hit) -> None:
        # Brighter for harder hits, so velocity changes are visible at a glance.
        strength = 0.35 + 0.65 * hit.velocity / 127
        color = QColor(theme.ACCENT)
        color.setAlphaF(strength)
        self.setStyleSheet(
            f"PadTile {{ background: {color.name(QColor.HexArgb)};"
            f" border: 1px solid {theme.ACCENT}; border-radius: 10px; }}"
        )
        self._detail.setText(f"note {hit.note}\nvel {hit.velocity}")
        self._timer.start()

    def _idle(self) -> None:
        self.setStyleSheet(
            f"PadTile {{ background: {theme.SURFACE};"
            f" border: 1px solid {theme.BORDER}; border-radius: 10px; }}"
        )


def _section(title: str) -> QLabel:
    label = QLabel(title.upper())
    label.setObjectName("sectionTitle")
    return label


def _table(headers: list[str], stretch_col: int) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.NoSelection)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeToContents)
    header.setSectionResizeMode(stretch_col, QHeaderView.Stretch)
    return table


class MonitorWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drum Practice — Kit Monitor")
        self.resize(1180, 720)

        self._start = time.perf_counter()
        # note -> [drum, count, min velocity, max velocity]
        self._seen: dict[int, list] = {}

        self._bridge = _MidiBridge()
        self._bridge.hit.connect(self._on_hit)
        self._bridge.raw.connect(self._on_raw)
        self._midi = MidiInput(on_hit=self._bridge.hit.emit, on_raw=self._bridge.raw.emit)

        self._build_ui()

        self._poll = QTimer(self, interval=1000)
        self._poll.timeout.connect(self._poll_connection)
        self._poll.start()
        self._poll_connection()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Kit Monitor")
        title.setObjectName("title")
        self._status = QLabel()
        self._status.setObjectName("status")
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._status)
        header.addWidget(clear)
        root.addLayout(header)

        root.addWidget(_section("Pads"))
        pads = QHBoxLayout()
        pads.setSpacing(8)
        self._tiles = {drum: PadTile(drum) for drum in DRUM_ORDER}
        for tile in self._tiles.values():
            pads.addWidget(tile)
        root.addLayout(pads)

        body = QHBoxLayout()
        body.setSpacing(12)

        log_col = QVBoxLayout()
        log_col.addWidget(_section("Hit log"))
        self._log = _table(["Time (s)", "Note", "Drum", "Velocity"], stretch_col=2)
        log_col.addWidget(self._log)
        body.addLayout(log_col, 3)

        seen_col = QVBoxLayout()
        seen_col.addWidget(_section("Notes seen"))
        self._seen_table = _table(["Note", "Drum", "Hits", "Min vel", "Max vel"], stretch_col=1)
        seen_col.addWidget(self._seen_table, 2)
        seen_col.addWidget(_section("Other messages (pedal position etc.)"))
        self._raw = QListWidget()
        seen_col.addWidget(self._raw, 1)
        body.addLayout(seen_col, 2)

        root.addLayout(body, 1)

    def _poll_connection(self) -> None:
        if self._midi.poll_connection():
            self._status.setText(f"● Connected: {self._midi.port_name}")
            color = theme.OK
        else:
            self._status.setText(f"● {self._midi.port_name} not found — is the kit switched on?")
            color = theme.BAD
        self._status.setStyleSheet(f"color: {color}; background: {theme.SURFACE};")

    def _on_hit(self, hit: Hit) -> None:
        if hit.drum is not None:
            self._tiles[hit.drum].flash(hit)
        drum_label = hit.drum.label if hit.drum else "UNMAPPED"

        self._log.insertRow(0)
        cells = [f"{hit.time - self._start:.3f}", str(hit.note), drum_label, str(hit.velocity)]
        for col, text in enumerate(cells):
            item = QTableWidgetItem(text)
            if hit.drum is None:
                item.setForeground(QColor(theme.BAD))
            self._log.setItem(0, col, item)
        if self._log.rowCount() > MAX_LOG_ROWS:
            self._log.removeRow(MAX_LOG_ROWS)

        entry = self._seen.setdefault(hit.note, [drum_label, 0, hit.velocity, hit.velocity])
        entry[1] += 1
        entry[2] = min(entry[2], hit.velocity)
        entry[3] = max(entry[3], hit.velocity)
        self._refresh_seen()

    def _refresh_seen(self) -> None:
        self._seen_table.setRowCount(len(self._seen))
        for row, (note, (drum, count, lo, hi)) in enumerate(sorted(self._seen.items())):
            for col, value in enumerate([note, drum, count, lo, hi]):
                self._seen_table.setItem(row, col, QTableWidgetItem(str(value)))

    def _on_raw(self, msg: RawMessage) -> None:
        self._raw.insertItem(0, f"{msg.time - self._start:8.3f}  {msg.text}")
        if self._raw.count() > MAX_RAW_ROWS:
            self._raw.takeItem(MAX_RAW_ROWS)

    def _clear(self) -> None:
        self._log.setRowCount(0)
        self._raw.clear()
        self._seen.clear()
        self._refresh_seen()

    def closeEvent(self, event) -> None:
        self._poll.stop()
        self._midi.close()
        super().closeEvent(event)
