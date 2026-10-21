"""Step-grid view of a beat: one row per drum, one column per step."""

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from dataclasses import dataclass, field

from ..grading import NoteResult, Verdict
from ..kit import DRUM_ORDER, DrumClass
from ..model import Beat
from . import theme

LABEL_WIDTH = 130
ROW_HEIGHT = 34
HEADER_HEIGHT = 22
CELL_GAP = 3
MARK_RADIUS = 4.5


@dataclass
class GridResults:
    """What the grid needs to draw a graded run."""

    notes: dict[tuple[int, DrumClass], NoteResult]
    extras: list[tuple[float, DrumClass]] = field(default_factory=list)  # (fractional step, drum)
    ignored: list[tuple[float, DrumClass]] = field(default_factory=list)


class BeatGrid(QWidget):
    def __init__(self):
        super().__init__()
        self.beat: Beat | None = None
        self.results: GridResults | None = None
        self._step: int | None = None
        self.setMinimumHeight(HEADER_HEIGHT + ROW_HEIGHT * len(DRUM_ORDER) + 2)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_beat(self, beat: Beat | None) -> None:
        self.beat = beat
        self.results = None
        self._step = None
        self.update()

    def set_results(self, results: GridResults | None) -> None:
        self.results = results
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
            graded = self.results.notes.get((note.step, note.drum)) if self.results else None
            if graded is not None:
                self._paint_graded(p, rect, graded)
                continue
            lit = note.step == self._step
            color = QColor(theme.LIT if lit else theme.ACCENT)
            color.setAlphaF(1.0 if lit else 0.35 + 0.55 * note.velocity / 127)
            p.setPen(QPen(QColor(theme.LIT), 2) if lit else Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(rect, 5, 5)

        if self.results:
            for marks, color in ((self.results.ignored, theme.TEXT_DIM), (self.results.extras, theme.BAD)):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(color))
                for step, drum in marks:
                    x = LABEL_WIDTH + (min(max(step, -0.5), steps - 0.5) + 0.5) * cell_w
                    y = HEADER_HEIGHT + (DRUM_ORDER.index(drum) + 0.5) * ROW_HEIGHT
                    p.drawEllipse(QRectF(x - MARK_RADIUS, y - MARK_RADIUS, 2 * MARK_RADIUS, 2 * MARK_RADIUS))

    def _paint_graded(self, p: QPainter, rect: QRectF, graded: NoteResult) -> None:
        if graded.verdict is Verdict.MISS:
            p.setPen(QPen(QColor(theme.BAD), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 5, 5)
            return
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.OK if graded.verdict is Verdict.PERFECT else theme.ACCENT))
        p.drawRoundedRect(rect, 5, 5)
        if graded.verdict is Verdict.GOOD:
            # A notch on the side you were off towards: left = early, right = late.
            notch_w = max(3.0, rect.width() * 0.22)
            notch = QRectF(rect.left(), rect.top(), notch_w, rect.height())
            if not graded.early:
                notch.moveRight(rect.right())
            p.setBrush(QColor(theme.BG))
            p.drawRect(notch.adjusted(0, 4, 0, -4))
