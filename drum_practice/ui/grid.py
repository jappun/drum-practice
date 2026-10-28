"""Grid view of a beat: one row per drum, time running left to right.

Every beat gets the same width, split into its own number of columns (16ths,
triplets, 32nds…), so the picture stays true to time even when beats are
divided differently."""

from dataclasses import dataclass, field
from fractions import Fraction

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..grading import NoteResult, Verdict
from ..kit import DRUM_ORDER, DrumClass
from ..model import Beat
from ..rhythm import subdivision_for
from . import theme

LABEL_WIDTH = 130
KEY_LABEL_EXTRA = 56  # dev mode widens the label column to fit key hints
ROW_HEIGHT = 34
HEADER_HEIGHT = 22
CELL_GAP = 3
MAX_GAP_SHARE = 0.25  # narrow cells (e.g. 32nds) shrink their gap so notes stay visible
MARK_RADIUS = 4.5


@dataclass
class GridResults:
    """What the grid needs to draw a graded run."""

    notes: dict[tuple[Fraction, DrumClass], NoteResult]
    extras: list[tuple[float, DrumClass]] = field(default_factory=list)  # (quarters, drum)
    ignored: list[tuple[float, DrumClass]] = field(default_factory=list)


class BeatGrid(QWidget):
    # Edit mode only: a click on a cell, then cells dragged over on the same row.
    cell_pressed = Signal(object, object)  # position (Fraction quarters), DrumClass
    cell_dragged = Signal(object, object)
    # Edit mode only: a click on a beat's number, to change how it's divided.
    beat_header_clicked = Signal(int, QPoint)  # beat index, global position for a menu

    def __init__(self, key_labels: dict[DrumClass, str] | None = None):
        """`key_labels` (dev mode only) shows each drum's keyboard key beside its name."""
        super().__init__()
        self._key_labels = key_labels
        self._label_width = LABEL_WIDTH + (KEY_LABEL_EXTRA if key_labels else 0)
        self.beat: Beat | None = None
        self.results: GridResults | None = None
        self._position: float | None = None  # playhead, in quarters
        self._playing_cell: tuple[int, int] | None = None  # (beat, column) under the playhead
        self._editable = False
        self._hover: tuple[Fraction, DrumClass] | None = None
        self._drag_row: DrumClass | None = None
        self._last_cell: tuple[Fraction, DrumClass] | None = None
        self._checks: set[tuple[int, DrumClass | None]] = set()
        self.setMinimumHeight(HEADER_HEIGHT + ROW_HEIGHT * len(DRUM_ORDER) + 2)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_beat(self, beat: Beat | None) -> None:
        self.beat = beat
        self.results = None
        self._position = self._playing_cell = None
        self.update()

    def set_results(self, results: GridResults | None) -> None:
        self.results = results
        self.update()

    def set_checks(self, checks: set[tuple[int, DrumClass | None]]) -> None:
        """Spots to check, outlined in yellow: (beat index, drum, or None for
        every drum in that beat). They stay put while the beat is edited."""
        self._checks = set(checks)
        self.update()

    def set_editable(self, editable: bool) -> None:
        self._editable = editable
        self._hover = self._drag_row = self._last_cell = None
        self.setMouseTracking(editable)
        self.setCursor(Qt.PointingHandCursor if editable else Qt.ArrowCursor)
        self.update()

    def set_position(self, quarters: float | None) -> None:
        """Move the playhead (quarters into the beat); None hides it."""
        self._position = quarters
        cell = None if quarters is None or self.beat is None else self._cell_index(quarters)
        if cell != self._playing_cell:
            self._playing_cell = cell
            self.update()

    # --- geometry: time <-> x ---

    def _area_width(self) -> float:
        return self.width() - self._label_width

    def x_of(self, quarters: float | Fraction) -> float:
        return self._label_width + float(quarters) / float(self.beat.total_quarters) * self._area_width()

    def _quarters_at(self, x: float) -> float:
        return (x - self._label_width) / self._area_width() * float(self.beat.total_quarters)

    def _cell_index(self, quarters: float) -> tuple[int, int] | None:
        """(beat, column) containing a position, or None outside the beat."""
        beat = self.beat
        if not 0 <= quarters < beat.total_quarters:
            return None
        index = int(quarters // float(beat.beat_quarters))
        offset = quarters - float(index * beat.beat_quarters)
        column = int(offset / float(beat.column_length(index)))
        return index, min(column, beat.columns_in_beat(index) - 1)

    def _cell_start(self, index: int, column: int) -> Fraction:
        return index * self.beat.beat_quarters + column * self.beat.column_length(index)

    def _cell_rect(self, at: Fraction, drum: DrumClass) -> QRectF:
        beat = self.beat
        length = beat.column_length(beat.beat_index(at))
        left, right = self.x_of(at), self.x_of(at + length)
        gap = min(CELL_GAP, (right - left) * MAX_GAP_SHARE)
        return QRectF(
            left + gap / 2,
            HEADER_HEIGHT + DRUM_ORDER.index(drum) * ROW_HEIGHT + CELL_GAP,
            right - left - gap,
            ROW_HEIGHT - 2 * CELL_GAP,
        )

    def cell_at(self, x: float, y: float) -> tuple[Fraction, DrumClass] | None:
        """The (position, drum) cell under a point, or None outside the cells."""
        if self.beat is None or x < self._label_width or y < HEADER_HEIGHT:
            return None
        row = int((y - HEADER_HEIGHT) / ROW_HEIGHT)
        cell = self._cell_index(self._quarters_at(x))
        if cell is None or not 0 <= row < len(DRUM_ORDER):
            return None
        return self._cell_start(*cell), DRUM_ORDER[row]

    def beat_at_header(self, x: float, y: float) -> int | None:
        if self.beat is None or y >= HEADER_HEIGHT or x < self._label_width:
            return None
        cell = self._cell_index(self._quarters_at(x))
        return None if cell is None else cell[0]

    # --- mouse (edit mode) ---

    def mousePressEvent(self, event) -> None:
        if not self._editable or event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        x, y = event.position().x(), event.position().y()
        header_beat = self.beat_at_header(x, y)
        if header_beat is not None:
            self.beat_header_clicked.emit(header_beat, event.globalPosition().toPoint())
            return
        cell = self.cell_at(x, y)
        if cell is None:
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

    # --- drawing ---

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(theme.BG))
        if self.beat is None:
            return

        beat = self.beat
        used = {n.drum for n in beat.notes}
        grid_bottom = HEADER_HEIGHT + ROW_HEIGHT * len(DRUM_ORDER)
        height = grid_bottom - HEADER_HEIGHT
        number_font = QFont(self.font())
        number_font.setPixelSize(11)
        p.setFont(number_font)

        # Beat shading, column lines, beat numbers and bar lines.
        for index in range(beat.total_beats):
            start = index * beat.beat_quarters
            left, right = self.x_of(start), self.x_of(start + beat.beat_quarters)
            if index % 2 == 0:
                p.fillRect(QRectF(left, HEADER_HEIGHT, right - left, height), QColor(theme.SURFACE))
            columns = beat.columns_in_beat(index)
            p.setPen(QPen(QColor(theme.BORDER), 1, Qt.DotLine))
            for column in range(1, columns):
                x = int(self.x_of(start + column * beat.column_length(index)))
                p.drawLine(x, HEADER_HEIGHT, x, grid_bottom)
            # Beat number, plus the subdivision when it isn't the beat's default.
            p.setPen(QColor(theme.TEXT_DIM))
            label = str(index % beat.beats_per_bar + 1)
            if columns != beat.grid:
                sub = subdivision_for(columns, beat.time_signature)
                label += f"  ({sub.name if sub else f'{columns} per beat'})"
            p.drawText(QRectF(left + 4, 0, right - left - 4, HEADER_HEIGHT), Qt.AlignVCenter, label)
            if index % beat.beats_per_bar == 0 and index:
                p.setPen(QPen(QColor(theme.TEXT_DIM), 2))
                p.drawLine(int(left), HEADER_HEIGHT, int(left), grid_bottom)

        # Close off the last cell, so the final column doesn't fade into the background.
        end_x = int(self.x_of(beat.total_quarters)) - 1
        p.setPen(QPen(QColor(theme.BORDER), 1, Qt.DotLine))
        p.drawLine(end_x, HEADER_HEIGHT, end_x, grid_bottom)

        # Playhead column.
        if self._playing_cell is not None:
            index, column = self._playing_cell
            start = self._cell_start(index, column)
            left, right = self.x_of(start), self.x_of(start + beat.column_length(index))
            head = QColor(theme.ACCENT)
            head.setAlphaF(0.18)
            p.fillRect(QRectF(left, HEADER_HEIGHT, right - left, height), head)

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
        playing_start = None if self._playing_cell is None else self._cell_start(*self._playing_cell)
        for note in beat.notes:
            rect = self._cell_rect(note.at, note.drum)
            graded = self.results.notes.get((note.at, note.drum)) if self.results else None
            if graded is not None:
                self._paint_graded(p, rect, graded)
                continue
            lit = playing_start is not None and self._note_is_lit(note.at, playing_start)
            color = QColor(theme.LIT if lit else theme.ACCENT)
            color.setAlphaF(1.0 if lit else 0.35 + 0.55 * note.velocity / 127)
            p.setPen(QPen(QColor(theme.LIT), 2) if lit else Qt.NoPen)
            p.setBrush(color)
            radius = min(5.0, rect.width() / 3)
            p.drawRoundedRect(rect, radius, radius)

        self._paint_checks(p)

        if self._editable and self._hover is not None:
            p.setPen(QPen(QColor(theme.ACCENT), 1.5))
            p.setBrush(Qt.NoBrush)
            rect = self._cell_rect(*self._hover)
            radius = min(5.0, rect.width() / 3)
            p.drawRoundedRect(rect, radius, radius)

        if self.results:
            total = float(beat.total_quarters)
            for marks, color in ((self.results.ignored, theme.TEXT_DIM), (self.results.extras, theme.BAD)):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(color))
                for quarters, drum in marks:
                    x = self.x_of(min(max(quarters, 0.0), total))
                    y = HEADER_HEIGHT + (DRUM_ORDER.index(drum) + 0.5) * ROW_HEIGHT
                    p.drawEllipse(QRectF(x - MARK_RADIUS, y - MARK_RADIUS, 2 * MARK_RADIUS, 2 * MARK_RADIUS))

    def _paint_checks(self, p: QPainter) -> None:
        """Outline the notes to check; where there are none (e.g. a note may be
        missing), outline that beat's row instead, dashed."""
        beat = self.beat
        p.setBrush(Qt.NoBrush)
        for index, drum in self._checks:
            if index >= beat.total_beats:
                continue
            notes = [n for n in beat.notes if beat.beat_index(n.at) == index and drum in (None, n.drum)]
            p.setPen(QPen(QColor(theme.CHECK), 2))
            for note in notes:
                rect = self._cell_rect(note.at, note.drum).adjusted(-1, -1, 1, 1)
                radius = min(5.0, rect.width() / 3)
                p.drawRoundedRect(rect, radius, radius)
            if notes:
                continue
            start = index * beat.beat_quarters
            left, right = self.x_of(start), self.x_of(start + beat.beat_quarters)
            rows = [DRUM_ORDER.index(drum)] if drum else list(range(len(DRUM_ORDER)))
            top = HEADER_HEIGHT + min(rows) * ROW_HEIGHT + CELL_GAP
            bottom = HEADER_HEIGHT + (max(rows) + 1) * ROW_HEIGHT - CELL_GAP
            p.setPen(QPen(QColor(theme.CHECK), 1.5, Qt.DashLine))
            p.drawRoundedRect(QRectF(left + 2, top, right - left - 4, bottom - top), 4, 4)

    def _note_is_lit(self, at: Fraction, playing_start: Fraction) -> bool:
        """A note lights while the playhead is in the column it starts in."""
        index = self.beat.beat_index(at)
        return playing_start <= at < playing_start + self.beat.column_length(index)

    def _paint_graded(self, p: QPainter, rect: QRectF, graded: NoteResult) -> None:
        radius = min(5.0, rect.width() / 3)
        if graded.verdict is Verdict.MISS:
            p.setPen(QPen(QColor(theme.BAD), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)
            return
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.OK if graded.verdict is Verdict.PERFECT else theme.ACCENT))
        p.drawRoundedRect(rect, radius, radius)
        if graded.verdict is Verdict.GOOD:
            # A notch on the side you were off towards: left = early, right = late.
            notch_w = max(2.0, rect.width() * 0.22)
            notch = QRectF(rect.left(), rect.top(), notch_w, rect.height())
            if not graded.early:
                notch.moveRight(rect.right())
            p.setBrush(QColor(theme.BG))
            p.drawRect(notch.adjusted(0, 4, 0, -4))
