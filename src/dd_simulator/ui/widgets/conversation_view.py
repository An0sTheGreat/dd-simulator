"""Concept T conversation: a transparent, bottom-anchored message thread over the scene art."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import (
    Property,
    QCoreApplication,
    QEvent,
    QEasingCurve,
    QPropertyAnimation,
    QTimer,
    QVariantAnimation,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from dd_simulator.ui.models.presentation import NarrativeMessageView

PORTRAIT_SIZE = 38
NOTE_INDENT = 48
PLAYER_MAX_SHARE = 0.62
NPC_MAX_SHARE = 0.78
# Top fade, as in the mockup's mask: transparent at 0, 25% at 70 px, opaque from 190 px.
FADE_STOPS = ((0.0, 0), (70 / 190, 64), (1.0, 255))
FADE_HEIGHT = 190
EMPHASIS_MS = 3000
SCROLL_MS = 260


def _text_label(text: str, object_name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    # Model output is untrusted: never let QLabel interpret it as rich text.
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _rounded_portrait(path: str, size: int, radius: float) -> QPixmap | None:
    source = QPixmap(path) if path else QPixmap()
    if source.isNull():
        return None
    source = source.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(0, 0, size, size, radius, radius)
    painter.setClipPath(clip)
    painter.drawPixmap((size - source.width()) // 2, (size - source.height()) // 2, source)
    painter.end()
    return result


class ConversationMessage(QWidget):
    """One message row. ``box`` is the bordered frame (player/NPC) or the narrator label."""

    def __init__(self, message: NarrativeMessageView) -> None:
        super().__init__()
        self.message = message
        self.kind = message.kind
        self.setProperty("messageKind", message.kind)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.portrait: QLabel | None = None
        self.speaker_label: QLabel | None = None
        if message.kind == "player":
            self.role = "player"
            self.setObjectName("conversationPlayerRow")
            self.box = QFrame()
            self.box.setObjectName("conversationPlayer")
            box_layout = QVBoxLayout(self.box)
            box_layout.setContentsMargins(12, 6, 12, 6)
            self.text_label = _text_label(message.text, "conversationPlayerText")
            box_layout.addWidget(self.text_label)
            layout.addStretch(1)
            layout.addWidget(self.box)
            self.setAccessibleName(f"You: {message.text}")
        elif message.kind == "spoken":
            self.role = "npc"
            self.setObjectName("conversationNpcRow")
            name = message.speaker_name.strip()
            self.portrait = QLabel()
            self.portrait.setObjectName("conversationPortrait")
            self.portrait.setFixedSize(PORTRAIT_SIZE, PORTRAIT_SIZE)
            self.portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = _rounded_portrait(message.speaker_portrait, PORTRAIT_SIZE - 4, 4)
            if pixmap is None:
                self.portrait.setProperty("placeholder", True)
                self.portrait.setText(name[:1].upper())
            else:
                self.portrait.setProperty("placeholder", False)
                self.portrait.setPixmap(pixmap)
            self.portrait.setAccessibleName(f"{name} portrait" if name else "Unknown speaker")
            self.box = QFrame()
            self.box.setObjectName("conversationNpc")
            box_layout = QVBoxLayout(self.box)
            box_layout.setContentsMargins(12, 6, 12, 6)
            box_layout.setSpacing(1)
            if name:
                self.speaker_label = _text_label(name, "conversationSpeaker")
                box_layout.addWidget(self.speaker_label)
            self.text_label = _text_label(message.text, "conversationNpcText")
            box_layout.addWidget(self.text_label)
            layout.addWidget(self.portrait, 0, Qt.AlignmentFlag.AlignTop)
            layout.addWidget(self.box)
            layout.addStretch(1)
            self.setAccessibleName(f"{name or 'Someone'} says: {message.text}")
        else:
            # narrative, monologue, combat and system lines read as plain narration.
            self.role = "narrator"
            self.setObjectName("conversationNarratorRow")
            self.text_label = _text_label(message.text, "conversationNarrator")
            self.text_label.setProperty("messageKind", message.kind)
            self.box = self.text_label
            layout.addWidget(self.text_label, 1)
            self.setAccessibleName(message.text)

    def fit_width(self, row_width: int) -> None:
        """Shrink the box to its text, capped at the kind's share of the row."""

        if self.role == "narrator":
            return
        share = PLAYER_MAX_SHARE if self.role == "player" else NPC_MAX_SHARE
        labels = [self.text_label] + ([self.speaker_label] if self.speaker_label else [])
        natural = 0
        for label in labels:
            label.ensurePolished()
            natural = max(natural, label.fontMetrics().horizontalAdvance(label.text()) + 4)
        margins = self.box.layout().contentsMargins()
        natural += margins.left() + margins.right() + 2
        self.box.setFixedWidth(max(1, min(natural, int(row_width * share))))


