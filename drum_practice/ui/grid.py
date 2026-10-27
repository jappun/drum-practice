"""Step-grid view of a beat: one row per drum, one column per step."""

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..grading import NoteResult, Verdict
from ..kit import DRUM_ORDER, DrumClass
from ..model import Beat
from . import theme

LABEL_WIDTH = 130
KEY_LABEL_EXTRA = 56  # dev mode widens the label column to fit key hints
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
    # Edit mode only: a click on a cell, then cells dragged over on the same row.
    cell_pressed = Signal(int, object)  # step, DrumClass
    cell_dragged = Signal(int, object)

    def __init__(self, key_labels: dict[DrumClass, str] | None = None):
        """`key_labels` (dev mode only) shows each drum's keyboard key beside its name."""
        super().__init__()
        self._key_labels = key_labels
        self._label_width = LABEL_WIDTH + (KEY_LABEL_EXTRA if key_labels else 0)
        self.beat: Beat | None = None
        self.results: GridResults | None = None
        self._step: int | None = None
        self._editable = False
        self._hover: tuple[int, DrumClass] | None = None
        self._drag_row: DrumClass | None = None
        self._last_cell: tuple[int, DrumClass] | None = None
        self.setMinimumHeight(HEADER_HEIGHT + ROW_HEIGHT * len(DRUM_ORDER) + 2)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_beat(self, beat: Beat | None) -> None:
        self.beat = beat
        self.results = None
        self._step = None
        self.update()

    def set_editable(self, editable: bool) -> None:
        self._editable = editable
        self._hover = self._drag_row = self._last_cell = None
        self.setMouseTracking(editable)
        self.setCursor(Qt.PointingHandCursor if editable else Qt.ArrowCursor)
        self.update()

    def cell_at(self, x: float, y: float) -> tuple[int, DrumClass] | None:
        """The (step, drum) cell under a point, or None outside the cells."""
        if self.beat is None or x < self._label_width or y < HEADER_HEIGHT:
            return None
        step = int((x - self._label_width) / self._cell_width())
        row = int((y - HEADER_HEIGHT) / ROW_HEIGHT)
        if 0 <= step < self.beat.total_steps and 0 <= row < len(DRUM_ORDER):
            return step, DRUM_ORDER[row]
        return None

    def mousePressEvent(self, event) -> None:
        cell = self.cell_at(event.position().x(), event.position().y()) if self._editable else None
        if cell is None or event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        self._drag_row, self._last_cell = cell[1], cell
        self.cell_pressed.emit(*cell)

    def mouseMoveEvent(self, event) -> None:
        if not self._editable:
            return super().mouseMoveEvent(event)
        cell = self.cell_at(event.position().x(), event.position().y())
        if cell != self._hover:
            self._hover = cell
            self.update()
        # Dragging paints along the row the press started on.
        if self._drag_row is not None and cell and cell[1] is self._drag_row and cell != self._last_cell:
            self._last_cell = cell
            self.cell_dragged.emit(*cell)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_row = self._last_cell = None
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        if self._hover is not None:
            self._hover = None
            self.update()
        super().leaveEvent(event)

    def _cell_width(self) -> float:
        return (self.width() - self._label_width) / self.beat.total_steps

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
        cell_w = self._cell_width()
        used = {n.drum for n in beat.notes}

        # Beat shading, bar lines and beat numbers.
        number_font = QFont(self.font())
        number_font.setPixelSize(11)
        p.setFont(number_font)
        grid_bottom = HEADER_HEIGHT + ROW_HEIGHT * len(DRUM_ORDER)
        for step in range(steps):
            x = self._label_width + step * cell_w
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

        # Close off the last cell, so the final step doesn't fade into the background.
        end_x = int(self._label_width + steps * cell_w) - 1
        p.setPen(QPen(QColor(theme.BORDER), 1, Qt.DotLine))
        p.drawLine(end_x, HEADER_HEIGHT, end_x, grid_bottom)

        # Playhead column.
        if self._step is not None:
            x = self._label_width + self._step * cell_w
            head = QColor(theme.ACCENT)
            head.setAlphaF(0.18)
            p.fillRect(QRectF(x, HEADER_HEIGHT, cell_w, grid_bottom - HEADER_HEIGHT), head)

        # Row labels.
        p.setFont(self.font())
        for row, drum in enumerate(DRUM_ORDER):
            y = HEADER_HEIGHT + row * ROW_HEIGHT
            p.setPen(QColor(theme.TEXT if drum in used else theme.TEXT_DIM))
            rect = QRectF(8, y, self._label_width - 12, ROW_HEIGHT)
            p.drawText(rect, Qt.AlignVCenter, drum.label)
            if self._key_labels:
                p.setPen(QColor(theme.ACCENT_TEXT))
                p.drawText(rect, Qt.AlignVCenter | Qt.AlignRight, self._key_labels[drum])

        # Notes; the ones under the playhead light up.
        for note in beat.notes:
            row = DRUM_ORDER.index(note.drum)
            rect = QRectF(
                self._label_width + note.step * cell_w + CELL_GAP / 2,
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

        if self._editable and self._hover is not None:
            step, drum = self._hover
            p.setPen(QPen(QColor(theme.ACCENT), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(
                QRectF(
                    self._label_width + step * cell_w + CELL_GAP / 2,
                    HEADER_HEIGHT + DRUM_ORDER.index(drum) * ROW_HEIGHT + CELL_GAP,
                    cell_w - CELL_GAP,
                    ROW_HEIGHT - 2 * CELL_GAP,
                ),
                5,
                5,
            )

        if self.results:
            for marks, color in ((self.results.ignored, theme.TEXT_DIM), (self.results.extras, theme.BAD)):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(color))
                for step, drum in marks:
                    x = self._label_width + (min(max(step, -0.5), steps - 0.5) + 0.5) * cell_w
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
