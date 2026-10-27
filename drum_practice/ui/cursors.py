"""Pointing-hand cursor on everything clickable, app-wide.

Qt stylesheets can't set cursors, so an application event filter sets them
as widgets are first polished and whenever they're enabled or disabled
(disabled controls get the normal arrow, so the cursor shows what's usable)."""

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractButton, QComboBox, QListWidget, QSlider, QWidget

CLICKABLE = (QAbstractButton, QComboBox, QSlider)


class PointerCursors(QObject):
    def eventFilter(self, obj, event) -> bool:
        if event.type() in (QEvent.Polish, QEvent.EnabledChange) and isinstance(obj, QWidget):
            target = obj.viewport() if isinstance(obj, QListWidget) else obj
            if isinstance(obj, (*CLICKABLE, QListWidget)):
                target.setCursor(Qt.PointingHandCursor if obj.isEnabled() else Qt.ArrowCursor)
        return False
