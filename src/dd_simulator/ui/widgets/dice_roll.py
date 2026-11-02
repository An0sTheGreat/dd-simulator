"""Animated d20 roll shown under the newest conversation item, then faded away."""

from __future__ import annotations

import math
import random

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QRectF,
    QTimer,
    QVariantAnimation,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from dd_simulator.state import SkillCheckResult

ROLL_MS = 900
FADE_MS = 1000  # fixed; only the hold before it is a preference
DEFAULT_HOLD_SECONDS = 3.0
HOLD_RANGE_SECONDS = (1.0, 10.0)
DIE_SIZE = 58


class DieFace(QWidget):
    """A d20 silhouette (hexagon with its front triangle) that tumbles, then lands."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("diceRollDie")
        self.setFixedSize(DIE_SIZE, DIE_SIZE)
        self.number = 20
        self.angle = 0.0
        self.scale = 1.0
        self.state = "rolling"
        self._face = QColor(21, 17, 12)
        self._edge = QColor(213, 169, 54)
        self._text = QColor(244, 226, 185)
        self._success = QColor(117, 184, 77)
        self._failure = QColor(167, 67, 50)

    # Theme hooks: qproperty-faceColor etc. in the QSS.
    def _getter(name):  # type: ignore[no-untyped-def]
        return lambda self: getattr(self, name)

    def _setter(name):  # type: ignore[no-untyped-def]
        def set_color(self, color: QColor) -> None:  # type: ignore[no-untyped-def]
            setattr(self, name, QColor(color))
            self.update()
        return set_color

    faceColor = Property(QColor, _getter("_face"), _setter("_face"))
    edgeColor = Property(QColor, _getter("_edge"), _setter("_edge"))
    textColor = Property(QColor, _getter("_text"), _setter("_text"))
    successColor = Property(QColor, _getter("_success"), _setter("_success"))
    failureColor = Property(QColor, _getter("_failure"), _setter("_failure"))
    del _getter, _setter

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self.angle)
        painter.scale(self.scale, self.scale)
        radius = side * 0.44
        hexagon = [
            QPointF(radius * math.cos(math.radians(90 + 60 * i)),
                    -radius * math.sin(math.radians(90 + 60 * i)))
            for i in range(6)
        ]
        accent = {"success": self._success, "failure": self._failure}.get(self.state, self._edge)
        outline = QPainterPath(hexagon[0])
        for point in hexagon[1:]:
            outline.lineTo(point)
        outline.closeSubpath()
        painter.setPen(QPen(accent, 2.2))
        painter.setBrush(self._face)
        painter.drawPath(outline)
        # front face triangle and the edges running to the hexagon's corners
        inner = [QPointF(0, -radius * 0.62), QPointF(radius * 0.56, radius * 0.36),
                 QPointF(-radius * 0.56, radius * 0.36)]
        faint = QColor(accent)
        faint.setAlpha(140)
        painter.setPen(QPen(faint, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(inner)
        for a, b in ((0, 0), (0, 1), (0, 5), (1, 5), (1, 4), (1, 3), (2, 1), (2, 2), (2, 3)):
            painter.drawLine(inner[a], hexagon[b])
        font = QFont(self.font())
        font.setBold(True)
        font.setPixelSize(int(side * 0.27))
        painter.setFont(font)
        painter.setPen(accent if self.state != "rolling" else self._text)
        painter.drawText(QRectF(-radius, -radius * 0.45, radius * 2, radius), Qt.AlignmentFlag.AlignCenter,
                         str(self.number))
        painter.end()


class DiceRollBanner(QFrame):
    """Rolls for ``ROLL_MS``, holds the result for ``hold_ms``, fades over ``FADE_MS``."""

    finished = Signal()

    def __init__(
        self,
        result: SkillCheckResult,
        *,
        hold_ms: int = int(DEFAULT_HOLD_SECONDS * 1000),
        reduced_motion: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("diceRollBanner")
        self.result = result
        self.hold_ms = hold_ms
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(f"{result.name} roll")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 18, 8)
        layout.setSpacing(12)
        self.die = DieFace(self)
        layout.addWidget(self.die)
        text = QVBoxLayout()
        text.setSpacing(2)
        name = result.name if ":" in result.name else f"{result.name} check"
        self.title = QLabel(name.upper())
        self.title.setObjectName("diceRollTitle")
        self.detail = QLabel()
        self.detail.setObjectName("diceRollDetail")
        self.outcome = QLabel()
        self.outcome.setObjectName("diceRollOutcome")
        for label in (self.title, self.detail, self.outcome):
            text.addWidget(label)
        layout.addLayout(text)

        self.roll_animation = QVariantAnimation(self)
        self.roll_animation.setDuration(0 if reduced_motion else ROLL_MS)
        self.roll_animation.setStartValue(0.0)
        self.roll_animation.setEndValue(1.0)
        self.roll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.roll_animation.valueChanged.connect(self._tumble)
        self.roll_animation.finished.connect(self._land)
        self.hold_timer = QTimer(self)
        self.hold_timer.setSingleShot(True)
        self.hold_timer.timeout.connect(self._fade)
        # A QGraphicsOpacityEffect here would nest inside the conversation viewport's own
        # fade effect, and Qt then paints nothing; so the fade draws a snapshot instead.
        self.fade_animation = QVariantAnimation(self)
        self.fade_animation.setDuration(FADE_MS)
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.valueChanged.connect(self._set_fade)
        self.fade_animation.finished.connect(self.finished)
        self._snapshot: QPixmap | None = None
        self.fade_opacity = 1.0
        self._step = -1
        self._set_state("rolling")
        self.detail.setText(self._detail_text("?"))
        self.outcome.setText("ROLLING…")

    def start(self) -> None:
        if self.roll_animation.duration() == 0:
            self._land()
        else:
            self.roll_animation.start()

    def _detail_text(self, total: object) -> str:
        r = self.result
        roll = r.roll if total != "?" else "?"
        return f"d20 {roll} {'+' if r.modifier >= 0 else '−'} {abs(r.modifier)} = {total}  vs {r.target_label} {r.target}"

    def _tumble(self, value: object) -> None:
        t = float(value)
        step = int(t * 14)  # number changes slow down as the curve eases out
        if step != self._step:
            self._step = step
            self.die.number = random.randint(1, 20)
        self.die.angle = (1.0 - t) * 540.0
        self.die.scale = 1.0 + 0.18 * math.sin(math.pi * t)
        self.die.update()

    def _land(self) -> None:
        if self.die.state != "rolling":
            return
        state = "success" if self.result.success else "failure"
        self.die.number, self.die.angle, self.die.scale = self.result.roll, 0.0, 1.0
        self.detail.setText(self._detail_text(self.result.total))
        self.outcome.setText("SUCCESS" if self.result.success else "FAILED")
        self._set_state(state)
        self.hold_timer.start(self.hold_ms)

    def _fade(self) -> None:
        self._snapshot = self.grab()
        self.setFixedSize(self.size())
        for child in self.findChildren(QWidget):
            child.hide()
        self.fade_animation.start()

    def _set_fade(self, value: object) -> None:
        self.fade_opacity = float(value)
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._snapshot is None:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setOpacity(self.fade_opacity)
        painter.drawPixmap(0, 0, self._snapshot)
        painter.end()

    def _set_state(self, state: str) -> None:
        self.die.state = state
        self.die.update()
        for label in (self.detail, self.outcome):
            label.setProperty("checkState", state)
            label.style().unpolish(label)
            label.style().polish(label)

    @property
    def state(self) -> str:
        return self.die.state
