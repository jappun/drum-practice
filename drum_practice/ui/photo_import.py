"""Import a beat from a photo: crop to the bars, then have an AI read them
(or enter the notes by hand with the photo alongside)."""

import logging

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..ai import keys
from ..ai.providers import PROVIDERS, TranscriptionError, friendly_message
from ..ai.transcription import PhotoResult, ReplyError, parse_reply, to_beats
from ..settings import Settings
from . import theme
from .ai_settings import PRIVACY, AISettingsDialog, chosen_model
from .worker import run_in_background

MAX_EDGE = 2000  # px sent to the AI: plenty for notation, well inside every provider's limits
MAX_BYTES = 4_500_000
VIEW_SIZE = QSize(880, 520)


log = logging.getLogger(__name__)  # --dev prints the AI's raw replies


def prepare_image(image: QImage, crop: QRect | None) -> tuple[bytes, str]:
    """The crop (or whole image), scaled down if huge, as PNG (or JPEG if large)."""
    part = image.copy(crop) if crop is not None and not crop.isEmpty() else image
    if max(part.width(), part.height()) > MAX_EDGE:
        part = part.scaled(MAX_EDGE, MAX_EDGE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    for fmt, mime, quality in (("PNG", "image/png", -1), ("JPEG", "image/jpeg", 90), ("JPEG", "image/jpeg", 75)):
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        part.save(buffer, fmt, quality)
        if data.size() <= MAX_BYTES:
            return bytes(data), mime
    return bytes(data), mime


class CropView(QWidget):
    """Shows the photo. Drag to select the bars to read: everything outside the
    selection is dimmed. Drag inside the selection to move it, or a corner to
    resize it; drag anywhere else to start a new one."""

    HANDLE = 8  # px: corner handle size, and how close counts as "on" a corner
    MIN_SIZE = 8

    def __init__(self, image: QImage):
        super().__init__()
        self.image = image
        self._pixmap = QPixmap.fromImage(image).scaled(VIEW_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setFixedSize(self._pixmap.size())
        self.setMouseTracking(True)
        self._scale = image.width() / self._pixmap.width()
        self.selection: QRect | None = None  # in widget coordinates
        self._drag: str | None = None  # "new", "move", or a corner: "tl", "tr", "bl", "br"
        self._anchor = QPoint()
        self._start_rect = QRect()

    # --- what a press at a point would do ---

    def _corners(self) -> dict[str, QPoint]:
        r = self.selection
        return {"tl": r.topLeft(), "tr": r.topRight(), "bl": r.bottomLeft(), "br": r.bottomRight()}

    def _action_at(self, point: QPoint) -> str:
        if self.selection is not None:
            for name, corner in self._corners().items():
                if (corner - point).manhattanLength() <= self.HANDLE * 1.5:
                    return name
            if self.selection.contains(point):
                return "move"
        return "new"

    def _update_cursor(self, point: QPoint) -> None:
        action = self._drag or self._action_at(point)
        shapes = {
            "move": Qt.SizeAllCursor,
            "tl": Qt.SizeFDiagCursor,
            "br": Qt.SizeFDiagCursor,
            "tr": Qt.SizeBDiagCursor,
            "bl": Qt.SizeBDiagCursor,
        }
        self.setCursor(shapes.get(action, Qt.CrossCursor))

    # --- mouse ---

    def mousePressEvent(self, event) -> None:
        point = event.position().toPoint()
        self._drag = self._action_at(point)
        self._anchor = point
        self._start_rect = QRect(self.selection) if self.selection is not None else QRect()
        if self._drag == "new":
            self.selection = QRect(point, point)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        point = self._clamp(event.position().toPoint())
        if self._drag is None:
            self._update_cursor(point)
            return
        if self._drag == "new":
            self.selection = QRect(self._anchor, point).normalized()
        elif self._drag == "move":
            moved = self._start_rect.translated(point - self._anchor)
            # Keep the whole selection on the photo.
            dx = max(0, -moved.left()) - max(0, moved.right() - (self.width() - 1))
            dy = max(0, -moved.top()) - max(0, moved.bottom() - (self.height() - 1))
            self.selection = moved.translated(dx, dy)
        else:
            # Resize: the opposite corner stays put.
            opposite = {"tl": "br", "tr": "bl", "bl": "tr", "br": "tl"}[self._drag]
            fixed = {
                "tl": self._start_rect.topLeft(),
                "tr": self._start_rect.topRight(),
                "bl": self._start_rect.bottomLeft(),
                "br": self._start_rect.bottomRight(),
            }[opposite]
            self.selection = QRect(fixed, point).normalized()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        self._drag = None
        if self.selection is not None and (
            self.selection.width() < self.MIN_SIZE or self.selection.height() < self.MIN_SIZE
        ):
            self.selection = None  # a click, not a drag: no selection (use the whole photo)
        self._update_cursor(event.position().toPoint())
        self.update()

    def _clamp(self, point: QPoint) -> QPoint:
        return QPoint(min(max(point.x(), 0), self.width() - 1), min(max(point.y(), 0), self.height() - 1))

    # --- drawing ---

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.drawPixmap(0, 0, self._pixmap)
        if self.selection is None:
            return
        # Dim everything outside the selection.
        outside = QPainterPath()
        outside.addRect(QRectF(self.rect()))
        inside = QPainterPath()
        inside.addRect(QRectF(self.selection))
        p.fillPath(outside.subtracted(inside), QColor(0, 0, 0, 150))
        # Border and corner handles.
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(theme.ACCENT), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(self.selection).adjusted(0.5, 0.5, -0.5, -0.5))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.ACCENT))
        half = self.HANDLE / 2
        for corner in self._corners().values():
            p.drawRect(QRectF(corner.x() - half, corner.y() - half, self.HANDLE, self.HANDLE))

    # --- results ---

    def clear(self) -> None:
        self.selection = None
        self.update()

    def crop_rect(self) -> QRect | None:
        """The selection in the original image's pixels."""
        if self.selection is None:
            return None
        s = self._scale
        r = self.selection
        return QRect(int(r.x() * s), int(r.y() * s), int(r.width() * s), int(r.height() * s))


