"""Main window: pick a beat, play it, watch the grid light up."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..audio import AudioEngine
from ..model import load_beats
from ..player import BeatPlayer
from ..sounds import build_kit
from .grid import BeatGrid
from .monitor import MonitorWindow

FRAME_MS = 16


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drum Practice")
        self.resize(1180, 520)

        self._engine = AudioEngine()
        self._player = BeatPlayer(self._engine, build_kit(self._engine.sample_rate))
        self._engine.start()
        self._beats = load_beats()
        self._monitor: MonitorWindow | None = None

        self._build_ui()
        self._select_beat(0)

        self._frame = QTimer(self, interval=FRAME_MS)
        self._frame.timeout.connect(self._tick)
        self._frame.start()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Drum Practice")
        title.setObjectName("title")
        monitor = QPushButton("Kit monitor")
        monitor.clicked.connect(self._open_monitor)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(monitor)
        root.addLayout(header)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self._picker = QComboBox()
        for beat in self._beats:
            self._picker.addItem(beat.name)
        self._picker.currentIndexChanged.connect(self._select_beat)
        self._play = QPushButton("Play")
        self._play.setObjectName("primary")
        self._play.clicked.connect(self._toggle_play)
        self._meta = QLabel()
        self._meta.setObjectName("meta")
        controls.addWidget(self._picker)
        controls.addWidget(self._play)
        controls.addWidget(self._meta)
        controls.addStretch()
        root.addLayout(controls)

        self._grid = BeatGrid()
        root.addWidget(self._grid)
        root.addStretch()

    def _select_beat(self, index: int) -> None:
        beat = self._beats[index]
        was_playing = self._player.playing
        self._player.stop()
        self._grid.set_beat(beat)
        self._meta.setText(
            f"{beat.genre} · {beat.difficulty} · {beat.bars} bars · {beat.tempo:g} BPM"
        )
        if was_playing:
            self._player.play(beat)
        self._update_play_button()

    def _toggle_play(self) -> None:
        if self._player.playing:
            self._player.stop()
        else:
            self._player.play(self._grid.beat)
        self._update_play_button()

    def _update_play_button(self) -> None:
        self._play.setText("Stop" if self._player.playing else "Play")

    def _tick(self) -> None:
        self._player.pump()
        self._grid.set_step(self._player.current_step())

    def _open_monitor(self) -> None:
        if self._monitor is None:
            self._monitor = MonitorWindow()
        self._monitor.show()
        self._monitor.raise_()

    def closeEvent(self, event) -> None:
        self._frame.stop()
        self._player.stop()
        self._engine.close()
        if self._monitor is not None:
            self._monitor.close()
        super().closeEvent(event)
