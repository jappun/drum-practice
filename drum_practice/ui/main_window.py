"""Main window: pick a beat, listen to it, then play it back and get graded."""

from enum import Enum, auto

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import calibration
from ..audio import AudioEngine
from ..grading import GOOD_WINDOW, Played, Result, Verdict, grade
from ..midi_in import Hit, MidiInput
from ..model import load_beats
from ..player import BeatPlayer
from ..session import Stage, Timeline
from ..settings import Settings
from ..sounds import build_clicks, build_kit
from . import theme
from .grid import BeatGrid, GridResults
from .monitor import MonitorWindow

FRAME_MS = 16
START_LEAD_SECONDS = 0.3  # pause between pressing Start and the first click
FINISH_GRACE_SECONDS = 0.15  # keep listening this long after the last bar for late hits


class Mode(Enum):
    IDLE = auto()
    LISTEN = auto()
    PRACTICE = auto()
    CALIBRATE = auto()


class _HitBridge(QObject):
    """Moves MIDI hits from rtmidi's thread onto the Qt main thread."""

    hit = Signal(object)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drum Practice")
        self.resize(1180, 640)

        self._settings = Settings.load()
        self._engine = AudioEngine()
        self._kit = build_kit(self._engine.sample_rate)
        self._clicks = build_clicks(self._engine.sample_rate)
        self._player = BeatPlayer(self._engine, self._kit)
        self._engine.start()
        self._beats = load_beats()
        self._monitor: MonitorWindow | None = None

        self._mode = Mode.IDLE
        self._timeline: Timeline | None = None
        self._calibration_clicks: list[int] = []
        self._hits: list[Hit] = []

        self._bridge = _HitBridge()
        self._bridge.hit.connect(self._on_hit)
        self._midi = MidiInput(on_hit=self._bridge.hit.emit)

        self._build_ui()
        self._select_beat(0)

        self._frame = QTimer(self, interval=FRAME_MS)
        self._frame.timeout.connect(self._tick)
        self._frame.start()
        self._poll = QTimer(self, interval=1000)
        self._poll.timeout.connect(self._poll_kit)
        self._poll.start()
        self._poll_kit()

    # --- layout ---

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Drum Practice")
        title.setObjectName("title")
        self._kit_status = QLabel()
        self._kit_status.setObjectName("status")
        self._calibrate = QPushButton("Calibrate")
        self._calibrate.clicked.connect(self._toggle_calibration)
        monitor = QPushButton("Kit monitor")
        monitor.clicked.connect(self._open_monitor)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._kit_status)
        header.addWidget(self._calibrate)
        header.addWidget(monitor)
        root.addLayout(header)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self._picker = QComboBox()
        for beat in self._beats:
            self._picker.addItem(beat.name)
        self._picker.currentIndexChanged.connect(self._select_beat)
        self._listen = QPushButton("Listen")
        self._listen.clicked.connect(self._toggle_listen)
        self._start = QPushButton("Start practice")
        self._start.setObjectName("primary")
        self._start.clicked.connect(self._toggle_practice)
        self._meta = QLabel()
        self._meta.setObjectName("meta")
        # Fixed widths so buttons don't jump when their text flips to "Stop".
        self._listen.setFixedWidth(90)
        self._start.setFixedWidth(150)
        self._calibrate.setFixedWidth(100)
        controls.addWidget(self._picker)
        controls.addWidget(self._listen)
        controls.addWidget(self._start)
        controls.addWidget(self._meta)
        controls.addStretch()
        root.addLayout(controls)

        self._banner = QLabel()
        self._banner.setObjectName("banner")
        root.addWidget(self._banner)

        self._grid = BeatGrid()
        root.addWidget(self._grid)

        self._summary = QLabel()
        self._summary.setObjectName("summary")
        self._summary.setTextFormat(Qt.RichText)
        self._summary.setWordWrap(True)
        self._summary.setMinimumHeight(70)
        root.addWidget(self._summary)
        root.addStretch()

    # --- actions ---

    def _select_beat(self, index: int) -> None:
        self._stop_all()
        beat = self._beats[index]
        self._grid.set_beat(beat)
        self._meta.setText(f"{beat.genre} · {beat.difficulty} · {beat.bars} bars · {beat.tempo:g} BPM")
        self._show_idle_banner()

    def _toggle_listen(self) -> None:
        if self._mode is Mode.LISTEN:
            self._stop_all()
            return
        self._stop_all()
        self._grid.set_results(None)
        self._player.play(self._grid.beat)
        self._set_mode(Mode.LISTEN)
        self._banner.setText("Listening — press Stop when you're ready to practise")

    def _toggle_practice(self) -> None:
        if self._mode is Mode.PRACTICE:
            self._stop_all()
            return
        self._stop_all()
        self._grid.set_results(None)
        start = int(self._engine.mixer.position + START_LEAD_SECONDS * self._engine.sample_rate)
        self._timeline = Timeline(self._grid.beat, start, self._engine.sample_rate)
        self._timeline.schedule(self._engine.mixer, self._kit, self._clicks)
        self._hits = []
        self._set_mode(Mode.PRACTICE)

    def _toggle_calibration(self) -> None:
        if self._mode is Mode.CALIBRATE:
            self._stop_all()
            return
        self._stop_all()
        sr = self._engine.sample_rate
        start = int(self._engine.mixer.position + START_LEAD_SECONDS * sr)
        self._calibration_clicks = calibration.click_samples(start, sr)
        accent, click = self._clicks
        for i, sample in enumerate(self._calibration_clicks):
            self._engine.mixer.schedule(sample, accent if i % 4 == 0 else click)
        self._hits = []
        self._set_mode(Mode.CALIBRATE)

    def _stop_all(self) -> None:
        self._player.stop()
        self._engine.mixer.clear()
        self._timeline = None
        self._grid.set_step(None)
        if self._mode is not Mode.IDLE:
            self._set_mode(Mode.IDLE)
            self._show_idle_banner()

    def _set_mode(self, mode: Mode) -> None:
        self._mode = mode
        self._listen.setText("Stop" if mode is Mode.LISTEN else "Listen")
        self._start.setText("Stop" if mode is Mode.PRACTICE else "Start practice")
        self._calibrate.setText("Stop" if mode is Mode.CALIBRATE else "Calibrate")
        if mode is not Mode.IDLE:
            self._summary.setText("")

    def _show_idle_banner(self) -> None:
        if self._settings.calibrated:
            self._banner.setText("Press Start practice: count-in, listen, count-in, then your turn.")
        else:
            self._banner.setText("Tip: press Calibrate first so timing is graded accurately.")

    # --- per frame ---

    def _tick(self) -> None:
        if self._mode is Mode.LISTEN:
            self._player.pump()
            self._grid.set_step(self._player.current_step())
        elif self._mode is Mode.PRACTICE:
            self._tick_practice()
        elif self._mode is Mode.CALIBRATE:
            self._tick_calibration()

    def _tick_practice(self) -> None:
        tl = self._timeline
        now = self._engine.position_samples()
        stage, step = tl.stage_at(now)
        beat = tl.beat
        if stage is Stage.COUNT_IN:
            self._grid.set_step(None)
            count = int(step // beat.steps_per_beat) + 1 if now >= tl.segments[0].start else ""
            self._banner.setText(f"Count-in   {count}")
        elif stage is Stage.DEMO:
            self._grid.set_step(step)
            self._banner.setText("Listen…")
        elif stage is Stage.PLAY:
            self._grid.set_step(step)
            self._banner.setText("Your turn!")
        elif now > tl.end + FINISH_GRACE_SECONDS * self._engine.sample_rate:
            self._finish_practice()

    def _tick_calibration(self) -> None:
        now = self._engine.position_samples()
        sr = self._engine.sample_rate
        clicks = self._calibration_clicks
        heard = sum(1 for c in clicks if c <= now)
        if heard <= calibration.LEAD_IN_CLICKS:
            self._banner.setText(f"Calibrating: listen to the count-in… {heard or ''}")
        else:
            n = heard - calibration.LEAD_IN_CLICKS
            self._banner.setText(f"Hit any pad exactly on each click   {n} / {calibration.MEASURED_CLICKS}")
        beat = 60.0 / calibration.TEMPO * sr
        if now > clicks[-1] + beat / 2:
            self._finish_calibration()

    # --- results ---

    def _finish_practice(self) -> None:
        tl = self._timeline
        offset = self._settings.latency_offset
        to_perf = self._engine.sample_to_perf
        play = tl.segment(Stage.PLAY)
        play_start, play_end = to_perf(play.start), to_perf(play.end)
        played = [
            Played(h.time - offset, h.drum)
            for h in self._hits
            if h.drum is not None and play_start - GOOD_WINDOW <= h.time - offset <= play_end + GOOD_WINDOW
        ]
        result = grade(tl.expected(to_perf), played)

        step_s = tl.beat.step_seconds()
        def step_of(p: Played) -> float:
            return (p.time - play_start) / step_s

        self._grid.set_results(
            GridResults(
                notes={(n.expected.step, n.expected.drum): n for n in result.notes},
                extras=[(step_of(p), p.drum) for p in result.extras],
                ignored=[(step_of(p), p.drum) for p in result.ignored],
            )
        )
        self._stop_all()
        self._banner.setText(f"Score  {result.score:.0f}%")
        self._summary.setText(_summary_text(result))

    def _finish_calibration(self) -> None:
        clicks = [self._engine.sample_to_perf(s) for s in self._calibration_clicks[calibration.LEAD_IN_CLICKS:]]
        m = calibration.measure(clicks, [h.time for h in self._hits])
        self._stop_all()
        if not m.enough_taps:
            self._banner.setText("Calibration didn't get enough hits. Press Calibrate to try again.")
            return
        if not m.consistent:
            self._banner.setText(
                f"Your taps were too uneven to calibrate (scattered by ±{m.scatter * 1000:.0f} ms). "
                "Try again, hitting as steadily as you can."
            )
            return
        offset = m.offset
        self._settings.latency_offset = offset
        self._settings.calibrated = True
        self._settings.save()
        direction = "late" if offset >= 0 else "early"
        self._banner.setText(
            f"Calibrated: your hits arrive {abs(offset) * 1000:.0f} ms {direction}. That's now corrected for."
        )

    # --- MIDI ---

    def _on_hit(self, hit: Hit) -> None:
        if self._mode in (Mode.PRACTICE, Mode.CALIBRATE):
            self._hits.append(hit)

    def _poll_kit(self) -> None:
        if self._midi.poll_connection():
            self._kit_status.setText("● Kit connected")
            color = theme.OK
        else:
            self._kit_status.setText("● Kit not found — switch it on")
            color = theme.BAD
        self._kit_status.setStyleSheet(f"color: {color}; background: {theme.SURFACE};")

    def _open_monitor(self) -> None:
        if self._monitor is None:
            self._monitor = MonitorWindow()
        self._monitor.show()
        self._monitor.raise_()

    def closeEvent(self, event) -> None:
        self._frame.stop()
        self._poll.stop()
        self._stop_all()
        self._midi.close()
        self._engine.close()
        if self._monitor is not None:
            self._monitor.close()
        super().closeEvent(event)


def _summary_text(result: Result) -> str:
    good = [n for n in result.notes if n.verdict is Verdict.GOOD]
    early = sum(1 for n in good if n.early)
    parts = [
        f"<span style='color:{theme.OK}'>■</span> Perfect {result.count(Verdict.PERFECT)}",
        f"<span style='color:{theme.ACCENT}'>■</span> Good {len(good)} ({early} early, {len(good) - early} late)",
        f"<span style='color:{theme.BAD}'>□</span> Missed {result.count(Verdict.MISS)}",
        f"<span style='color:{theme.BAD}'>●</span> Extra hits {len(result.extras)}",
    ]
    if result.ignored:
        parts.append(f"<span style='color:{theme.TEXT_DIM}'>●</span> Pedal closes ignored {len(result.ignored)}")
    text = "&nbsp;&nbsp;·&nbsp;&nbsp;".join(parts)
    mean = result.mean_offset
    if mean is not None and abs(mean) >= 0.005:
        text += f"<br>On average you were {abs(mean) * 1000:.0f} ms {'early' if mean < 0 else 'late'}."
    text += f"<br><span style='color:{theme.TEXT_DIM}'>Good notes have a notch on the side you were off: left = early, right = late.</span>"
    return text
