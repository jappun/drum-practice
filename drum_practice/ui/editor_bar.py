"""Beat editor controls: details, rhythm (bars, time signature, grid), the
note-strength brush, and save/cancel/delete.

Shown in place of the practice settings while a beat is being edited."""

from dataclasses import replace

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..library import DIFFICULTIES
from ..model import ACCENT, GHOST, MAX_BEAT_BARS, NORMAL, Beat
from ..rhythm import (
    COMMON_TIME_SIGNATURES,
    SUBDIVISIONS,
    TimeSignature,
    subdivision_for,
    subdivision_named,
)
from .settings_bar import MAX_TEMPO, MIN_TEMPO, ROW_LABEL_WIDTH, NumberField

BRUSHES = (("Ghost", GHOST), ("Normal", NORMAL), ("Accent", ACCENT))


class EditorBar(QWidget):
    details_changed = Signal()  # name, genre, level or tempo
    bars_changed = Signal(int)
    time_signature_changed = Signal(object)  # TimeSignature
    grid_changed = Signal(int)  # columns per beat
    save_clicked = Signal()
    cancel_clicked = Signal()
    delete_clicked = Signal()

    def __init__(self):
        super().__init__()
        rows = QVBoxLayout(self)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(10)

        details = _row(rows, "Beat:")
        self._name = QLineEdit()
        self._name.setPlaceholderText("Name")
        self._name.setFixedWidth(200)
        self._genre = QComboBox()
        self._genre.setEditable(True)  # pick a genre or type a new one
        self._genre.setObjectName("filter")
        self._genre.setFixedWidth(140)
        self._level = QComboBox()
        self._level.setObjectName("filter")
        for d in DIFFICULTIES:
            self._level.addItem(d.capitalize(), d)
        self._tempo = NumberField(MIN_TEMPO, MAX_TEMPO, 90, width=52)
        for widget in (self._name, self._genre, self._level):
            details.addWidget(widget)
        details.addSpacing(10)
        details.addWidget(_label("Tempo"))
        details.addWidget(self._tempo)
        details.addWidget(_label("BPM"))
        details.addStretch()

        rhythm = _row(rows, "Rhythm:")
        rhythm.addWidget(_label("Bars"))
        self._bars = NumberField(1, MAX_BEAT_BARS, 2, width=44)
        rhythm.addWidget(self._bars)
        rhythm.addSpacing(18)
        rhythm.addWidget(_label("Time"))
        self._time = QComboBox()
        self._time.setEditable(True)  # pick a common one or type e.g. 7/8
        self._time.setObjectName("filter")
        self._time.setFixedWidth(80)
        self._time.addItems(COMMON_TIME_SIGNATURES)
        self._time.lineEdit().editingFinished.connect(self._on_time_typed)
        self._time.activated.connect(self._on_time_typed)
        rhythm.addWidget(self._time)
        rhythm.addSpacing(18)
        rhythm.addWidget(_label("Grid"))
        self._grid = QButtonGroup(self)
        self._grid_buttons: dict[str, QPushButton] = {}
        for sub in SUBDIVISIONS:
            button = QPushButton(sub.name)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setToolTip(f"Divide every beat into {sub.name}. Click a beat's number in the grid to change just that beat.")
            self._grid.addButton(button)
            self._grid_buttons[sub.name] = button
            rhythm.addWidget(button)
        self._grid.buttonClicked.connect(self._on_grid_clicked)
        rhythm.addStretch()
        self._ts = TimeSignature()

        notes = _row(rows, "Notes:")
        notes.addWidget(_label("Brush"))
        self._brush = QButtonGroup(self)
        for i, (label, velocity) in enumerate(BRUSHES):
            button = QPushButton(label)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setChecked(velocity == NORMAL)
            button.setFixedWidth(76)
            self._brush.addButton(button, velocity)
            notes.addWidget(button)
        notes.addStretch()
        self._delete = QPushButton("Delete")
        self._delete.setObjectName("danger")
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        save.setObjectName("primary")
        for button in (self._delete, cancel, save):
            button.setFixedWidth(90)
            notes.addWidget(button)

        self._name.textEdited.connect(self.details_changed)
        self._genre.currentTextChanged.connect(self.details_changed)
        self._level.currentIndexChanged.connect(self.details_changed)
        self._tempo.valueChanged.connect(self.details_changed)
        self._bars.valueChanged.connect(self.bars_changed)
        self._delete.clicked.connect(self.delete_clicked)
        cancel.clicked.connect(self.cancel_clicked)
        save.clicked.connect(self.save_clicked)

    @property
    def brush(self) -> int:
        """Velocity new notes get: ghost, normal or accent."""
        return self._brush.checkedId()

    def load(self, beat: Beat, genres: list[str], deletable: bool) -> None:
        """Show a beat's details without announcing them as changes."""
        widgets = (self._name, self._genre, self._level, self._tempo, self._bars, self._time)
        for w in widgets:
            w.blockSignals(True)
        self._name.setText(beat.name)
        self._genre.clear()
        self._genre.addItems(sorted(set(genres) | {beat.genre}))
        self._genre.setCurrentText(beat.genre)
        self._level.setCurrentIndex(max(0, self._level.findData(beat.difficulty)))
        self._tempo.setValue(round(beat.tempo))
        self._bars.setValue(beat.bars)
        self.show_rhythm(beat)
        for w in widgets:
            w.blockSignals(False)
        self._delete.setVisible(deletable)

    def show_rhythm(self, beat: Beat) -> None:
        """Reflect the beat's time signature and grid (options that don't fit
        the meter are disabled, e.g. 8th triplets in 6/8)."""
        self._ts = beat.time_signature
        self._time.blockSignals(True)
        self._time.setCurrentText(str(beat.time_signature))
        self._time.blockSignals(False)
        current = subdivision_for(beat.grid, beat.time_signature)
        self._grid.setExclusive(False)
        for sub in SUBDIVISIONS:
            button = self._grid_buttons[sub.name]
            button.setEnabled(sub.columns(beat.time_signature) is not None)
            button.setChecked(current is not None and sub.name == current.name)
        self._grid.setExclusive(True)

    def _on_time_typed(self, *_) -> None:
        try:
            ts = TimeSignature.parse(self._time.currentText().strip())
        except ValueError:
            self._time.setCurrentText(str(self._ts))  # not a time signature: put the old one back
            return
        if ts != self._ts:
            self._ts = ts
            self.time_signature_changed.emit(ts)

    def _on_grid_clicked(self, button: QPushButton) -> None:
        columns = subdivision_named(button.text()).columns(self._ts)
        if columns is not None:
            self.grid_changed.emit(columns)

    def apply_details(self, beat: Beat) -> Beat:
        """The beat with the name, genre, level and tempo from the fields."""
        return replace(
            beat,
            name=self._name.text().strip(),
            genre=self._genre.currentText().strip() or "Mine",
            difficulty=self._level.currentData(),
            tempo=float(self._tempo.value()),
        )


def _row(rows: QVBoxLayout, title: str) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(10)
    heading = QLabel(title)
    heading.setObjectName("rowTitle")
    heading.setFixedWidth(ROW_LABEL_WIDTH)
    row.addWidget(heading)
    rows.addLayout(row)
    return row


def _label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("meta")
    return label