class ConversationNotes(QWidget):
    """The tags under a turn's last message; right-aligned after the player, else indented."""

    def __init__(self, message: NarrativeMessageView) -> None:
        super().__init__()
        self.setObjectName("conversationNotes")
        self.alignment = "right" if message.kind == "player" else "indent"
        self.setProperty("noteAlignment", self.alignment)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0 if self.alignment == "right" else NOTE_INDENT, 0, 0, 0)
        layout.setSpacing(6)
        if self.alignment == "right":
            layout.addStretch(1)
        self.tags: list[QLabel] = []
        for note in message.notes:
            tag = QLabel(note.text)
            tag.setObjectName("conversationNote")
            tag.setTextFormat(Qt.TextFormat.PlainText)
            tag.setProperty("noteKind", note.kind)
            tag.setAccessibleName(note.text)
            layout.addWidget(tag)
            self.tags.append(tag)
        if self.alignment != "right":
            layout.addStretch(1)
        self.setAccessibleName("Turn updates: " + ", ".join(n.text for n in message.notes))


class ConversationView(QScrollArea):
    """Scrollable history that fades into the art above it and pages older turns on demand."""

    older_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None, *, reduced_motion: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("conversationView")
        self.setAccessibleName("Conversation")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.viewport().setAutoFillBackground(False)
        self.reduced_motion = reduced_motion
        self._shadow_color = QColor(0, 0, 0)
        self._highlight_color = QColor(229, 192, 114)
        self._has_older = False
        self._older_pending = False
        self.messages: list[NarrativeMessageView] = []
        self.rows: list[ConversationMessage] = []
        self.note_rows: list[ConversationNotes] = []
        self.recent_rows: list[ConversationMessage] = []

        thread = QWidget()
        thread.setObjectName("conversationThread")
        thread.setAutoFillBackground(False)
        self._layout = QVBoxLayout(thread)
        self._layout.setContentsMargins(24, 0, 13, 4)
        self._layout.setSpacing(8)
        self._layout.addStretch(1)  # keeps the thread anchored to the bottom
        self.setWidget(thread)
        thread.setAutoFillBackground(False)  # setWidget turns it on; the scene must show through

        fade = QGraphicsOpacityEffect(self.viewport())
        gradient = QLinearGradient(0, 0, 0, FADE_HEIGHT)
        for stop, alpha in FADE_STOPS:
            gradient.setColorAt(stop, QColor(0, 0, 0, alpha))
        fade.setOpacityMask(QBrush(gradient))
        self.viewport().setGraphicsEffect(fade)
        self.fade_effect = fade

        self.scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self.scroll_animation.setDuration(SCROLL_MS)
        self.scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._emphasis_timer = QTimer(self)
        self._emphasis_timer.setSingleShot(True)
        self._emphasis_timer.timeout.connect(self.clear_emphasis)
        self._emphasis_animation = QVariantAnimation(self)
        self._emphasis_animation.setDuration(EMPHASIS_MS)
        self._emphasis_animation.setStartValue(255)
        self._emphasis_animation.setEndValue(0)
        self._emphasis_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._emphasis_animation.valueChanged.connect(self._fade_emphasis)
        self._pin_bottom = False
        self._keep_from_bottom: int | None = None  # set while a prepend holds the reading position
        self.verticalScrollBar().valueChanged.connect(self._check_top)
        self.verticalScrollBar().rangeChanged.connect(self._range_changed)

    # Theme hooks: QSS sets these with qproperty-shadowColor / qproperty-highlightColor.
    def _get_shadow_color(self) -> QColor:
        return self._shadow_color

    def _set_shadow_color(self, color: QColor) -> None:
        self._shadow_color = QColor(color)
        for row in self.rows:
            effect = row.text_label.graphicsEffect()
            if isinstance(effect, QGraphicsDropShadowEffect) and row not in self.recent_rows:
                effect.setColor(self._shadow_color)

    shadowColor = Property(QColor, _get_shadow_color, _set_shadow_color)

    def _get_highlight_color(self) -> QColor:
        return self._highlight_color

    def _set_highlight_color(self, color: QColor) -> None:
        self._highlight_color = QColor(color)

    highlightColor = Property(QColor, _get_highlight_color, _set_highlight_color)

    # Content
    def set_messages(self, messages: Iterable[NarrativeMessageView], has_older: bool) -> None:
        self.clear_emphasis()
        for widget in (*self.rows, *self.note_rows):
            self._layout.removeWidget(widget)
            widget.deleteLater()
        self.rows, self.note_rows, self.messages = [], [], []
        self._insert(self._layout.count(), tuple(messages))
        self._has_older = has_older
        self._older_pending = False
        self._relayout()
        self._pin_bottom, self._keep_from_bottom = True, None
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def append_turn(self, messages: Iterable[NarrativeMessageView]) -> None:
        self.clear_emphasis()
        added = self._insert(self._layout.count(), tuple(messages))
        self._relayout()
        bar = self.verticalScrollBar()
        self.scroll_animation.stop()
        self._pin_bottom, self._keep_from_bottom = True, None
        if self.reduced_motion:
            bar.setValue(bar.maximum())
        else:
            self.scroll_animation.setStartValue(bar.value())
            self.scroll_animation.setEndValue(bar.maximum())
            self.scroll_animation.start()
        self._emphasize(added)

    def prepend_messages(self, messages: Iterable[NarrativeMessageView], has_older: bool) -> None:
        bar = self.verticalScrollBar()
        self._pin_bottom = False
        value, maximum = bar.value(), bar.maximum()
        self._insert(1, tuple(messages), prepend=True)
        self._has_older = has_older
        # Keep the reading position: the content above grows by exactly the range's growth,
        # so hold the distance from the bottom, including through late layout passes.
        self._keep_from_bottom = maximum - value
        self._relayout()
        bar.setValue(bar.maximum() - self._keep_from_bottom)
        self._older_pending = False

    def older_load_failed(self) -> None:
        """A page of older messages was not loaded; scrolling to the top asks again."""

        self._older_pending = False

    @property
    def has_older(self) -> bool:
        return self._has_older

    def _insert(
        self, index: int, messages: tuple[NarrativeMessageView, ...], *, prepend: bool = False
    ) -> list[ConversationMessage]:
        rows: list[ConversationMessage] = []
        notes: list[ConversationNotes] = []
        width = self._row_width()
        for message in messages:
            row = ConversationMessage(message)
            row.fit_width(width)
            if row.role == "narrator":
                shadow = QGraphicsDropShadowEffect(row.text_label)
                shadow.setBlurRadius(6)
                shadow.setOffset(0, 1)
                shadow.setColor(self._shadow_color)
                row.text_label.setGraphicsEffect(shadow)
            self._layout.insertWidget(index, row)
            row.show()  # layouts show new children on a queued call; we need the height now
            index += 1
            rows.append(row)
            if message.notes:
                note_row = ConversationNotes(message)
                self._layout.insertWidget(index, note_row)
                note_row.show()
                index += 1
                notes.append(note_row)
        if prepend:
            self.rows[:0], self.note_rows[:0], self.messages[:0] = rows, notes, list(messages)
        else:
            self.rows += rows
            self.note_rows += notes
            self.messages += messages
        return rows

    def _relayout(self) -> None:
        """Lay out the thread now, so the scroll range is current before we scroll."""

        self.widget().layout().activate()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)

    def _row_width(self) -> int:
        margins = self._layout.contentsMargins()
        return max(1, self.viewport().width() - margins.left() - margins.right())

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        width = self._row_width()
        for row in self.rows:
            row.fit_width(width)

    def _range_changed(self, _minimum: int, maximum: int) -> None:
        # Late word-wrap layout can grow the range after we scrolled; stay on the newest message.
        if self._keep_from_bottom is not None:
            self.verticalScrollBar().setValue(maximum - self._keep_from_bottom)
            return
        if not self._pin_bottom:
            return
        if self.scroll_animation.state() == QPropertyAnimation.State.Running:
            self.scroll_animation.setEndValue(maximum)
        else:
            self.verticalScrollBar().setValue(maximum)

    # Paging
    def _check_top(self, value: int) -> None:
        bar = self.verticalScrollBar()
        if value < bar.maximum() and self.scroll_animation.state() != QPropertyAnimation.State.Running:
            self._pin_bottom = False
        if self._keep_from_bottom is not None and value != bar.maximum() - self._keep_from_bottom:
            self._keep_from_bottom = None  # the reader scrolled; stop holding the position
        if (
            value == bar.minimum() and bar.maximum() > bar.minimum()
            and self._has_older and not self._older_pending and self.messages
        ):
            self._older_pending = True
            self.older_requested.emit(min(m.turn_number for m in self.messages))

    # New-turn emphasis: three seconds, static under reduced motion (as NarrativePanel).
    def _emphasize(self, rows: list[ConversationMessage]) -> None:
        self.recent_rows = rows
        for row in rows:
            self._set_recent(row, True)
            if not self.reduced_motion and row.role != "narrator":
                glow = QGraphicsDropShadowEffect(row.box)
                glow.setBlurRadius(14)
                glow.setOffset(0, 0)
                glow.setColor(self._highlight_color)
                row.box.setGraphicsEffect(glow)
        if not self.reduced_motion:
            self._emphasis_animation.start()
        self._emphasis_timer.start(EMPHASIS_MS)

    def _fade_emphasis(self, value: object) -> None:
        color = QColor(self._highlight_color)
        color.setAlpha(int(value))
        for row in self.recent_rows:
            effect = row.box.graphicsEffect()
            if row.role != "narrator" and isinstance(effect, QGraphicsDropShadowEffect):
                effect.setColor(color)

    @property
    def emphasis_animating(self) -> bool:
        return self._emphasis_animation.state() == QVariantAnimation.State.Running

    def clear_emphasis(self) -> None:
        self._emphasis_timer.stop()
        self._emphasis_animation.stop()
        for row in self.recent_rows:
            self._set_recent(row, False)
            if row.role != "narrator":
                row.box.setGraphicsEffect(None)
        self.recent_rows = []

    @staticmethod
    def _set_recent(row: ConversationMessage, recent: bool) -> None:
        # The box is the text label for narration, so today's QLabel[recentTurn] style applies.
        for widget in (row, row.box):
            widget.setProperty("recentTurn", recent)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
