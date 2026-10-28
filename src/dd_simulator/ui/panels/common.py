"""Shared semantic helpers for static dashboard panels."""

from PySide6.QtCore import QEasingCurve, QTimer, Qt, QVariantAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QVBoxLayout, QWidget

from dd_simulator.ui.widgets.themed_frame import ThemedFrame


class DashboardPanel(ThemedFrame):
    """Base frame with a consistent title and content layout."""

    def __init__(self, object_name: str, title: str) -> None:
        super().__init__(object_name, role="panel")
        self.setAccessibleName(title)
        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(12, 10, 12, 10)
        self.content_layout.setSpacing(7)

        if title:
            heading = QLabel(title)
            heading.setObjectName("panelTitle")
            heading.setProperty("textRole", "heading")
            heading.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.content_layout.addWidget(heading)


def semantic_label(
    text: str,
    *,
    object_name: str = "contentLabel",
    text_role: str = "body",
    word_wrap: bool = False,
) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setProperty("textRole", text_role)
    label.setWordWrap(word_wrap)
    return label


def highlight_recent_turn(
    owner: QWidget,
    widgets: list[QWidget],
    *,
    reduced_motion: bool,
) -> None:
    """Emphasize a newly committed player/response pair for three seconds."""

    previous_clear = getattr(owner, "_recent_turn_clear", None)
    if callable(previous_clear):
        previous_clear()
    animations: list[QVariantAnimation] = []
    previous_styles = {widget: widget.styleSheet() for widget in widgets}
    for widget in widgets:
        widget.setProperty("recentTurn", True)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        if reduced_motion:
            continue
        glow = QGraphicsDropShadowEffect(widget)
        glow.setBlurRadius(14)
        glow.setOffset(0, 0)
        glow.setColor(QColor(255, 210, 80, 255))
        widget.setGraphicsEffect(glow)
        animation = QVariantAnimation(owner)
        animation.setDuration(3000)
        animation.setStartValue(255)
        animation.setEndValue(0)
        animation.setEasingCurve(QEasingCurve.Type.InOutSine)

        def apply_opacity(value: object, target: QWidget = widget, effect=glow) -> None:
            alpha = int(value)
            target.setStyleSheet(
                f"background-color: rgba(255, 210, 80, {alpha}); "
                f"border-left: 2px solid rgba(255, 210, 80, {alpha}); padding-left: 5px;"
            )
            effect.setColor(QColor(255, 210, 80, alpha))

        animation.valueChanged.connect(apply_opacity)
        apply_opacity(255)
        animation.start()
        animations.append(animation)

    def clear() -> None:
        timer.stop()
        for animation in animations:
            animation.stop()
        for widget in widgets:
            widget.setProperty("recentTurn", False)
            widget.setGraphicsEffect(None)
            widget.setStyleSheet(previous_styles.get(widget, ""))
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        animations.clear()

    timer = QTimer(owner)
    timer.setSingleShot(True)
    timer.timeout.connect(clear)
    owner._recent_turn_timer = timer  # type: ignore[attr-defined]
    owner._recent_turn_animations = animations  # type: ignore[attr-defined]
    owner._recent_turn_clear = clear  # type: ignore[attr-defined]
    timer.start(3000)
