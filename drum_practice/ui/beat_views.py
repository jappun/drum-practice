"""The notation and grid views of a beat, kept in step.

Practice shows one of them (the user's choice); editing shows both, with
notation as a live preview above the grid you click in."""

from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..kit import DrumClass
from ..model import Beat
from .grid import BeatGrid, GridResults
from .notation_view import NotationView

NOTATION, GRID = "notation", "grid"


class BeatViews(QWidget):
    def __init__(self, key_labels: dict[DrumClass, str] | None = None, view: str = NOTATION):
        super().__init__()
        self.notation = NotationView()
        self.grid = BeatGrid(key_labels=key_labels)
        self._view = view if view in (NOTATION, GRID) else NOTATION
        self._editing = False
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        column.addWidget(self.notation)
        column.addWidget(self.grid)
        self._apply()

    @property
    def view(self) -> str:
        return self._view

    def set_view(self, view: str) -> None:
        self._view = view
        self._apply()

    def set_editing(self, editing: bool) -> None:
        self._editing = editing
        self.grid.set_editable(editing)
        self._apply()

    def _apply(self) -> None:
        self.notation.setVisible(self._editing or self._view == NOTATION)
        self.grid.setVisible(self._editing or self._view == GRID)

    # Both views always show the same thing.

    def set_beat(self, beat: Beat | None) -> None:
        self.notation.set_beat(beat)
        self.grid.set_beat(beat)

    def set_position(self, quarters: float | None) -> None:
        self.notation.set_position(quarters)
        self.grid.set_position(quarters)

    def set_results(self, results: GridResults | None) -> None:
        self.notation.set_results(results)
        self.grid.set_results(results)
