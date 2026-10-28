"""Shared positioning for non-activating themed hover cards."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QFrame, QWidget


class PositionedHoverCard(QFrame):
    def __init__(self, parent: QWidget, *, object_name: str, card_kind: str) -> None:
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setObjectName(object_name)
        self.setProperty("cardKind", card_kind)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def show_near(self, global_position: QPoint) -> None:
        self.adjustSize()
        screen = QApplication.screenAt(global_position) or QApplication.primaryScreen()
        position = global_position + QPoint(14, 18)
        if screen is not None:
            bounds = screen.availableGeometry()
            position.setX(
                max(bounds.left(), min(position.x(), bounds.right() - self.width() + 1))
            )
            position.setY(
                max(bounds.top(), min(position.y(), bounds.bottom() - self.height() + 1))
            )
        self.move(position)
        self.show()
        self.raise_()

    def show_beside(self, reference: QWidget, *, gap: int = 10) -> None:
        """Show beside another hover card while keeping both on the active screen."""

        self.adjustSize()
        reference_top_left = reference.mapToGlobal(QPoint(0, 0))
        screen = QApplication.screenAt(reference_top_left) or QApplication.primaryScreen()
        position = reference_top_left + QPoint(reference.width() + gap, 0)
        if screen is not None:
            bounds = screen.availableGeometry()
            if position.x() + self.width() > bounds.right() + 1:
                position.setX(reference_top_left.x() - self.width() - gap)
            position.setX(
                max(bounds.left(), min(position.x(), bounds.right() - self.width() + 1))
            )
            position.setY(
                max(bounds.top(), min(position.y(), bounds.bottom() - self.height() + 1))
            )
        self.move(position)
        self.show()
        self.raise_()
