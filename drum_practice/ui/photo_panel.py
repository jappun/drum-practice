"""The reference photo shown above the notation while editing a beat read from a photo."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget

BOX = QSize(520, 150)  # the photo is shrunk to fit inside this
LARGE = QSize(1200, 800)  # the click-to-enlarge view


class PhotoPanel(QWidget):
    def __init__(self):
        super().__init__()
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        self._image = QLabel()
        self._image.setObjectName("photo")
        self._image.setAlignment(Qt.AlignCenter)
        self._image.setCursor(Qt.PointingHandCursor)
        self._image.setToolTip("Click to see the photo larger")
        self._image.mousePressEvent = lambda event: self._enlarge()
        column.addWidget(self._image, 0, Qt.AlignLeft)
        self._pixmap: QPixmap | None = None
        self.hide()

    def set_photo(self, image: bytes | None) -> None:
        self._pixmap = None
        if image:
            pixmap = QPixmap()
            if pixmap.loadFromData(image):
                self._pixmap = pixmap
        self.setVisible(self._pixmap is not None)
        if self._pixmap is not None:
            self._image.setPixmap(_fit(self._pixmap, BOX))

    def _enlarge(self) -> None:
        if self._pixmap is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Photo")
        layout = QVBoxLayout(dialog)
        label = QLabel()
        label.setPixmap(_fit(self._pixmap, LARGE))
        layout.addWidget(label)
        dialog.exec()


def _fit(pixmap: QPixmap, box: QSize) -> QPixmap:
    """Shrink to fit the box (never enlarge, which would just blur it)."""
    if pixmap.width() <= box.width() and pixmap.height() <= box.height():
        return pixmap
    return pixmap.scaled(box, Qt.KeepAspectRatio, Qt.SmoothTransformation)
