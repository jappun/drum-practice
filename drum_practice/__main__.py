import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from .ui.cursors import PointerCursors
from .ui.main_window import MainWindow
from .ui.theme import ACCENT_TEXT, STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Drum Practice")
    app.setStyleSheet(STYLESHEET)
    palette = app.palette()
    palette.setColor(QPalette.Link, QColor(ACCENT_TEXT))  # readable links on the dark theme
    app.setPalette(palette)
    cursors = PointerCursors(app)  # pointing hand on anything clickable
    app.installEventFilter(cursors)
    # --dev is the only way to enable keyboard drums (a developer tool).
    window = MainWindow(dev_mode="--dev" in sys.argv[1:])
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
