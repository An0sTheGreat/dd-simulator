"""Non-editable combo box whose full surface consistently opens the popup."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox


class FullClickComboBox(QComboBox):
    def __init__(self) -> None:
        super().__init__()
        self.setEditable(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self.showPopup()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.showPopup()
            event.accept()
            return
        super().keyPressEvent(event)
