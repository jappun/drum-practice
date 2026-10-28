"""The New beat dialog: read a beat from a photo, or write one in the editor."""

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

PHOTO, WRITE = "photo", "write"


class NewBeatDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New beat")
        self.choice: str | None = None

        column = QVBoxLayout(self)
        column.setSpacing(12)
        column.setContentsMargins(24, 20, 24, 20)
        heading = QLabel("Make a new beat")
        heading.setObjectName("sectionHeading")
        column.addWidget(heading)

        for choice, title, detail in (
            (PHOTO, "From a photo", "Read the notes from a photo of sheet music (JPG or PNG)."),
            (WRITE, "Write it yourself", "Start from an empty grid in the editor."),
        ):
            button = QPushButton(f"{title}\n{detail}")
            button.setObjectName("choice")
            button.setMinimumWidth(380)
            button.clicked.connect(lambda _=False, c=choice: self._choose(c))
            column.addWidget(button)

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(cancel)
        column.addLayout(row)

    def _choose(self, choice: str) -> None:
        self.choice = choice
        self.accept()
