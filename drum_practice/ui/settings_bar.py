"""Two rows of settings: practice (bars, count-in, click) and metronome (tempo, play)."""

from PySide6.QtCore import QRegularExpression, Qt, Signal
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..settings import Settings

MIN_TEMPO, MAX_TEMPO = 40, 200
MAX_BARS = 4  # wider grids need horizontal scrolling (later phase)
ROW_LABEL_WIDTH = 90
METRONOME_PLAY = "▶  Play"
METRONOME_STOP = "■  Stop"


class SettingsBar(QWidget):
    changed = Signal()  # any setting changed (already written to `settings`)
    metronome_toggled = Signal()

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        rows = QVBoxLayout(self)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(10)

        practice = _row(rows, "Practice:")
        practice.addWidget(_label("Bars"))
        self._bars = NumberField(1, MAX_BARS, settings.bars, width=44)
        self._bars.setToolTip(f"How many bars to practise (1–{MAX_BARS}); the pattern repeats to fill them")
        self._bars.valueChanged.connect(self._on_bars)
        practice.addWidget(self._bars)
        practice.addSpacing(24)
        self._count_in = QCheckBox("Count-in")
        self._count_in.setChecked(settings.count_in)
        self._count_in.toggled.connect(self._on_toggles)
        practice.addWidget(self._count_in)
        practice.addSpacing(24)
        self._click = QCheckBox("Click during your turn")
        self._click.setChecked(settings.metronome)
        self._click.toggled.connect(self._on_toggles)
        practice.addWidget(self._click)
        practice.addStretch()

        metronome = _row(rows, "Metronome:")
        metronome.addWidget(_label("Tempo"))
        self._tempo = QSlider(Qt.Horizontal)
        self._tempo.setRange(MIN_TEMPO, MAX_TEMPO)
        self._tempo.setFixedWidth(170)
        self._tempo.setValue(round(settings.tempo))
        self._tempo.valueChanged.connect(self._on_slider_moved)
        self._tempo.sliderReleased.connect(self._on_tempo_set)
        self._tempo_box = NumberField(MIN_TEMPO, MAX_TEMPO, round(settings.tempo), width=52)
        self._tempo_box.valueChanged.connect(self._on_box_set)
        metronome.addWidget(self._tempo)
        metronome.addWidget(self._tempo_box)
        metronome.addWidget(_label("BPM"))
        metronome.addSpacing(24)
        self.metronome_button = QPushButton(METRONOME_PLAY)
        self.metronome_button.setFixedWidth(90)
        self.metronome_button.setToolTip("A click at this tempo, no beat")
        self.metronome_button.clicked.connect(self.metronome_toggled.emit)
        metronome.addWidget(self.metronome_button)
        metronome.addStretch()

    def set_metronome_playing(self, playing: bool) -> None:
        self.metronome_button.setText(METRONOME_STOP if playing else METRONOME_PLAY)

    def _on_slider_moved(self, value: int) -> None:
        # Keep the box in step while dragging, but only apply on release
        # (or straight away for keyboard, wheel or typed changes).
        self._tempo_box.blockSignals(True)
        self._tempo_box.setValue(value)
        self._tempo_box.blockSignals(False)
        if not self._tempo.isSliderDown():
            self._on_tempo_set()

    def _on_box_set(self, value: int) -> None:
        self._tempo.setValue(value)  # moves the slider, which applies it

    def _on_tempo_set(self) -> None:
        value = float(self._tempo.value())
        if value != self.settings.tempo:
            self.settings.tempo = value
            self.changed.emit()

    def _on_bars(self, bars: int) -> None:
        if bars != self.settings.bars:
            self.settings.bars = bars
            self.changed.emit()

    def _on_toggles(self) -> None:
        self.settings.count_in = self._count_in.isChecked()
        self.settings.metronome = self._click.isChecked()
        self.changed.emit()


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


class NumberField(QLineEdit):
    """A plain typed whole number in [low, high]. Applies on Enter or when
    focus leaves; anything out of range snaps back to the last good value."""

    valueChanged = Signal(int)

    def __init__(self, low: int, high: int, value: int, width: int):
        super().__init__()
        self._low, self._high = low, high
        self._value = min(max(value, low), high)
        # Digits only; the range is checked on commit. (A range validator would
        # treat out-of-range numbers as "still typing" and swallow Enter.)
        self.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,3}"), self))
        self.setAlignment(Qt.AlignCenter)
        self.setFixedWidth(width)
        self.setText(str(self._value))
        self.editingFinished.connect(self._commit)

    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:
        """Set from code; emits valueChanged if it changed (like QSpinBox)."""
        value = min(max(value, self._low), self._high)
        self.setText(str(value))
        if value != self._value:
            self._value = value
            self.valueChanged.emit(value)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._commit()

    def _commit(self) -> None:
        text = self.text().strip()
        if text.isdigit() and self._low <= int(text) <= self._high:
            self.setValue(int(text))
        else:
            self.setText(str(self._value))
