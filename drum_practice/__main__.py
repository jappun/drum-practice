import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .ui.theme import STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Drum Practice")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
