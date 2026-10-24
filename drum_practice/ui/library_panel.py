"""Left-hand library: filter by genre and difficulty, pick a beat or get a random one.

Collapsible to a thin strip so the grid can use the full width."""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QAbstractButton,
    QApplication,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from ..library import DIFFICULTIES, ScoreBook, filter_beats, genres, surprise
from ..model import Beat
from . import theme

PANEL_WIDTH = 280
COLLAPSED_WIDTH = 36


class LibraryPanel(QWidget):
    beat_selected = Signal(object)  # Beat
    collapsed_changed = Signal(bool)

    def __init__(self, beats: list[Beat], scores: ScoreBook, collapsed: bool = False):
        super().__init__()
        self._beats = beats
        self._scores = scores
        self._current_id: str | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # The header (and its toggle) stays usable even while the body is locked.
        header = QHBoxLayout()
        self._title = QLabel("Library")
        self._title.setObjectName("sectionHeading")
        self._toggle = SidebarToggle()
        self._toggle.clicked.connect(lambda: self.set_collapsed(not self.collapsed))
        header.addWidget(self._title)
        header.addStretch()
        header.addWidget(self._toggle)
        outer.addLayout(header)

        self._body = QWidget()
        col = QVBoxLayout(self._body)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        outer.addWidget(self._body, 1)
        # Takes the body's place when collapsed, so the toggle stays at the top.
        self._filler = QWidget()
        self._filler.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        outer.addWidget(self._filler, 1)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self._genre = QComboBox()
        self._genre.addItem("All genres", None)
        for g in genres(beats):
            self._genre.addItem(g, g)
        self._difficulty = QComboBox()
        self._difficulty.addItem("All levels", None)
        for d in DIFFICULTIES:
            self._difficulty.addItem(d.capitalize(), d)
        for combo in (self._genre, self._difficulty):
            combo.setObjectName("filter")
            combo.currentIndexChanged.connect(self._refresh)
            filters.addWidget(combo)
        col.addLayout(filters)

        self._list = QListWidget()
        self._list.setObjectName("library")
        self._list.setUniformItemSizes(True)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setItemDelegate(_BeatRowDelegate(self._list))
        self._list.itemClicked.connect(self._on_item)
        col.addWidget(self._list, 1)

        self._empty = QLabel("No beats match these filters.")
        self._empty.setObjectName("meta")
        self._empty.setAlignment(Qt.AlignCenter)
        col.addWidget(self._empty)

        self._surprise = QPushButton("Surprise me")
        self._surprise.setToolTip("Pick a random beat that matches the filters")
        self._surprise.clicked.connect(self._on_surprise)
        col.addWidget(self._surprise)

        self._refresh()
        self._collapsed = not collapsed  # force set_collapsed to lay out
        self.set_collapsed(collapsed, announce=False)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool, announce: bool = True) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self._title.setVisible(not collapsed)
        self._body.setVisible(not collapsed)
        self._filler.setVisible(collapsed)
        self.setFixedWidth(COLLAPSED_WIDTH if collapsed else PANEL_WIDTH)
        self._toggle.set_pointing_left(not collapsed)
        self._toggle.setToolTip("Show library" if collapsed else "Hide library")
        if announce:
            self.collapsed_changed.emit(collapsed)

    def set_locked(self, locked: bool) -> None:
        """Stop beat changes (e.g. mid-run); collapsing still works."""
        self._body.setEnabled(not locked)

    def select(self, beat_id: str) -> None:
        """Highlight a beat and announce it (as if the user clicked it)."""
        beat = next(b for b in self._beats if b.id == beat_id)
        self._current_id = beat.id
        self._highlight()
        self.beat_selected.emit(beat)

    def refresh_scores(self) -> None:
        self._refresh()

    def _filters(self) -> tuple[str | None, str | None]:
        return self._genre.currentData(), self._difficulty.currentData()

    def _refresh(self) -> None:
        visible = filter_beats(self._beats, *self._filters())
        self._list.clear()
        for beat in visible:
            best = self._scores.best(beat.id)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, beat.id)
            item.setData(_NAME, beat.name)
            item.setData(_META, f"{beat.genre} · {beat.difficulty}")
            item.setData(_SCORE, f"{best.score:.0f}%" if best else "")
            if best:
                item.setToolTip(f"Best: {best.score:.1f}% at {best.tempo:.0f} BPM, {best.bars} bars")
            self._list.addItem(item)
        self._empty.setVisible(not visible)
        self._list.setVisible(bool(visible))
        self._surprise.setEnabled(bool(visible))
        self._highlight()

    def _highlight(self) -> None:
        # The current beat may be filtered out of view; then nothing is highlighted.
        self._list.clearSelection()
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.UserRole) == self._current_id:
                item.setSelected(True)
                self._list.scrollToItem(item)

    def _on_item(self, item: QListWidgetItem) -> None:
        self.select(item.data(Qt.UserRole))

    def _on_surprise(self) -> None:
        pick = surprise(self._beats, *self._filters(), exclude_id=self._current_id)
        if pick is not None:
            self.select(pick.id)


