import sys

from PySide6.QtWidgets import QApplication

from .ui.monitor import MonitorWindow
from .ui.theme import STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Drum Practice")
    app.setStyleSheet(STYLESHEET)
    window = MonitorWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
