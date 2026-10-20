"""Step-grid view of a beat: one row per drum, one column per step."""

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..kit import DRUM_ORDER
from ..model import Beat
from . import theme

LABEL_WIDTH = 130
ROW_HEIGHT = 34
HEADER_HEIGHT = 22
CELL_GAP = 3


class BeatGrid(QWidget):
    def __init__(self):
        super().__init__()
        self.beat: Beat | None = None
        self._step: int | None = None
        self.setMinimumHeight(HEADER_HEIGHT + ROW_HEIGHT * len(DRUM_ORDER) + 2)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_beat(self, beat: Beat | None) -> None:
        self.beat = beat
        self._step = None
        self.update()

    def set_step(self, step: float | None) -> None:
        """Move the playhead; `step` is fractional, None hides it."""
        whole = None if step is None else math.floor(step)
        if whole != self._step:
            self._step = whole
            self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(theme.BG))
        if self.beat is None:
            return

        beat = self.beat
        steps = beat.total_steps
        cell_w = (self.width() - LABEL_WIDTH) / steps
        used = {n.drum for n in beat.notes}

        # Beat shading, bar lines and beat numbers.
        number_font = QFont(self.font())
        number_font.setPixelSize(11)
        p.setFont(number_font)
        grid_bottom = HEADER_HEIGHT + ROW_HEIGHT * len(DRUM_ORDER)
        for step in range(steps):
            x = LABEL_WIDTH + step * cell_w
            beat_index = step // beat.steps_per_beat
            if beat_index % 2 == 0:
                p.fillRect(QRectF(x, HEADER_HEIGHT, cell_w, grid_bottom - HEADER_HEIGHT), QColor(theme.SURFACE))
            if step % beat.steps_per_beat:
                p.setPen(QPen(QColor(theme.BORDER), 1, Qt.DotLine))
                p.drawLine(int(x), HEADER_HEIGHT, int(x), grid_bottom)
            if step % beat.steps_per_beat == 0:
                p.setPen(QColor(theme.TEXT_DIM))
                label = str(beat_index % beat.beats_per_bar + 1)
                p.drawText(QRectF(x + 4, 0, cell_w * 2, HEADER_HEIGHT), Qt.AlignVCenter, label)
            if step % beat.steps_per_bar == 0 and step:
                p.setPen(QPen(QColor(theme.TEXT_DIM), 2))
                p.drawLine(int(x), HEADER_HEIGHT, int(x), grid_bottom)

        # Playhead column.
        if self._step is not None:
            x = LABEL_WIDTH + self._step * cell_w
            head = QColor(theme.ACCENT)
            head.setAlphaF(0.18)
            p.fillRect(QRectF(x, HEADER_HEIGHT, cell_w, grid_bottom - HEADER_HEIGHT), head)

        # Row labels.
        p.setFont(self.font())
        for row, drum in enumerate(DRUM_ORDER):
            y = HEADER_HEIGHT + row * ROW_HEIGHT
            p.setPen(QColor(theme.TEXT if drum in used else theme.TEXT_DIM))
            p.drawText(QRectF(8, y, LABEL_WIDTH - 12, ROW_HEIGHT), Qt.AlignVCenter, drum.label)

        # Notes; the ones under the playhead light up.
        for note in beat.notes:
            row = DRUM_ORDER.index(note.drum)
            rect = QRectF(
                LABEL_WIDTH + note.step * cell_w + CELL_GAP / 2,
                HEADER_HEIGHT + row * ROW_HEIGHT + CELL_GAP,
                cell_w - CELL_GAP,
                ROW_HEIGHT - 2 * CELL_GAP,
            )
            lit = note.step == self._step
            color = QColor(theme.LIT if lit else theme.ACCENT)
            color.setAlphaF(1.0 if lit else 0.35 + 0.55 * note.velocity / 127)
            p.setPen(QPen(QColor(theme.LIT), 2) if lit else Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(rect, 5, 5)
