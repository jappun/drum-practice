"""Main window: pick a beat, listen to it, then play it back and get graded."""

import sys
import time
from pathlib import Path
from dataclasses import replace
from enum import Enum, auto

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QFileDialog,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import calibration, editing, keyboard_in
from ..audio import AudioEngine
from ..grading import GOOD_WINDOW, Played, Result, Verdict, grade
from ..kit import DrumClass
from ..midi_in import Hit, MidiInput
from ..library import ScoreBook, UserBeats, genres, is_example, is_user_beat, search_beats, visible_beats
from ..model import MAX_BEAT_BARS, Beat, load_beats
from ..player import BeatPlayer, MetronomePlayer
from ..rhythm import SUBDIVISIONS
from ..session import Stage, Timeline
from ..ai.transcription import describe_unsure, unsure_cells
from ..settings import DevSettings, Settings
from ..sounds import build_clicks, build_kit
from . import theme
from .editor_bar import EditorBar
from .ai_settings import AISettingsDialog
from .beat_views import GRID, NOTATION, BeatViews
from .grid import GridResults
from .library_panel import LibraryPanel
from .monitor import MonitorWindow
from .new_beat import PHOTO, NewBeatDialog
from .photo_import import GrooveChoiceDialog, PhotoImportDialog
from .photo_panel import PhotoPanel
from .settings_bar import SettingsBar

FRAME_MS = 16
WINDOW_MAX_WIDTH = 1280
WINDOW_MIN_HEIGHT = 640
WINDOW_SCREEN_SHARE = 0.85  # never more than this much of the screen
ABOUT_TEXT = """<p>Practise drum beats on an electronic kit and get graded on your timing.</p>
<p>Your library is made of your own beats, plus a few hand-made examples you can hide.</p>
<p>Music notation uses the <a href="https://github.com/steinbergmedia/bravura">Bravura</a> font,
© Steinberg Media Technologies, under the SIL Open Font License.</p>
<p>MIT licensed.</p>"""
START_LEAD_SECONDS = 0.3  # pause between pressing Start and the first click
FINISH_GRACE_SECONDS = 0.15  # keep listening this long after the last bar for late hits


class Mode(Enum):
    IDLE = auto()
    LISTEN = auto()
    PRACTICE = auto()
    CALIBRATE = auto()
    METRONOME = auto()


class _HitBridge(QObject):
    """Moves MIDI hits from rtmidi's thread onto the Qt main thread."""

    hit = Signal(object)


class VerticalScroll(QScrollArea):
    """Scrolls up and down only. It never gets narrower than its content, so
    nothing is cut off at the side."""

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        if self.widget() is not None:
            hint.setWidth(self.widget().minimumSizeHint().width() + self.verticalScrollBar().sizeHint().width())
        return hint

    def eventFilter(self, watched, event) -> bool:
        if watched is self.widget() and event.type() == QEvent.LayoutRequest:
            self.updateGeometry()  # content shown or hidden: recheck the minimum width
        return super().eventFilter(watched, event)


