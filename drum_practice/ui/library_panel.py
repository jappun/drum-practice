"""Left-hand library: filter by genre and difficulty, pick a beat or get a random one."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..library import DIFFICULTIES, ScoreBook, filter_beats, genres, surprise
from ..model import Beat

PANEL_WIDTH = 280


class LibraryPanel(QWidget):
    beat_selected = Signal(object)  # Beat

    def __init__(self, beats: list[Beat], scores: ScoreBook):
        super().__init__()
        self._beats = beats
        self._scores = scores
        self._current_id: str | None = None
        self.setFixedWidth(PANEL_WIDTH)

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)

        title = QLabel("Library")
        title.setObjectName("sectionHeading")
        col.addWidget(title)

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
            item = QListWidgetItem()
            item.setData(Qt.UserRole, beat.id)
            row = _BeatRow(beat, self._scores)
            item.setSizeHint(row.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
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


class _BeatRow(QWidget):
    """Name and genre/level on the left, best score on the right."""

    def __init__(self, beat: Beat, scores: ScoreBook):
        super().__init__()
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 7, 10, 7)
        text = QVBoxLayout()
        text.setSpacing(1)
        name = QLabel(beat.name)
        name.setObjectName("beatName")
        meta = QLabel(f"{beat.genre} · {beat.difficulty}")
        meta.setObjectName("meta")
        text.addWidget(name)
        text.addWidget(meta)
        row.addLayout(text, 1)

        best = scores.best(beat.id)
        score = QLabel(f"{best.score:.0f}%" if best else "–")
        score.setObjectName("bestScore" if best else "meta")
        score.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if best:
            score.setToolTip(f"Best: {best.score:.1f}% at {best.tempo:.0f} BPM, {best.bars} bars")
        row.addWidget(score)
        for label in (name, meta, score):
            label.setStyleSheet("background: transparent;")
