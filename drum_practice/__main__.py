import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .ui.theme import STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Drum Practice")
    app.setStyleSheet(STYLESHEET)
    # --dev is the only way to enable keyboard drums (a developer tool).
    window = MainWindow(dev_mode="--dev" in sys.argv[1:])
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