# Item data roles for the painted rows.
_NAME = Qt.UserRole + 1
_META = Qt.UserRole + 2
_SCORE = Qt.UserRole + 3  # "" when the beat has no best score yet


class _BeatRowDelegate(QStyledItemDelegate):
    """Paints each row (name and genre/level on the left, best score on the
    right) directly, which keeps a list of hundreds of beats instant."""

    ROW_HEIGHT = 48
    PAD = 10

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), self.ROW_HEIGHT)

    def paint(self, p: QPainter, option, index) -> None:
        # Background, hover and selection come from the stylesheet.
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        widget = opt.widget
        (widget.style() if widget else QApplication.style()).drawControl(
            QStyle.CE_ItemViewItem, opt, p, widget
        )

        rect = option.rect.adjusted(self.PAD, 6, -self.PAD, -6)
        score = index.data(_SCORE)
        p.save()
        score_font = QFont(option.font)
        score_font.setBold(True)
        p.setFont(score_font)
        p.setPen(QColor(theme.OK if score else theme.TEXT_DIM))
        score_text = score or "–"
        score_width = p.fontMetrics().horizontalAdvance(score_text)
        p.drawText(rect, Qt.AlignRight | Qt.AlignVCenter, score_text)

        text_rect = rect.adjusted(0, 0, -(score_width + 8), 0)
        name_font = QFont(option.font)
        name_font.setBold(True)
        p.setFont(name_font)
        p.setPen(QColor(theme.TEXT))
        top, bottom = text_rect.adjusted(0, 0, 0, -text_rect.height() // 2), text_rect.adjusted(0, text_rect.height() // 2, 0, 0)
        p.drawText(top, Qt.AlignLeft | Qt.AlignBottom, p.fontMetrics().elidedText(index.data(_NAME), Qt.ElideRight, top.width()))
        p.setFont(option.font)
        p.setPen(QColor(theme.TEXT_DIM))
        p.drawText(bottom, Qt.AlignLeft | Qt.AlignTop, index.data(_META))
        p.restore()


class SidebarToggle(QAbstractButton):
    """A drawn sidebar icon: rounded panel, divider, and a chevron pointing
    the way the sidebar will move (left = hide, right = show)."""

    SIZE = 28

    def __init__(self):
        super().__init__()
        self._left = True
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)

    def set_pointing_left(self, left: bool) -> None:
        self._left = left
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(theme.ACCENT if self.underMouse() else theme.TEXT_DIM)
        pen = QPen(color, 1.8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        frame = QRectF(4, 6, 20, 16)
        p.drawRoundedRect(frame, 4, 4)
        divider_x = frame.left() + 6
        p.drawLine(QPointF(divider_x, frame.top()), QPointF(divider_x, frame.bottom()))

        # Chevron centred in the area right of the divider.
        cx = (divider_x + frame.right()) / 2
        cy = frame.center().y()
        dx, dy = 2.2, 4.0
        tip, back = (cx - dx, cx + dx) if self._left else (cx + dx, cx - dx)
        chevron = QPainterPath(QPointF(back, cy - dy))
        chevron.lineTo(tip, cy)
        chevron.lineTo(back, cy + dy)
        p.drawPath(chevron)