class PhotoImportDialog(QDialog):
    """After exec(): `result` holds what was read (or None for by-hand entry,
    `manual` True), and `photo` the cropped image to keep as a reference."""

    def __init__(self, image: QImage, name: str, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import a beat from a photo")
        self._settings = settings
        self._name = name
        self._job = None
        self.result: PhotoResult | None = None
        self.manual = False
        self.photo: bytes = b""

        column = QVBoxLayout(self)
        column.setSpacing(12)
        hint = QLabel(
            "Drag over the bars you want to read (drag the box to move it, or a corner to resize it), "
            "or leave it to use the whole photo."
        )
        hint.setWordWrap(True)
        hint.setObjectName("meta")
        column.addWidget(hint)
        self._view = CropView(image)
        column.addWidget(self._view, 0, Qt.AlignCenter)

        provider_row = QHBoxLayout()
        self._provider_label = QLabel()
        settings_button = QPushButton("AI settings…")
        settings_button.clicked.connect(self._open_settings)
        clear = QPushButton("Clear selection")
        clear.clicked.connect(self._view.clear)
        provider_row.addWidget(self._provider_label, 1)
        provider_row.addWidget(clear)
        provider_row.addWidget(settings_button)
        column.addLayout(provider_row)

        privacy = QLabel(PRIVACY)
        privacy.setObjectName("meta")
        privacy.setWordWrap(True)
        column.addWidget(privacy)

        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setTextFormat(Qt.PlainText)
        column.addWidget(self._status)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self._by_hand = QPushButton("Enter by hand")
        self._by_hand.setToolTip("Open the editor with this photo alongside")
        self._by_hand.clicked.connect(self._enter_by_hand)
        self._read = QPushButton("Read notes")
        self._read.setObjectName("primary")
        self._read.clicked.connect(self._read_notes)
        for b in (cancel, self._by_hand, self._read):
            buttons.addWidget(b)
        column.addLayout(buttons)
        self._refresh_provider()

    def _provider(self):
        return PROVIDERS[self._settings.ai_provider]

    def _refresh_provider(self) -> None:
        cls = self._provider()
        model = chosen_model(self._settings, cls.name)
        has_key = keys.has_key(cls.name)
        self._provider_label.setText(f"Reads with {cls.label} · {model}")
        self._read.setEnabled(has_key)
        if not has_key:
            self._say(friendly_message(TranscriptionError(TranscriptionError.NO_KEY), cls.label), theme.TEXT_DIM)
        else:
            self._say("", theme.TEXT_DIM)

    def _open_settings(self) -> None:
        AISettingsDialog(self._settings, self).exec()
        self._refresh_provider()

    def _cropped(self) -> tuple[bytes, str]:
        return prepare_image(self._view.image, self._view.crop_rect())

    def _enter_by_hand(self) -> None:
        self.photo, _ = self._cropped()
        self.manual = True
        self.accept()

    def _read_notes(self) -> None:
        cls = self._provider()
        key = keys.get_key(cls.name)
        if not key:
            self._refresh_provider()
            return
        image, mime = self._cropped()
        self.photo = image
        model = chosen_model(self._settings, cls.name)
        provider = cls()
        name = self._name

        def work():
            reply = provider.read(image, mime, model, key)
            log.debug("%s (%s) replied in %.1fs:\n%s", cls.label, reply.model, reply.seconds, reply.text)
            return to_beats(parse_reply(reply.text), name=name)

        def done(result: PhotoResult):
            self.result = result
            self.accept()

        def failed(error):
            self._set_busy(False)
            if isinstance(error, TranscriptionError):
                self._say(friendly_message(error, cls.label), theme.BAD)
            elif isinstance(error, ReplyError):
                self._say(f"{error} You can try again, or enter it by hand.", theme.BAD)
            else:
                self._say(f"Something went wrong reading the photo: {error}", theme.BAD)

        self._set_busy(True)
        self._say(f"Reading the notes with {cls.label}… this can take up to a minute.", theme.ACCENT_TEXT)
        self._job = run_in_background(work, done, failed)

    def _set_busy(self, busy: bool) -> None:
        for widget in (self._read, self._by_hand):
            widget.setEnabled(not busy)

    def _say(self, text: str, color: str) -> None:
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {color};")
        self._status.setVisible(bool(text))

    def reject(self) -> None:
        if self._job is not None and not self._read.isEnabled() and not self._by_hand.isEnabled():
            return  # don't close mid-request; the result would arrive with nowhere to go
        super().reject()


class GrooveChoiceDialog(QDialog):
    """Several grooves were read from one photo: pick which to keep, each as its own beat."""

    def __init__(self, result: PhotoResult, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Grooves found in the photo")
        column = QVBoxLayout(self)
        column.setSpacing(10)
        title = QLabel(f"Found {len(result.grooves)} grooves. Each one you keep is saved as its own beat.")
        title.setWordWrap(True)
        column.addWidget(title)
        self._boxes = []
        for groove in result.grooves:
            beat = groove.beat
            detail = f"{beat.time_signature}, {beat.bars} bar{'s' if beat.bars != 1 else ''}, {len(beat.notes)} notes"
            if groove.problems:
                detail += f", {len(groove.problems)} unreadable note(s) skipped"
            box = QCheckBox(f"{beat.name}  ·  {detail}")
            box.setChecked(bool(beat.notes))
            self._boxes.append((box, groove))
            column.addWidget(box)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save selected")
        save.setObjectName("primary")
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        column.addLayout(buttons)

    def chosen(self):
        return [groove for box, groove in self._boxes if box.isChecked()]
