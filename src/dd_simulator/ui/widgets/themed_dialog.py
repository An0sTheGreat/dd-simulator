"""Shared frameless shell for themed application dialogs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from dd_simulator.ui.widgets.semantic_button import SemanticButton

class DraggableTitleBar(QFrame):
    def __init__(self, *, maximizable: bool = False) -> None:
        super().__init__()
        self.maximizable = maximizable

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            self.restore_from_maximized_drag(
                event.position(), event.globalPosition()
            )
            handle = window.windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
        super().mousePressEvent(event)

    def restore_from_maximized_drag(self, local_position, global_position) -> bool:
        """Restore under the pointer before handing the active drag to Windows."""

        window = self.window()
        if not self.maximizable or not window.isMaximized():
            return False
        restore = window.normalGeometry()
        width = max(restore.width(), window.minimumWidth())
        height = max(restore.height(), window.minimumHeight())
        horizontal_anchor = local_position.x() / max(1, self.width())
        window.showNormal()
        window.resize(width, height)
        window.move(
            int(global_position.x() - (width * horizontal_anchor)),
            int(global_position.y() - local_position.y()),
        )
        return True

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self.maximizable and event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            window.showNormal() if window.isMaximized() else window.showMaximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class ThemedDialog(QDialog):
    """A native modal dialog with an application-owned title bar."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dimming_active = False
        self.setWindowTitle(title)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        shell = QVBoxLayout(self)
        shell.setContentsMargins(10, 10, 10, 10)
        shell.setSpacing(8)

        self.title_bar = DraggableTitleBar()
        self.title_bar.setObjectName("themedDialogTitleBar")
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(10, 3, 3, 3)
        left_balance = QWidget()
        left_balance.setFixedWidth(28)
        title_layout.addWidget(left_balance)
        title_label = QLabel(title)
        title_label.setObjectName("themedDialogWindowTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(title_label, 1)
        close = SemanticButton("×", role="secondary", object_name="themedDialogCloseButton")
        close.setAccessibleName("Close dialog")
        close.setFixedSize(28, 24)
        close.clicked.connect(self.reject)
        title_layout.addWidget(close)
        shell.addWidget(self.title_bar)

        content = QWidget()
        content.setObjectName("themedDialogContent")
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(10, 4, 10, 10)
        shell.addWidget(content, 1)

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        owner = self.parentWidget().window() if self.parentWidget() is not None else None
        dim = getattr(owner, "set_dialog_dimmed", None)
        if callable(dim) and not self._dimming_active:
            dim(True)
            self._dimming_active = True

    def hideEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._dimming_active:
            owner = self.parentWidget().window() if self.parentWidget() is not None else None
            dim = getattr(owner, "set_dialog_dimmed", None)
            if callable(dim):
                dim(False)
            self._dimming_active = False
        super().hideEvent(event)
