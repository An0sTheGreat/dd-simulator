"""Shared layout and positioning for non-activating themed hover cards."""

from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QCursor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QStyle,
    QStyleOption,
    QVBoxLayout,
    QWidget,
)

CARD_WIDTH = 320
CARD_ICON_SIZE = 46
CURSOR_OFFSET = QPoint(14, 18)


def card_label(text: str, object_name: str, *, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setTextFormat(Qt.TextFormat.PlainText)  # card text may come from the model
    label.setWordWrap(wrap)
    return label


def card_icon(path: Path) -> QLabel:
    icon = QLabel()
    icon.setFixedSize(CARD_ICON_SIZE, CARD_ICON_SIZE)
    icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon.setPixmap(
        QPixmap(str(path)).scaled(
            CARD_ICON_SIZE - 2,
            CARD_ICON_SIZE - 2,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )
    return icon


def card_bounds(host: QWidget | None, point: QPoint, size: QSize | None = None) -> QRect:
    """The area a card must stay inside: the host window clipped to its screen.

    A window too small to hold the card beside the cursor falls back to the
    screen; clamping into it would put the card under the cursor, and the
    host's leave/enter would then recreate the card forever.
    """

    screen = QApplication.screenAt(point) or QApplication.primaryScreen()
    screen_rect = screen.availableGeometry() if screen is not None else QRect()
    window = host.window() if host is not None else None
    if window is None or not window.isVisible():
        return screen_rect
    clipped = window.geometry().intersected(screen_rect)
    if clipped.isEmpty():
        clipped = window.geometry()
    if size is not None and (
        clipped.width() < size.width() + CURSOR_OFFSET.x()
        or clipped.height() < size.height() + CURSOR_OFFSET.y()
    ):
        return screen_rect
    return clipped


def place_card(size: QSize, anchor: QPoint, bounds: QRect) -> QPoint:
    """Below-right of the anchor, flipped left or up when that would leave the bounds."""

    x = anchor.x() + CURSOR_OFFSET.x()
    if x + size.width() > bounds.right() + 1:
        x = anchor.x() - CURSOR_OFFSET.x() - size.width()
    y = anchor.y() + CURSOR_OFFSET.y()
    if y + size.height() > bounds.bottom() + 1:
        y = anchor.y() - CURSOR_OFFSET.y() - size.height()
    x = max(bounds.left(), min(x, bounds.right() - size.width() + 1))
    y = max(bounds.top(), min(y, bounds.bottom() - size.height() + 1))
    return QPoint(x, y)


class PositionedHoverCard(QFrame):
    def __init__(self, parent: QWidget, *, object_name: str, card_kind: str) -> None:
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setObjectName(object_name)
        self.setProperty("cardKind", card_kind)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def show_near(self, global_position: QPoint) -> None:
        # One card at a time: a newly hovered card replaces any other open one.
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, PositionedHoverCard) and widget is not self and widget.isVisible():
                widget.close()
        self.adjustSize()
        bounds = card_bounds(self.parentWidget(), global_position, self.size())
        self.move(place_card(self.size(), global_position, bounds))
        self.show()
        self.raise_()

    def show_beside(self, reference: QWidget, *, gap: int = 10) -> None:
        """Show beside another hover card while keeping both inside the window."""

        self.setProperty("companion", True)
        self.adjustSize()
        reference_top_left = reference.mapToGlobal(QPoint(0, 0))
        bounds = card_bounds(self.parentWidget(), reference_top_left, self.size())
        position = reference_top_left + QPoint(reference.width() + gap, 0)
        if position.x() + self.width() > bounds.right() + 1:
            position.setX(reference_top_left.x() - self.width() - gap)
        position.setX(max(bounds.left(), min(position.x(), bounds.right() - self.width() + 1)))
        position.setY(max(bounds.top(), min(position.y(), bounds.bottom() - self.height() + 1)))
        self.move(position)
        self.show()
        self.raise_()


class TooltipCard(PositionedHoverCard):
    """The shared Concept T card: header, stat table, extras, description, footer.

    ``tone`` (a rarity, or ability, spell, skill, response) drives the name and
    frame colours in each theme's QSS.
    """

    def __init__(
        self,
        parent: QWidget,
        *,
        object_name: str,
        card_kind: str,
        title: str,
        tone: str,
        subtitle: str = "",
        icon: QLabel | None = None,
        badge: str = "",
        badge_tone: str = "",
        rows: Sequence[tuple[str, str]] = (),
        extras: Sequence[QWidget] = (),
        description: str = "",
        footer: str = "",
        width: int = CARD_WIDTH,
    ) -> None:
        super().__init__(parent, object_name=object_name, card_kind=card_kind)
        self.setProperty("tone", tone)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAccessibleName(f"{title}. {subtitle}".strip(". "))
        self.setFixedWidth(width)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)  # frame and padding come from QSS
        layout.setSpacing(6)
        header = QHBoxLayout()
        header.setSpacing(10)
        self.icon_label = icon
        if icon is not None:
            icon.setObjectName(icon.objectName() or "tooltipIcon")
            icon.setProperty("tone", tone)
            header.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
        names = QVBoxLayout()
        names.setSpacing(1)
        self.title_label = card_label(title, "tooltipName", wrap=True)
        self.title_label.setProperty("tone", tone)
        names.addWidget(self.title_label)
        self.subtitle_label = card_label(subtitle, "tooltipSubtitle", wrap=True)
        self.subtitle_label.setVisible(bool(subtitle))
        names.addWidget(self.subtitle_label)
        header.addLayout(names, 1)
        self.badge_label: QLabel | None = None
        if badge:
            self.badge_label = card_label(badge.upper(), "tooltipBadge")
            self.badge_label.setProperty("badgeTone", badge_tone)
            header.addWidget(self.badge_label, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        divider = QFrame()
        divider.setObjectName("tooltipDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        table = QGridLayout()
        table.setContentsMargins(0, 0, 0, 0)
        table.setHorizontalSpacing(10)
        table.setVerticalSpacing(3)
        table.setColumnMinimumWidth(0, width * 2 // 5 - 20)
        table.setColumnStretch(1, 1)
        self.rows: dict[str, QLabel] = {}
        for row, (name, value) in enumerate(rows):
            table.addWidget(card_label(name, "tooltipStatName"), row, 0, Qt.AlignmentFlag.AlignTop)
            value_label = card_label(value or "—", "tooltipStatValue", wrap=True)
            table.addWidget(value_label, row, 1)
            self.rows[name] = value_label
        layout.addLayout(table)
        for extra in extras:
            layout.addWidget(extra)

        self.description_label: QLabel | None = None
        if description:
            self.description_label = card_label(description, "tooltipDescription", wrap=True)
            font = self.description_label.font()
            font.setItalic(True)
            self.description_label.setFont(font)
            layout.addWidget(self.description_label)
        self.footer_label: QLabel | None = None
        if footer:
            self.footer_label = card_label(footer, "tooltipFooter", wrap=True)
            layout.addWidget(self.footer_label)

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        # A translucent top-level skips its styled background, so the QSS frame
        # (border-image or border) is painted here; the corners stay transparent.
        option = QStyleOption()
        option.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, option, painter, self)

    def text_content(self) -> str:
        return " ".join(label.text() for label in self.findChildren(QLabel) if label.text())


class HoverCardHost:
    """Mixin for a QWidget that shows ``build_hover_card()`` only while hovered."""

    hover_card: PositionedHoverCard | None = None
    _hover_suppressed = False

    def build_hover_card(self) -> PositionedHoverCard | None:
        raise NotImplementedError

    def enterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        # A repeated enter while our card is up (showing or closing a card can
        # synthesise one) must not rebuild it, or enter/close ping-pongs forever.
        showing = self.hover_card is not None and self.hover_card.isVisible()
        if not self._hover_suppressed and not showing:
            self.close_hover_card()
            self.hover_card = self.build_hover_card()
            if self.hover_card is not None:
                self.hover_card.show_near(QCursor.pos())
        super().enterEvent(event)  # type: ignore[misc]

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.close_hover_card()
        self._hover_suppressed = False
        super().leaveEvent(event)  # type: ignore[misc]

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._hover_suppressed = True
        self.close_hover_card()
        super().mousePressEvent(event)  # type: ignore[misc]

    def close_hover_card(self) -> None:
        if self.hover_card is not None:
            self.hover_card.close()
            self.hover_card.deleteLater()
            self.hover_card = None