class MainWindow(QWidget):
    def __init__(self, dev_mode: bool = False):
        """`dev_mode` (only ever set by launching with --dev) lets the laptop
        keyboard play drums. It has its own calibration file and never
        changes anything for the regular app."""
        super().__init__()
        self._dev_mode = dev_mode
        self.setWindowTitle("Drum Practice — DEV (keyboard)" if dev_mode else "Drum Practice")

        self._settings = Settings.load()
        self._dev = DevSettings.load() if dev_mode else None
        self._engine = AudioEngine()
        self._kit = build_kit(self._engine.sample_rate)
        self._clicks = build_clicks(self._engine.sample_rate)
        self._player = BeatPlayer(self._engine, self._kit)
        self._metronome = MetronomePlayer(self._engine, self._clicks)
        self._engine.start()
        self._user_beats = UserBeats()
        self._scores = ScoreBook()
        self._scores.forget_prefix("gmd_")  # beats from the removed Groove MIDI library
        self._beats: list[Beat] = []
        self._hidden_count = 0
        self._load_library()
        # Editing: the beat being changed, and how it started (to spot unsaved changes).
        self._draft: Beat | None = None
        self._draft_start: Beat | None = None
        self._draft_photo: bytes | None = None  # reference photo shown while editing
        self._stroke = editing.Stroke.ADD  # what the current drag does
        self._base_beat: Beat | None = None  # as written; settings reshape it
        self._monitor: MonitorWindow | None = None

        self._mode = Mode.IDLE
        self._timeline: Timeline | None = None
        self._calibration_clicks: list[int] = []
        self._hits: list[Hit] = []

        self._bridge = _HitBridge()
        self._bridge.hit.connect(self._on_hit)
        self._midi = MidiInput(on_hit=self._bridge.hit.emit)

        self._build_ui()
        self._select_after_reload(self._settings.beat_id)

        self._frame = QTimer(self, interval=FRAME_MS)
        self._frame.timeout.connect(self._tick)
        self._frame.start()
        self._poll = QTimer(self, interval=1000)
        self._poll.timeout.connect(self._poll_kit)
        self._poll.start()
        self._poll_kit()

        # Start with nothing focused, and drop focus from a text box when the
        # user clicks anywhere else. On macOS buttons never take focus, so
        # without this the tempo box keeps a blinking cursor after any click.
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()
        QApplication.instance().installEventFilter(self)
        self._place_on_screen()

    def _place_on_screen(self) -> None:
        """A comfortable window, not full screen, centred on the screen. It's
        tall enough for the practice view; the grid and the editor make it
        grow (Qt keeps the window at least as big as its contents need)."""
        area = self.screen().availableGeometry()
        width = min(WINDOW_MAX_WIDTH, int(area.width() * WINDOW_SCREEN_SHARE))
        height = min(int(area.height() * WINDOW_SCREEN_SHARE), max(self.sizeHint().height(), WINDOW_MIN_HEIGHT))
        self.resize(width, height)
        frame = self.frameGeometry()
        frame.moveCenter(area.center())
        self.move(frame.topLeft())

    def eventFilter(self, obj, event) -> bool:
        if self._dev_mode and event.type() == QEvent.KeyPress:
            return self._dev_key_press(event)
        if event.type() == QEvent.MouseButtonPress:
            focused = QApplication.focusWidget()
            clicked = obj if isinstance(obj, QWidget) else None
            if (
                isinstance(focused, QLineEdit)
                and clicked is not None
                and clicked is not focused
                and not focused.isAncestorOf(clicked)
            ):
                self.setFocus()  # the box commits its typed value as it loses focus
        return False

    def _dev_key_press(self, event) -> bool:
        """Dev mode: a mapped key becomes a drum hit. Returns True to consume
        the key, so one press is one hit even though the app-wide filter sees
        the event again as it travels to the focused widget."""
        if event.isAutoRepeat() or isinstance(QApplication.focusWidget(), QLineEdit):
            return False  # held keys and typing into number fields aren't drums
        drum = keyboard_in.drum_for_key(event.text())
        if drum is None:
            return False
        self._on_hit(Hit(keyboard_in.note_for(drum), 100, time.perf_counter(), drum))
        return True

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
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._kit_status)
        root.addLayout(header)
        self._build_menus(root)

        body = QHBoxLayout()
        body.setSpacing(24)
        root.addLayout(body, 1)
        self._library = LibraryPanel(
            self._beats,
            self._scores,
            collapsed=True,  # the app opens with the library tucked away, so the beat gets the width
            hidden_examples=self._hidden_count,
        )
        self._library.restore_examples_requested.connect(self._restore_examples)
        self._library.beat_selected.connect(self._select_beat)
        self._library.new_beat_requested.connect(self._new_beat)
        body.addWidget(self._library)
        # The beat column scrolls up and down, so the editor stays reachable on
        # short screens (the photo, notation and grid together are tall).
        content = QWidget()
        main = QVBoxLayout(content)
        main.setContentsMargins(0, 0, 10, 0)  # room for the scroll bar
        main.setSpacing(14)
        self._scroll = VerticalScroll()
        self._scroll.setWidget(content)
        body.addWidget(self._scroll, 1)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self._beat_name = QLabel()
        self._beat_name.setObjectName("sectionHeading")
        self._listen = QPushButton("Listen")
        self._listen.clicked.connect(self._toggle_listen)
        self._start = QPushButton("Start practice")
        self._start.setObjectName("primary")
        self._start.clicked.connect(self._toggle_practice)
        self._edit = QPushButton("Edit")
        self._edit.clicked.connect(self._edit_current)
        self._hide = QPushButton("Hide example")
        self._hide.setToolTip("Remove this example from your library (you can show it again)")
        self._hide.clicked.connect(self._hide_example)
        self._meta = QLabel()
        self._meta.setObjectName("meta")
        # Fixed widths so buttons don't jump when their text flips to "Stop".
        self._listen.setFixedWidth(90)
        self._start.setFixedWidth(150)
        self._edit.setFixedWidth(150)
        controls.addWidget(self._listen)
        controls.addWidget(self._start)
        controls.addWidget(self._edit)
        controls.addWidget(self._hide)
        controls.addSpacing(12)
        controls.addWidget(self._beat_name)
        controls.addWidget(self._meta)
        controls.addStretch()
        main.addLayout(controls)

        self._settings_bar = SettingsBar(self._settings)
        self._settings_bar.changed.connect(self._on_settings_changed)
        self._settings_bar.metronome_toggled.connect(self._toggle_metronome)
        main.addWidget(self._settings_bar)

        self._editor_bar = EditorBar()
        self._editor_bar.details_changed.connect(self._on_draft_details)
        self._editor_bar.bars_changed.connect(self._on_draft_bars)
        self._editor_bar.time_signature_changed.connect(self._on_draft_time_signature)
        self._editor_bar.grid_changed.connect(self._on_draft_grid)
        self._editor_bar.save_clicked.connect(self._save_draft)
        self._editor_bar.cancel_clicked.connect(self._cancel_edit)
        self._editor_bar.delete_clicked.connect(self._delete_draft)
        self._editor_bar.hide()
        main.addWidget(self._editor_bar)

        self._photo_panel = PhotoPanel()
        main.addWidget(self._photo_panel)

        self._banner = QLabel()
        self._banner.setObjectName("banner")
        main.addWidget(self._banner)

        self._ai_note = QLabel()  # what the AI wasn't sure about, after reading a photo
        self._ai_note.setObjectName("aiNote")
        self._ai_note.setWordWrap(True)
        self._ai_note.setTextFormat(Qt.PlainText)
        self._ai_note.hide()
        main.addWidget(self._ai_note)

        self._views = BeatViews(
            key_labels={d: keyboard_in.key_label(d) for d in DrumClass} if self._dev_mode else None,
            view=self._settings.view,
        )
        self._grid = self._views.grid  # editing happens in the grid
        self._grid.cell_pressed.connect(self._on_cell_pressed)
        self._grid.cell_dragged.connect(self._on_cell_dragged)
        self._grid.beat_header_clicked.connect(self._on_beat_header)
        main.addWidget(self._views)

        self._summary = QLabel()
        self._summary.setObjectName("summary")
        self._summary.setTextFormat(Qt.RichText)
        self._summary.setWordWrap(True)
        self._summary.setMinimumHeight(70)
        main.addWidget(self._summary)
        main.addStretch()

    def _build_menus(self, root: QVBoxLayout) -> None:
        """Settings, tools and the view live in the menu bar, so the window
        itself is just the beat. On macOS a menu bar with no parent is the one
        at the top of the screen."""
        mac = sys.platform == "darwin"
        self._menu_bar = bar = QMenuBar(None if mac else self)
        if not mac:
            root.setMenuBar(bar)

        settings = bar.addMenu("Settings")
        self._menu_item(settings, "AI settings…", self._open_ai_settings)
        self._calibrate = self._menu_item(settings, "Calibrate", self._toggle_calibration)
        self._menu_item(settings, "Kit monitor", self._open_monitor)

        view = bar.addMenu("View")
        self._view_actions = QActionGroup(self)
        for name, label, key in ((NOTATION, "Notation", "Ctrl+1"), (GRID, "Grid", "Ctrl+2")):
            action = self._menu_item(view, label)
            action.setCheckable(True)
            action.setChecked(self._settings.view == name)
            action.setData(name)
            action.setShortcut(key)  # Ctrl is ⌘ on macOS
            self._view_actions.addAction(action)
        self._view_actions.triggered.connect(self._on_view_chosen)

        # Esc stops whatever is playing; calibration has no on-screen Stop button.
        QShortcut(QKeySequence(Qt.Key_Escape), self, self._stop_all)

        # Kept in Help: run from Python, macOS would file About under an app menu
        # named "Python". A packaged app can move it to its own app menu.
        self._menu_item(bar.addMenu("Help"), "About Drum Practice", self._show_about)

    def _menu_item(self, menu: QMenu, text: str, slot=None) -> QAction:
        """A menu item that stays in the menu it's put in. macOS otherwise moves
        items named like "settings" or "about" to the app menu, and only reads
        the role when the item is added, so it's set first."""
        action = QAction(text, self)
        action.setMenuRole(QAction.NoRole)
        if slot is not None:
            action.triggered.connect(lambda: slot())
        menu.addAction(action)
        return action

    def _on_view_chosen(self, action) -> None:
        self._settings.view = action.data()
        self._settings.save()
        self._views.set_view(self._settings.view)

    def _load_library(self) -> None:
        """Bundled examples + your beats, minus examples you've hidden."""
        everything = load_beats() + self._user_beats.load()
        hidden = set(self._settings.hidden_examples)
        self._hidden_count = sum(1 for b in everything if is_example(b) and b.id in hidden)
        self._beats = visible_beats(everything, self._settings.hidden_examples)

    def _reload_library(self, select_id: str | None) -> None:
        self._load_library()
        self._library.set_beats(self._beats, self._hidden_count)
        self._select_after_reload(select_id)

    def _select_after_reload(self, beat_id: str | None) -> None:
        """Select `beat_id` if it's still there, else the first beat, else nothing."""
        known = {b.id for b in self._beats}
        if beat_id in known:
            self._library.select(beat_id)
        elif self._beats:
            self._library.select(search_beats(self._beats)[0].id)
        else:
            self._show_no_beat()

    def _show_no_beat(self) -> None:
        self._stop_all()
        self._base_beat = None
        self._views.set_beat(None)
        self._summary.setText("")
        self._beat_name.setText("No beat selected")
        self._meta.setText("")
        self._banner.setText("Make your first beat with New beat in the library.")
        self._apply_locks()

    def _hide_example(self) -> None:
        if self._base_beat is None or not is_example(self._base_beat):
            return
        self._settings.hidden_examples = sorted(set(self._settings.hidden_examples) | {self._base_beat.id})
        self._settings.save()
        self._reload_library(select_id=None)

    def _restore_examples(self) -> None:
        self._settings.hidden_examples = []
        self._settings.save()
        self._reload_library(select_id=self._base_beat.id if self._base_beat else None)

    # --- actions ---

    def _practice_beat(self) -> Beat:
        """The selected beat reshaped by the current tempo and bars settings.
        While editing it's the draft exactly as written, at its own tempo."""
        if self._draft is not None:
            return self._draft
        s = self._settings
        return self._base_beat.with_bars(s.bars).with_tempo(s.tempo)

    def _select_beat(self, beat: Beat) -> None:
        self._stop_all()
        self._base_beat = beat
        if self._settings.beat_id != beat.id:
            self._settings.beat_id = beat.id
            self._settings.save()
        self._views.set_beat(self._practice_beat())
        self._summary.setText("")
        self._set_ai_note("")
        self._show_beat_details(beat)
        self._edit.setText("Edit" if is_user_beat(beat) else "Duplicate && edit")  # && shows a literal &
        self._apply_locks()
        self._show_idle_banner()

    def _show_beat_details(self, beat: Beat) -> None:
        self._beat_name.setText(beat.name or "Untitled")
        self._meta.setText(
            f"{beat.genre} · {beat.difficulty} · {beat.bars}-bar pattern · written at {beat.tempo:g} BPM"
        )

    def _on_settings_changed(self) -> None:
        self._settings.save()
        self._views.set_beat(self._practice_beat())
        # Hear changes straight away while something's playing.
        if self._mode is Mode.LISTEN:
            self._player.play(self._practice_beat())
        elif self._mode is Mode.METRONOME:
            self._metronome.play(self._settings.tempo)
        elif self._mode is Mode.IDLE:
            self._show_idle_banner()

    def _toggle_listen(self) -> None:
        if self._mode is Mode.LISTEN:
            self._stop_all()
            return
        self._stop_all()
        self._views.set_results(None)
        self._player.play(self._practice_beat())
        self._set_mode(Mode.LISTEN)
        self._banner.setText("Listening — press Stop when you're ready to practise")

    def _toggle_metronome(self) -> None:
        if self._mode is Mode.METRONOME:
            self._stop_all()
            return
        self._stop_all()
        self._metronome.play(self._settings.tempo)
        self._set_mode(Mode.METRONOME)

    def _toggle_practice(self) -> None:
        if self._mode is Mode.PRACTICE:
            self._stop_all()
            return
        self._stop_all()
        self._views.set_results(None)
        start = int(self._engine.mixer.position + START_LEAD_SECONDS * self._engine.sample_rate)
        self._timeline = Timeline(
            self._practice_beat(),
            start,
            self._engine.sample_rate,
            count_in=self._settings.count_in,
            metronome=self._settings.metronome,
        )
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
        self._metronome.stop()
        self._engine.mixer.clear()
        self._timeline = None
        self._views.set_position(None)
        if self._mode is not Mode.IDLE:
            self._set_mode(Mode.IDLE)
            self._show_idle_banner()

    def _set_mode(self, mode: Mode) -> None:
        self._mode = mode
        self._listen.setText("Stop" if mode is Mode.LISTEN else "Listen")
        self._start.setText("Stop" if mode is Mode.PRACTICE else "Start practice")
        self._calibrate.setText("Stop calibrating" if mode is Mode.CALIBRATE else "Calibrate")
        self._settings_bar.set_metronome_playing(mode is Mode.METRONOME)
        # Settings can't change mid-run; while listening or clicking they apply live.
        self._settings_bar.setEnabled(mode not in (Mode.PRACTICE, Mode.CALIBRATE))
        self._apply_locks()
        if mode is not Mode.IDLE:
            self._summary.setText("")

    # Dev mode keeps its own keyboard calibration; the regular app uses the kit's.

    def _latency_offset(self) -> float:
        return self._dev.keyboard_latency_offset if self._dev_mode else self._settings.latency_offset

    def _calibrated(self) -> bool:
        return self._dev.keyboard_calibrated if self._dev_mode else self._settings.calibrated

    def _save_calibration(self, offset: float) -> None:
        if self._dev_mode:
            self._dev.keyboard_latency_offset = offset
            self._dev.keyboard_calibrated = True
            self._dev.save()
        else:
            self._settings.latency_offset = offset
            self._settings.calibrated = True
            self._settings.save()

    def _apply_locks(self) -> None:
        """What's usable depends on the mode and on whether a beat is being edited."""
        editing = self._draft is not None
        running = self._mode in (Mode.PRACTICE, Mode.CALIBRATE)
        has_beat = self._base_beat is not None or editing
        self._library.set_locked(running or editing)
        self._listen.setEnabled(has_beat)
        self._start.setEnabled(has_beat and not editing)
        self._calibrate.setEnabled(not editing)
        self._edit.setVisible(not editing and self._base_beat is not None)
        self._edit.setEnabled(not running)
        example = self._base_beat is not None and is_example(self._base_beat)
        self._hide.setVisible(example and not editing)
        self._hide.setEnabled(not running)
        self._settings_bar.setVisible(not editing)
        self._editor_bar.setVisible(editing)
        self._views.set_editing(editing)

    def _show_idle_banner(self) -> None:
        if self._draft is not None:
            self._banner.setText("Editing: click a cell to add or remove a note, drag to paint. Click a beat number to change its grid.")
            return
        if self._base_beat is None:
            self._banner.setText("Make your first beat with New beat in the library.")
            return
        if not self._calibrated():
            self._banner.setText("Tip: choose Settings → Calibrate first so timing is graded accurately.")
        elif self._settings.count_in:
            self._banner.setText("Press Start practice: count-in, listen, count-in, then your turn.")
        else:
            self._banner.setText("Press Start practice: listen, then your turn.")

    # --- editing ---

    def _new_beat(self) -> None:
        dialog = NewBeatDialog(self)
        if not dialog.exec():
            return
        if dialog.choice == PHOTO:
            self._import_photo()
        else:
            self._start_edit(editing.blank())

    def _edit_current(self) -> None:
        beat = self._base_beat
        # Your own beats are edited in place; library beats are copied first.
        draft = replace(beat, notes=list(beat.notes)) if is_user_beat(beat) else editing.duplicate(beat)
        self._start_edit(draft)

    def _start_edit(self, draft: Beat, photo: bytes | None = None) -> None:
        self._stop_all()
        self._views.set_results(None)
        self._summary.setText("")
        self._set_ai_note("")
        self._grid.set_checks(set())
        self._draft = self._draft_start = draft
        if photo is None and is_user_beat(draft):
            photo = self._user_beats.photo(draft.id)
        self._draft_photo = photo
        self._photo_panel.set_photo(photo)
        self._editor_bar.load(draft, genres(self._beats), deletable=is_user_beat(draft))
        self._apply_locks()
        self._show_draft()
        self._show_idle_banner()

    def _show_draft(self) -> None:
        self._views.set_beat(self._draft)
        self._show_beat_details(self._draft)
        self._player.update_beat(self._draft)  # hear edits while listening

    def _on_cell_pressed(self, at, drum) -> None:
        self._draft, self._stroke = editing.click(self._draft, at, drum, self._editor_bar.brush)
        self._show_draft()

    def _on_cell_dragged(self, at, drum) -> None:
        self._draft = editing.paint(self._draft, at, drum, self._stroke, self._editor_bar.brush)
        self._show_draft()

    def _on_draft_details(self) -> None:
        self._draft = self._editor_bar.apply_details(self._draft)
        self._show_draft()

    def _on_draft_time_signature(self, ts) -> None:
        self._draft, moved = editing.set_time_signature(self._draft, ts)
        self._editor_bar.show_rhythm(self._draft)
        self._show_draft()
        self._report_moved(moved)

    def _on_draft_grid(self, columns: int) -> None:
        self._draft, moved = editing.set_grid(self._draft, columns)
        self._editor_bar.show_rhythm(self._draft)
        self._show_draft()
        self._report_moved(moved)

    def _on_beat_header(self, index: int, where: QPoint) -> None:
        """Click on a beat's number: choose how that beat alone is divided."""
        ts = self._draft.time_signature
        current = self._draft.chosen_columns(index)
        menu = QMenu(self)
        menu.addSection(f"Divide beat {index % self._draft.beats_per_bar + 1} into")
        for sub in SUBDIVISIONS:
            columns = sub.columns(ts)
            if columns is None:
                continue
            action = menu.addAction(sub.name)
            action.setCheckable(True)
            action.setChecked(columns == current)
            action.setData(columns)
        chosen = menu.exec(where)
        if chosen is not None and chosen.data() != current:
            self._draft, moved = editing.set_beat_columns(self._draft, index, chosen.data())
            self._show_draft()
            self._report_moved(moved)

    def _report_moved(self, moved: int) -> None:
        if moved:
            self._banner.setText(f"Moved {moved} note{'s' if moved != 1 else ''} to the nearest spot on the new grid.")
        else:
            self._show_idle_banner()

    def _on_draft_bars(self, bars: int) -> None:
        self._draft = editing.resize(self._draft, bars)
        self._show_draft()

    def _has_unsaved_changes(self) -> bool:
        if self._draft is None:
            return False
        if self._draft_photo is not None and not is_user_beat(self._draft_start):
            return True  # read from a photo and not saved anywhere yet
        return self._editor_bar.apply_details(self._draft).to_dict() != self._draft_start.to_dict()

    def _save_draft(self) -> None:
        draft = self._editor_bar.apply_details(self._draft)
        if not draft.name:
            self._banner.setText("Give the beat a name before saving.")
            return
        if not draft.notes:
            self._banner.setText("Add at least one note before saving.")
            return
        saved = self._user_beats.save(draft)
        if self._draft_photo:
            self._user_beats.save_photo(saved.id, self._draft_photo)
        if is_user_beat(self._draft_start) and not editing.same_music(self._draft_start, saved):
            self._scores.forget(saved.id)  # different notes: the old best no longer applies
        self._finish_edit(select_id=saved.id)
        self._banner.setText(f"Saved “{saved.name}” to your beats.")

    def _cancel_edit(self) -> None:
        if self._has_unsaved_changes() and not self._confirm("Discard your changes to this beat?"):
            return
        self._finish_edit(select_id=self._base_beat.id if self._base_beat else None)

    def _delete_draft(self) -> None:
        if not self._confirm(f"Delete “{self._draft_start.name}”? This can't be undone.", "Delete", danger=True):
            return
        self._user_beats.delete(self._draft_start.id)
        self._scores.forget(self._draft_start.id)
        self._finish_edit(select_id=None)

    def _finish_edit(self, select_id: str | None) -> None:
        self._stop_all()
        self._draft = self._draft_start = None
        self._draft_photo = None
        self._photo_panel.set_photo(None)
        self._set_ai_note("")
        self._grid.set_checks(set())
        self._apply_locks()
        self._reload_library(select_id)

    def _confirm(self, question: str, confirm: str = "Yes", danger: bool = False) -> bool:
        """Ask a yes/no question. `danger` styles the confirm button red, for
        actions that can't be undone."""
        box = QMessageBox(self)
        box.setWindowTitle("Drum Practice")
        box.setText(question)
        yes = box.addButton(confirm, QMessageBox.ButtonRole.AcceptRole)
        no = box.addButton("Cancel" if danger else "No", QMessageBox.ButtonRole.RejectRole)
        if danger:
            yes.setObjectName("danger")
            yes.style().unpolish(yes)  # re-apply the stylesheet now the name has changed
            yes.style().polish(yes)
        box.setDefaultButton(no)  # Enter shouldn't trigger an irreversible action
        box.exec()
        return box.clickedButton() is yes

    # --- beats from photos ---

    def _open_ai_settings(self) -> None:
        AISettingsDialog(self._settings, self).exec()

    def _import_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import a beat from a photo", str(Path.home()), "Images (*.png *.jpg *.jpeg)"
        )
        if not path:
            return
        image = QImage(path)
        if image.isNull():
            QMessageBox.warning(self, "Drum Practice", "That file couldn't be opened as an image (JPG or PNG).")
            return
        name = Path(path).stem.replace("_", " ").replace("-", " ").strip().title() or "From photo"
        dialog = PhotoImportDialog(image, name, self._settings, self)
        if not dialog.exec():
            return
        if dialog.manual:
            self._start_edit(editing.blank(name), photo=dialog.photo)
            self._banner.setText("Enter the notes from the photo, then Save.")
            return
        self._use_photo_result(dialog.result, dialog.photo)

    def _use_photo_result(self, result, photo: bytes) -> None:
        long_ones = [g for g in result.grooves if g.too_long]
        if long_ones:
            bars = max(g.bars_read for g in long_ones)
            keep = self._confirm(
                f"This looks like a song ({bars} bars). Songs arrive in a later update. "
                f"Keep the first {MAX_BEAT_BARS} bars as a beat?",
                f"Keep first {MAX_BEAT_BARS} bars",
            )
            if not keep:
                return
        notes = []
        if result.unsure:
            notes.append(describe_unsure(result.unsure, several_grooves=len(result.grooves) > 1))
        skipped = sum(len(g.problems) for g in result.grooves)
        if skipped:
            notes.append(f"{skipped} note(s) couldn't be placed and were left out.")

        if len(result.grooves) == 1:
            beat = result.grooves[0].beat
            self._start_edit(beat, photo=photo)
            self._grid.set_checks(unsure_cells(result.unsure, beat))
            self._banner.setText("Check the notes against the photo, fix anything, then Save.")
            self._set_ai_note("\n\n".join(notes))
            return

        chooser = GrooveChoiceDialog(result, self)
        if not chooser.exec() or not chooser.chosen():
            return
        saved = []
        for groove in chooser.chosen():
            beat = self._user_beats.save(groove.beat)
            self._user_beats.save_photo(beat.id, photo)
            saved.append(beat)
        self._reload_library(saved[0].id)
        self._banner.setText(
            f"Saved {len(saved)} beats from the photo. Open each with Edit to check it against the photo."
        )
        self._set_ai_note("\n\n".join(notes))

    def _set_ai_note(self, text: str) -> None:
        self._ai_note.setText(text)
        self._ai_note.setVisible(bool(text))

    # --- per frame ---

    def _tick(self) -> None:
        if self._mode is Mode.LISTEN:
            self._player.pump()
            self._views.set_position(self._player.current_position())
        elif self._mode is Mode.PRACTICE:
            self._tick_practice()
        elif self._mode is Mode.CALIBRATE:
            self._tick_calibration()
        elif self._mode is Mode.METRONOME:
            self._metronome.pump()
            beat = self._metronome.current_beat()
            dots = " ".join("●" if beat == b else "○" for b in range(1, self._metronome.beats_per_bar + 1))
            self._banner.setText(f"Metronome · {self._settings.tempo:.0f} BPM     {dots}")

    def _tick_practice(self) -> None:
        tl = self._timeline
        now = self._engine.position_samples()
        stage, position = tl.stage_at(now)
        beat = tl.beat
        if now < tl.segments[0].start:
            self._views.set_position(None)
            self._banner.setText("Get ready…")
        elif stage is Stage.COUNT_IN:
            self._views.set_position(None)
            self._banner.setText(f"Count-in   {int(position // float(beat.beat_quarters)) + 1}")
        elif stage is Stage.DEMO:
            self._views.set_position(position)
            self._banner.setText("Listen…")
        elif stage is Stage.PLAY:
            self._views.set_position(position)
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
            target = "any drum key" if self._dev_mode else "any pad"
            self._banner.setText(f"Hit {target} exactly on each click   {n} / {calibration.MEASURED_CLICKS}   (Esc to stop)")
        beat = 60.0 / calibration.TEMPO * sr
        if now > clicks[-1] + beat / 2:
            self._finish_calibration()

    # --- results ---

    def _finish_practice(self) -> None:
        tl = self._timeline
        offset = self._latency_offset()
        to_perf = self._engine.sample_to_perf
        play = tl.segment(Stage.PLAY)
        play_start, play_end = to_perf(play.start), to_perf(play.end)
        played = [
            Played(h.time - offset, h.drum)
            for h in self._hits
            if h.drum is not None and play_start - GOOD_WINDOW <= h.time - offset <= play_end + GOOD_WINDOW
        ]
        result = grade(tl.expected(to_perf), played)

        def quarters_of(p: Played) -> float:
            return (p.time - play_start) * tl.beat.tempo / 60.0

        self._views.set_results(
            GridResults(
                notes={(n.expected.at, n.expected.drum): n for n in result.notes},
                extras=[(quarters_of(p), p.drum) for p in result.extras],
                ignored=[(quarters_of(p), p.drum) for p in result.ignored],
            )
        )
        self._stop_all()
        new_best = self._scores.record(self._base_beat.id, result.score, tl.beat.tempo, tl.beat.bars)
        self._banner.setText(f"Score  {result.score:.0f}%" + ("   ★ New best!" if new_best else ""))
        self._summary.setText(_summary_text(result))
        if new_best:
            self._library.refresh_scores()

    def _finish_calibration(self) -> None:
        clicks = [self._engine.sample_to_perf(s) for s in self._calibration_clicks[calibration.LEAD_IN_CLICKS:]]
        m = calibration.measure(clicks, [h.time for h in self._hits])
        self._stop_all()
        if not m.enough_taps:
            self._banner.setText("Calibration didn't get enough hits. Choose Settings → Calibrate to try again.")
            return
        if not m.consistent:
            self._banner.setText(
                f"Your taps were too uneven to calibrate (scattered by ±{m.scatter * 1000:.0f} ms). "
                "Try again, hitting as steadily as you can."
            )
            return
        offset = m.offset
        self._save_calibration(offset)
        direction = "late" if offset >= 0 else "early"
        self._banner.setText(
            f"Calibrated: your hits arrive {abs(offset) * 1000:.0f} ms {direction}. That's now corrected for."
        )

    # --- MIDI ---

    def _on_hit(self, hit: Hit) -> None:
        if self._mode in (Mode.PRACTICE, Mode.CALIBRATE):
            self._hits.append(hit)

    def _poll_kit(self) -> None:
        kit = self._midi.poll_connection()
        if self._dev_mode:
            self._kit_status.setText("⌨ Keyboard (dev mode)" + (" + kit" if kit else ""))
            color = theme.ACCENT_TEXT
        elif kit:
            self._kit_status.setText("● Kit connected")
            color = theme.OK
        else:
            self._kit_status.setText("● Kit not found — switch it on")
            color = theme.BAD
        self._kit_status.setStyleSheet(f"color: {color}; background: {theme.SURFACE};")

    def _show_about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("About Drum Practice")
        box.setText("Drum Practice")
        box.setInformativeText(ABOUT_TEXT)
        box.exec()

    def _open_monitor(self) -> None:
        if self._monitor is None:
            self._monitor = MonitorWindow()
        self._monitor.show()
        self._monitor.raise_()

    def closeEvent(self, event) -> None:
        if self._has_unsaved_changes() and not self._confirm("Quit without saving the beat you're editing?"):
            event.ignore()
            return
        QApplication.instance().removeEventFilter(self)
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
    text += f"<br><span style='color:{theme.TEXT_DIM}'>Good notes are marked on the side you were off: left = early, right = late.</span>"
    return text
