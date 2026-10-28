"""Concept T right column: location art, tabs, title and chips, quest or encounter card, choices."""

from __future__ import annotations

import math
from pathlib import Path
import re

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, Property, Signal
from PySide6.QtGui import Qt as GuiQt, QColor, QFontMetricsF, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QScrollArea,
    QApplication,
    QButtonGroup,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dd_simulator.state import CombatAction, CombatCommand
from dd_simulator.ui.item_icons import item_icon_pixmap
from dd_simulator.ui.location_images import resolve_location_image
from dd_simulator.ui.models.presentation import (
    CombatEncounterView,
    LocationSummaryView,
    QuestListItemView,
    QuestView,
)
from dd_simulator.ui.widgets.semantic_button import SemanticButton


NAV_TABS = (
    ("Adventure", "dashboard"),
    ("Map", "map"),
    ("People", "people"),
    ("Character Sheet", "character_sheet"),
    ("Settings", "settings"),
    ("Journal", "journal"),
)
COMBAT_ACTIONS = (
    ("Attack", CombatAction.ATTACK),
    ("Advance", CombatAction.ADVANCE),
    ("Defend", CombatAction.DEFEND),
    ("Use Potion", CombatAction.USE_ITEM),
    ("Negotiate", CombatAction.NEGOTIATE),
    ("Flee", CombatAction.FLEE),
)
TARGETED_ACTIONS = {CombatAction.ATTACK, CombatAction.NEGOTIATE}
# Shown instead of combat actions while a generated encounter is being prepared.
PREPARATION_CHOICES = (
    ("Take Cover (+2 Armor)", "take_cover"),
    ("Scout (+1 Attack)", "scout"),
    ("Charge (Close 15 ft)", "charge"),
)
CHOICE_KEYS = {getattr(Qt.Key, f"Key_{number}"): number for number in range(1, 7)}
TEXT_ENTRY_WIDGETS = (QLineEdit, QTextEdit, QPlainTextEdit)
CHOICE_ICON_SIZE = 22
# Concept T overlay: (position, opacity) of the overlay colour down the art; solid from 82%.
# The 45% stop darkens the top of the conversation band so narration on the brightest art
# stays above 4.5:1 (scripts/check_scene_contrast.py); the art above it is unchanged.
OVERLAY_STOPS = ((0.0, 0.35), (0.12, 0.0), (0.36, 0.25), (0.45, 0.6), (0.62, 0.88), (0.82, 1.0))
ART_FOCUS_Y = 0.3  # crop near the top: CSS background-position center 30%


def time_chip_text(time_label: str) -> str:
    """'Morning, Day 17' -> 'DAY 17 · MORNING'; anything else is shown as given."""

    match = re.fullmatch(r"\s*(.+?),\s*(Day\s+\d+)\s*", time_label, re.IGNORECASE)
    text = f"{match.group(2)} · {match.group(1)}" if match else time_label
    return text.upper()


def danger_chip_text(danger: str) -> str:
    text = danger.strip().upper()
    return text if "DANGER" in text else f"{text} DANGER"


def reward_chips(quest_list: tuple[QuestListItemView, ...]) -> tuple[str, ...]:
    """Reward chips for the selected quest, from the projected reward summary."""

    selected = next((quest for quest in quest_list if quest.selected), None)
    if selected is None or not selected.reward_summary:
        return ()
    return tuple(part.strip().upper() for part in selected.reward_summary.split(",") if part.strip())


def location_art(location: LocationSummaryView) -> Path | None:
    """Registry art when it is usable, otherwise the packaged biome/weather/time variant."""

    visual = location.visual
    if visual is not None and visual.status not in {"pending", "missing"} and visual.path:
        path = Path(visual.path)
        if path.is_file():
            return path
    return resolve_location_image(
        name=location.name,
        biome=location.biome,
        time_label=location.time_label,
        weather=location.weather,
        danger=location.danger,
    )


def _label(text: str, object_name: str, *, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setTextFormat(Qt.TextFormat.PlainText)  # game and model text
    label.setWordWrap(wrap)
    return label


def _shadowed(label: QLabel, blur: int) -> QLabel:
    # ponytail: black text shadow is theme-neutral, add a QSS-driven colour if a light theme lands
    shadow = QGraphicsDropShadowEffect(label)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, 2)
    shadow.setColor(QColor(0, 0, 0, 230))
    label.setGraphicsEffect(shadow)
    return label


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _clear_layout(layout) -> None:  # type: ignore[no-untyped-def]
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())


def shared_width_cap(widths: list[int], room: int) -> int:
    """Largest cap such that sum(min(width, cap)) fits ``room``: narrow items keep their width."""

    remaining = len(widths)
    for width in sorted(widths):
        if width * remaining > room:
            return max(0, room // remaining)
        room -= width
        remaining -= 1
    return max(widths, default=0)


CONVERSATION_MIN_HEIGHT = 150
SCENE_CARD_WIDTH = 340


class NavTabs(QWidget):
    """Adventure / Map / People / Character Sheet / Settings / Journal, plus the clock label."""

    navigation_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("sceneNavTabs")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, ElidedButton] = {}
        for title, target in NAV_TABS:
            button = ElidedButton(title.upper())
            button.setObjectName("sceneNavTab")
            button.setCheckable(True)
            button.setProperty("navigationTarget", target)
            button.setAccessibleName(f"{title} tab")
            button.setToolTip(f"Open {title}")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, value=target: self.navigation_requested.emit(value))
            self.group.addButton(button)
            self.buttons[target] = button
            layout.addWidget(button)
        layout.addStretch(1)
        self.clock_label = ElidedLabel("", "sceneClockLabel", tooltip_on_self=True)
        self.clock_label.setAccessibleDescription("Day and turn")  # the name is the clock text
        layout.addWidget(self.clock_label)
        self.set_current("dashboard")

    def event(self, event) -> bool:  # type: ignore[no-untyped-def]
        kind = event.type()
        if kind == QEvent.Type.StyleChange and self.property("compact"):
            self._set_compact(False)  # theme or font scale changed: measure the full padding again
        # LayoutRequest follows a font, text or width change of any tab, so the caps follow too.
        if kind in (QEvent.Type.LayoutRequest, QEvent.Type.Resize):
            self._fit_tabs()
        return super().event(event)

    def _set_compact(self, compact: bool) -> None:
        self.setProperty("compact", compact)  # QSS narrows the tab padding
        for button in self.buttons.values():
            _repolish(button)

    def _fit_tabs(self) -> None:
        """Short labels keep their natural width; one shared cap makes only the longest elide.

        A box layout takes the same width from every item, so short tabs such as MAP were the
        first to shrink to an ellipsis. Tabs that do not fit at full padding go compact first.
        """

        items = [*self.buttons.values(), self.clock_label]
        room = self.width() - self.layout().spacing() * (len(items) - 1)
        hints = [item.sizeHint().width() for item in items]
        compact = bool(self.property("compact"))
        if not compact:
            self._natural_width = sum(hints)  # remembered so compact padding cannot flip it back
        if (self._natural_width > room) != compact:
            self._set_compact(not compact)
            return  # the repolish posts another LayoutRequest with the new hints
        cap = shared_width_cap(hints, room)
        for item in items:
            item.setMaximumWidth(max(cap, item.minimumSizeHint().width()))

    def set_current(self, target: str) -> None:
        button = self.buttons.get(target)
        if button is not None:
            button.setChecked(True)


class ProgressRing(QWidget):
    """Completed / total ring; colours come from QSS qproperties."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("questProgressRing")
        self.setFixedSize(46, 46)
        self.completed = 0
        self.total = 0
        self._ring = QColor("#d9b46c")
        self._track = QColor("#3a2e1d")
        self._hole = QColor("#16120d")
        self._text = QColor("#ecdfc3")

    @property
    def fraction(self) -> float:
        return self.completed / self.total if self.total else 0.0

    def set_progress(self, completed: int, total: int) -> None:
        self.completed, self.total = completed, total
        self.setAccessibleName(f"Quest progress {completed} of {total} objectives")
        self.update()

    def _color_property(name: str):  # type: ignore[no-untyped-def]
        def getter(self) -> QColor:  # type: ignore[no-untyped-def]
            return getattr(self, name)

        def setter(self, value: QColor) -> None:  # type: ignore[no-untyped-def]
            setattr(self, name, QColor(value))
            self.update()

        return Property(QColor, getter, setter)

    ringColor = _color_property("_ring")
    trackColor = _color_property("_track")
    holeColor = _color_property("_hole")
    textColor = _color_property("_text")

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        pen = QPen(self._track, 5)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.setBrush(self._hole)
        painter.drawEllipse(ring)
        if self.fraction > 0:
            pen.setColor(self._ring)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(ring, 90 * 16, -round(self.fraction * 360 * 16))
        painter.setPen(self._text)
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self.completed}/{self.total}")


class DiamondMarker(QWidget):
    """Objective diamond in the QSS text colour: outlined while open, filled once complete."""

    def __init__(self, completed: bool) -> None:
        super().__init__()
        self.setObjectName("questObjectiveMarker")
        self.setProperty("completed", completed)
        self.completed = completed
        self.setFixedSize(12, 16)

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.palette().color(self.foregroundRole())
        painter.setPen(QPen(color, 1))
        painter.setBrush(color if self.completed else Qt.BrushStyle.NoBrush)
        cx, cy, r = 6.0, 9.0, 5.0
        painter.drawPolygon([QPointF(cx, cy - r), QPointF(cx + r, cy), QPointF(cx, cy + r), QPointF(cx - r, cy)])


class _SceneCard(QFrame):
    """Shared translucent frame for the quest and encounter cards."""

    def __init__(self, object_name: str, heading: str) -> None:
        super().__init__()
        self.setObjectName(object_name)
        self.setProperty("sceneCard", True)
        self.setMaximumWidth(SCENE_CARD_WIDTH)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(12, 10, 12, 10)
        self.body.setSpacing(4)
        self.heading = _label(heading.upper(), "sceneCardHeading")
        self.body.addWidget(self.heading)


class QuestProgressCard(_SceneCard):
    def __init__(self, quest: QuestView, rewards: tuple[str, ...] = ()) -> None:
        super().__init__("questProgressCard", "Quest progress")
        header = QHBoxLayout()
        header.setSpacing(10)
        self.ring = ProgressRing()
        header.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(1)
        self.title = _label("", "questCardTitle", wrap=True)
        self.summary = _label("", "questCardSummary", wrap=True)
        text.addWidget(self.title)
        text.addWidget(self.summary)
        header.addLayout(text, 1)
        self.body.addLayout(header)
        self.objectives_layout = QVBoxLayout()
        self.objectives_layout.setSpacing(2)
        self.body.addLayout(self.objectives_layout)
        self.rewards_layout = QHBoxLayout()
        self.rewards_layout.setSpacing(6)
        self.body.addLayout(self.rewards_layout)
        self.objective_rows: list[QLabel] = []
        self.reward_labels: list[QLabel] = []
        self.set_quest(quest, rewards)

    def set_quest(self, quest: QuestView, rewards: tuple[str, ...] = ()) -> None:
        done = sum(objective.completed for objective in quest.objectives)
        self.ring.set_progress(done, len(quest.objectives))
        self.title.setText(quest.title)
        self.summary.setText(quest.summary)
        self.setAccessibleName(f"Quest progress: {quest.title}, {done} of {len(quest.objectives)} objectives")
        _clear_layout(self.objectives_layout)
        _clear_layout(self.rewards_layout)
        self.objective_rows = []
        for objective in quest.objectives:
            text = f"Optional · {objective.text}" if objective.optional else objective.text
            line = QHBoxLayout()
            line.setSpacing(8)
            marker = DiamondMarker(objective.completed)
            line.addWidget(marker, 0, Qt.AlignmentFlag.AlignTop)
            row = _label(text, "questObjective", wrap=True)
            row.setProperty("completed", objective.completed)
            row.setAccessibleName(f"{text}, {'complete' if objective.completed else 'not complete'}")
            line.addWidget(row, 1)
            self.objectives_layout.addLayout(line)
            self.objective_rows.append(row)
        self.reward_labels = [_label(reward, "questRewardChip") for reward in rewards]
        for chip in self.reward_labels:
            chip.setAccessibleName(f"Reward {chip.text()}")
            self.rewards_layout.addWidget(chip)
        self.rewards_layout.addStretch(1)


class _CombatantRow(QFrame):
    """One combatant; an enemy row is a target button when several enemies are active (D2)."""

    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.property("targetable"):
            self.clicked.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.property("targetable") and event.key() in (
            Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space,
        ):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


def active_enemy_ids(encounter: CombatEncounterView) -> tuple[str, ...]:
    """Active enemies by initiative; the first is the automatic target."""

    return tuple(
        c.id
        for c in sorted(encounter.combatants, key=lambda c: -c.initiative)
        if c.side == "enemy" and c.status == "active"
    )


class EncounterCard(_SceneCard):
    target_selected = Signal(str)

    def __init__(self, encounter: CombatEncounterView, target_id: str | None = None) -> None:
        super().__init__("encounterCard", "Encounter")
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(5)
        self.body.addLayout(self.rows_layout)
        self.set_encounter(encounter, target_id)

    def set_encounter(self, encounter: CombatEncounterView, target_id: str | None = None) -> None:
        self.heading.setText(f"ENCOUNTER · ROUND {encounter.round_number}")
        self.setAccessibleName(f"Encounter, round {encounter.round_number}: {encounter.environment}")
        _clear_layout(self.rows_layout)
        self.health_bars: dict[str, QProgressBar] = {}
        self.rows: dict[str, _CombatantRow] = {}
        enemy_ids = active_enemy_ids(encounter)
        pickable = len(enemy_ids) > 1
        for combatant in sorted(encounter.combatants, key=lambda c: -c.initiative):
            row = _CombatantRow()
            row.setObjectName("encounterCombatant")
            row.setProperty("combatSide", combatant.side)
            row.setProperty("activeTurn", combatant.active_turn)
            targetable = pickable and combatant.id in enemy_ids
            row.setProperty("targetable", targetable)
            row.setProperty("targetSelected", targetable and combatant.id == target_id)
            if targetable:
                row.setCursor(Qt.CursorShape.PointingHandCursor)
                row.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                row.setToolTip(GuiQt.convertFromPlainText(f"Target {combatant.name}"))
                row.clicked.connect(lambda cid=combatant.id: self.target_selected.emit(cid))
            grid = QGridLayout(row)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(1)
            grid.addWidget(_label(combatant.name, "encounterCombatantName"), 0, 0)
            stats = (
                f"AC {combatant.armor_class} · INIT {combatant.initiative} · {combatant.distance_feet} FT"
            )
            grid.addWidget(_label(stats, "encounterCombatantStats"), 0, 1, Qt.AlignmentFlag.AlignRight)
            bar = QProgressBar()
            bar.setObjectName("encounterHealthBar")
            bar.setProperty("combatSide", combatant.side)
            bar.setRange(0, max(1, combatant.maximum_health))
            bar.setValue(max(0, combatant.current_health))
            bar.setTextVisible(False)
            bar.setAccessibleName(
                f"{combatant.name} health {combatant.current_health} of {combatant.maximum_health}"
            )
            grid.addWidget(bar, 1, 0, 1, 2)
            details = [*combatant.conditions]
            if combatant.declared_intent:
                details.insert(0, f"Intent: {combatant.declared_intent}")
            if details:
                grid.addWidget(_label(" · ".join(details), "encounterIntent", wrap=True), 2, 0, 1, 2)
            row.setAccessibleName(
                f"{combatant.name}, {combatant.side}, {combatant.current_health} of "
                f"{combatant.maximum_health} health, {stats}"
            )
            self.rows_layout.addWidget(row)
            self.health_bars[combatant.id] = bar
            self.rows[combatant.id] = row

    def mark_target(self, target_id: str | None) -> None:
        for combatant_id, row in self.rows.items():
            row.setProperty(
                "targetSelected", bool(row.property("targetable")) and combatant_id == target_id
            )
            _repolish(row)


class ElidedLabel(QLabel):
    """Single-line label that elides to its width and exposes the full text as a tooltip.

    The tooltip goes on the parent (for labels inside a button) unless ``tooltip_on_self``.
    Its size hint is the full text, so layouts give it room before it elides.
    """

    def __init__(self, text: str, object_name: str, *, tooltip_on_self: bool = False) -> None:
        super().__init__()
        self.setObjectName(object_name)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.tooltip_on_self = tooltip_on_self
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.full_text = text
        self._refresh()

    def set_full_text(self, text: str) -> None:
        self.full_text = text
        self._refresh()

    def sizeHint(self) -> QSize:  # noqa: N802
        return _with_text_width(self, super().sizeHint(), self.full_text)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return _with_text_width(self, super().minimumSizeHint(), ELLIPSIS)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._refresh()

    def changeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._refresh()

    def _refresh(self) -> None:
        width = self.contentsRect().width()
        shown = self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideRight, width)
        if shown != self.text():
            self.setText(shown)
        owner = None if self.tooltip_on_self else self.parentWidget()
        tip = GuiQt.convertFromPlainText(self.full_text) if shown != self.full_text else ""
        (owner if owner is not None else self).setToolTip(tip)
        _name_full_text(self)


class ElidedButton(QPushButton):
    """Push button that elides its own text to the space inside its padding."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.full_text = text
        self._refresh()

    def sizeHint(self) -> QSize:  # noqa: N802
        return _with_text_width(self, super().sizeHint(), self.full_text)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        # Not super().minimumSizeHint(): QPushButton's calls our sizeHint (the full text), which
        # made the minimum grow as the shown text got shorter.
        return _with_text_width(self, super().sizeHint(), ELLIPSIS)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._refresh()

    def changeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._refresh()

    def _refresh(self) -> None:
        option = QStyleOptionButton()
        self.initStyleOption(option)
        width = self.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, self).width()
        shown = self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideRight, width)
        if shown != self.text():
            self.setText(shown)
        _name_full_text(self)


ELLIPSIS = "…"


def _name_full_text(widget) -> None:  # type: ignore[no-untyped-def]
    """Screen readers get the full text, not the elided one, unless a caller named the widget."""

    if widget.accessibleName() == getattr(widget, "_auto_name", ""):
        widget._auto_name = widget.full_text
        widget.setAccessibleName(widget.full_text)


def _with_text_width(widget: QWidget, hint: QSize, text: str) -> QSize:
    """``hint`` with the width of the shown text swapped for the width of ``text``."""

    metrics = widget.fontMetrics()
    # Rounded up: elidedText compares the fractional width, so a rounded-down hint elides "MAP".
    full = math.ceil(QFontMetricsF(widget.font()).horizontalAdvance(text))
    width = hint.width() - metrics.horizontalAdvance(widget.text()) + full
    return QSize(max(0, width), hint.height())


class ChoiceButton(QPushButton):
    def __init__(self, number: int) -> None:
        super().__init__()
        self.setObjectName("sceneChoiceButton")
        self.number = number
        self.setMinimumHeight(38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)
        self.icon_label = QLabel()
        self.icon_label.setObjectName("sceneChoiceIcon")
        self.icon_label.setFixedSize(CHOICE_ICON_SIZE, CHOICE_ICON_SIZE)
        self.text_label = ElidedLabel("", "sceneChoiceText")
        # Two equal columns: a long choice must not take width from its neighbour.
        self.text_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.key_label = _label(str(number), "sceneChoiceKey")
        for child in (self.icon_label, self.text_label, self.key_label):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label, 1)
        layout.addWidget(self.key_label)

    def set_choice(self, text: str) -> None:
        self.text_label.set_full_text(text)
        self.icon_label.setPixmap(item_icon_pixmap(text, context="action", size=CHOICE_ICON_SIZE))
        self.setAccessibleName(f"Choice {self.number}: {text}")
        self.setAccessibleDescription(f"Press {self.number} to choose")


class ChoiceGrid(QWidget):
    """Six numbered choices in two columns, the wide action input and ACT.

    Signals and progress/cancel/retry behaviour match ``NarrativePanel``.
    """

    submission_requested = Signal(str)
    cancellation_requested = Signal()
    retry_requested = Signal(str)
    combat_action_requested = Signal(object)

    def __init__(self, suggestions: tuple[str, ...] = (), *, actor: str | None = None) -> None:
        super().__init__()
        self.setObjectName("choiceGrid")
        self.combat_actions: tuple[tuple[str, CombatAction], ...] = ()
        self.target_id: str | None = None
        self._placeholder = f"Or write what {actor} does…" if actor else "Or describe your action…"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        self.choice_buttons: list[ChoiceButton] = []
        for index in range(6):
            button = ChoiceButton(index + 1)
            button.clicked.connect(lambda _checked=False, number=index + 1: self.activate_choice(number))
            grid.addWidget(button, index // 2, index % 2)
            self.choice_buttons.append(button)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.action_input = QLineEdit()
        self.action_input.setObjectName("sceneActionInput")
        self.action_input.setAccessibleName("Player action")
        self.action_input.setPlaceholderText(self._placeholder)
        self.action_input.setMaxLength(2000)
        self.action_input.setToolTip("Submit a non-combat action for local model resolution")
        self.action_input.returnPressed.connect(self._request_submission)
        row.addWidget(self.action_input, 1)
        self.submit_button = SemanticButton("ACT", role="primary", object_name="sceneActButton")
        self.submit_button.setAccessibleName("Act")
        self.submit_button.clicked.connect(self._request_submission)
        row.addWidget(self.submit_button)
        self.cancel_button = SemanticButton("Cancel", role="destructive", object_name="cancelActionButton")
        self.cancel_button.setToolTip("Cancel this turn; generated changes will not be committed")
        self.cancel_button.clicked.connect(self._request_cancellation)
        self.cancel_button.setVisible(False)
        row.addWidget(self.cancel_button)
        self.retry_button = SemanticButton("Retry", role="secondary", object_name="retryActionButton")
        self.retry_button.setToolTip("Retry the unchanged player action")
        self.retry_button.clicked.connect(lambda: self.retry_requested.emit(self.action_input.text()))
        self.retry_button.setVisible(False)
        row.addWidget(self.retry_button)
        layout.addLayout(row)
        self.feedback = _label("", "actionFeedback")
        self.feedback.setProperty("textRole", "muted")
        self.feedback.setAccessibleName("Action submission feedback")
        self.feedback.setVisible(False)
        layout.addWidget(self.feedback)
        self.set_choices(suggestions)

    # Choices -----------------------------------------------------------------

    def set_choices(self, suggestions: tuple[str, ...]) -> None:
        self.combat_actions = ()
        self._set_texts(tuple(suggestions[:6]))
        self.action_input.setEnabled(True)
        self.submit_button.setEnabled(True)
        self.action_input.setPlaceholderText(self._placeholder)
        self.action_input.setToolTip("Submit a non-combat action for local model resolution")

    def set_combat_actions(
        self, actions: tuple[tuple[str, CombatAction], ...] = COMBAT_ACTIONS, *, enabled: bool = True
    ) -> None:
        """Swap the choices for combat actions and lock free text, as during combat today."""

        self.combat_actions = tuple(actions[:6])
        self._set_texts(tuple(label for label, _action in self.combat_actions))
        for button in self.choice_buttons:
            button.setEnabled(enabled and not button.isHidden())
        self.set_combat_active(True)

    def set_combat_active(self, active: bool) -> None:
        self.action_input.setEnabled(not active)
        self.submit_button.setEnabled(not active)
        if active:
            self.action_input.setPlaceholderText("Choose a combat action while an encounter is active")
            self.action_input.setToolTip("Combat actions are validated through the deterministic combat rules")

    def _set_texts(self, texts: tuple[str, ...]) -> None:
        for index, button in enumerate(self.choice_buttons):
            present = index < len(texts)
            button.setVisible(present)
            button.setEnabled(present)
            if present:
                button.set_choice(texts[index])

    def activate_choice(self, number: int) -> None:
        if not 1 <= number <= 6:
            return
        button = self.choice_buttons[number - 1]
        if button.isHidden() or not button.isEnabled():
            return
        if self.combat_actions:
            action = self.combat_actions[number - 1][1]
            if action is CombatAction.PREPARE:
                preparation = PREPARATION_CHOICES[number - 1][1]
                self.combat_action_requested.emit(CombatCommand(action, preparation=preparation))
                return
            target = self.target_id if action in TARGETED_ACTIONS else None
            self.combat_action_requested.emit(CombatCommand(action, target_id=target))
            return
        text = button.text_label.full_text
        self.action_input.setText(text)
        self.submission_requested.emit(text)

    # Keys 1-6 ----------------------------------------------------------------

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        QApplication.instance().installEventFilter(self)

    def hideEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        QApplication.instance().removeEventFilter(self)
        super().hideEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() in CHOICE_KEYS
            and event.modifiers() in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.KeypadModifier)
            and isinstance(watched, QWidget)
            and watched.window() is self.window()
            and self.isVisible()
            and not isinstance(QApplication.focusWidget(), TEXT_ENTRY_WIDGETS)
        ):
            self.activate_choice(CHOICE_KEYS[event.key()])
            return True
        return False

    # NarrativePanel-equivalent progress, cancel and retry ----------------------

    def _request_submission(self) -> None:
        self.submission_requested.emit(self.action_input.text())

    def _request_cancellation(self) -> None:
        self.cancel_button.setEnabled(False)
        self._feedback("warning", "Cancelling after the local model returns; no turn will be committed...")
        self.cancellation_requested.emit()

    def show_submission_feedback(self, text: str) -> None:
        self.action_input.clear()
        self.action_input.setProperty("validationState", "valid")
        self._feedback("success", f"Local action accepted: {text}")

    def show_validation_error(self, message: str) -> None:
        self.action_input.setProperty("validationState", "error")
        self._feedback("error", message)
        self.action_input.setFocus()

    def show_resolution_pending(self, action: str) -> None:
        self.action_input.setText(action)
        self.action_input.setEnabled(False)
        self.submit_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setVisible(True)
        self.retry_button.setVisible(False)
        self._feedback("warning", "Resolving this non-combat action with the local model...")

    def show_resolution_error(self, message: str) -> None:
        self._resolution_ended()
        self._feedback("error", message)
        self.action_input.setFocus()

    def show_resolution_cancelled(self) -> None:
        self._resolution_ended()
        self._feedback("warning", "Action cancelled; no state was changed.")
        self.action_input.setFocus()

    def reset_resolution_controls(self) -> None:
        self.action_input.clear()
        self.action_input.setEnabled(True)
        self.submit_button.setEnabled(True)
        self.cancel_button.setVisible(False)
        self.retry_button.setVisible(False)
        self._feedback("", "")

    def _resolution_ended(self) -> None:
        self.action_input.setEnabled(True)
        self.submit_button.setEnabled(True)
        self.cancel_button.setVisible(False)
        self.retry_button.setVisible(True)

    def _feedback(self, state: str, text: str) -> None:
        self.feedback.setProperty("feedbackState", state)
        self.feedback.setText(text)
        self.feedback.setVisible(bool(text))
        for widget in (self.action_input, self.feedback):
            _repolish(widget)


class SceneView(QWidget):
    """The right column: painted location art with overlay, holding every scene widget."""

    navigation_requested = Signal(str)
    submission_requested = Signal(str)
    cancellation_requested = Signal()
    retry_requested = Signal(str)
    combat_action_requested = Signal(object)

    def __init__(
        self,
        location: LocationSummaryView,
        quest: QuestView,
        suggestions: tuple[str, ...] = (),
        *,
        quest_list: tuple[QuestListItemView, ...] = (),
        combat: CombatEncounterView | None = None,
        actor: str | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("sceneView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._overlay = QColor("#120e0a")
        self._art: QPixmap | None = None
        self.image_path: Path | None = None
        self._suggestions = tuple(suggestions)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 16)
        layout.setSpacing(0)

        self.tabs = NavTabs()
        self.tabs.navigation_requested.connect(self.navigation_requested)
        layout.addWidget(self.tabs)

        location_row = QHBoxLayout()
        location_row.setContentsMargins(4, 10, 0, 0)
        location_row.setSpacing(16)
        heading = QVBoxLayout()
        heading.setSpacing(2)
        # Wraps rather than clipping long names when the column is narrow.
        self.title = _shadowed(_label("", "sceneLocationTitle", wrap=True), 14)
        self.subtitle = _shadowed(_label("", "sceneLocationSubtitle", wrap=True), 8)
        heading.addWidget(self.title)
        heading.addWidget(self.subtitle)
        chips = QHBoxLayout()
        chips.setContentsMargins(0, 6, 0, 0)
        chips.setSpacing(6)
        self.time_chip = ElidedLabel("", "sceneChip", tooltip_on_self=True)
        self.weather_chip = ElidedLabel("", "sceneChip", tooltip_on_self=True)
        self.danger_chip = ElidedLabel("", "sceneChip", tooltip_on_self=True)
        for kind, chip in (("time", self.time_chip), ("weather", self.weather_chip), ("danger", self.danger_chip)):
            chip.setProperty("chipKind", kind)
            chips.addWidget(chip)
        chips.addStretch(1)
        heading.addLayout(chips)
        heading.addStretch(1)
        location_row.addLayout(heading, 1)
        self.quest_card = QuestProgressCard(quest, reward_chips(quest_list))
        self.encounter_card: EncounterCard | None = None
        # The card scrolls rather than squeezing the conversation on short windows.
        self.card_scroll = QScrollArea()
        self.card_scroll.setObjectName("sceneCardScroll")
        self.card_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.card_scroll.setWidgetResizable(True)
        self.card_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.card_scroll.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.card_scroll.setFixedWidth(SCENE_CARD_WIDTH)
        self.card_scroll.viewport().setAutoFillBackground(False)
        cards = QWidget()
        cards.setObjectName("sceneCardHost")
        cards.setAutoFillBackground(False)
        self.card_slot = QVBoxLayout(cards)
        self.card_slot.setContentsMargins(0, 0, 0, 0)
        self.card_slot.addWidget(self.quest_card)
        self.card_slot.addStretch(1)
        self.card_scroll.setWidget(cards)
        location_row.addWidget(self.card_scroll)
        layout.addLayout(location_row)

        self.conversation_slot = QVBoxLayout()
        self.conversation_slot.setContentsMargins(4, 10, 0, 10)
        self.conversation_placeholder = QFrame()
        self.conversation_placeholder.setObjectName("sceneConversationPlaceholder")
        self.conversation_placeholder.setAccessibleName("Conversation")
        self.conversation_slot.addWidget(self.conversation_placeholder)
        layout.addLayout(self.conversation_slot, 1)

        self.choice_grid = ChoiceGrid(suggestions, actor=actor)
        self.choice_grid.setContentsMargins(4, 0, 0, 0)
        for name in ("submission_requested", "cancellation_requested", "retry_requested", "combat_action_requested"):
            getattr(self.choice_grid, name).connect(getattr(self, name))
        layout.addWidget(self.choice_grid)

        self.set_location(location)
        self.set_combat(combat)

    def overlayColor(self) -> QColor:  # noqa: N802 - Qt property name used from QSS
        return self._overlay

    def setOverlayColor(self, value: QColor) -> None:  # noqa: N802
        self._overlay = QColor(value)
        self.update()

    overlayColor = Property(QColor, overlayColor, setOverlayColor)  # type: ignore[assignment]

    def set_location(self, location: LocationSummaryView) -> None:
        """Refresh title, chips and art; call again when location, weather or time changes."""

        self.title.setText(location.name)
        self.title.setAccessibleName(f"Location: {location.name}")
        self.subtitle.setText(" · ".join(part for part in (location.region, location.route_status) if part).upper())
        self.time_chip.set_full_text(time_chip_text(location.time_label))
        self.weather_chip.set_full_text(location.weather.upper())
        self.danger_chip.set_full_text(danger_chip_text(location.danger))
        self.danger_chip.setProperty("dangerLevel", "low" if "low" in location.danger.casefold() else "elevated")
        _repolish(self.danger_chip)
        day = re.search(r"Day\s+\d+", location.time_label, re.IGNORECASE)
        if not self.tabs.clock_label.full_text and day:
            self.tabs.clock_label.set_full_text(day.group(0).upper())
        path = location_art(location)
        if path != self.image_path:
            self.image_path = path
            pixmap = QPixmap(str(path)) if path is not None else QPixmap()
            self._art = None if pixmap.isNull() else pixmap
            self.update()
        self.setAccessibleName(f"Scene: {location.name}")

    def set_clock(self, day: int, turn: int) -> None:
        self.tabs.clock_label.set_full_text(f"DAY {day} · TURN {turn}")

    def set_quest(self, quest: QuestView, quest_list: tuple[QuestListItemView, ...] = ()) -> None:
        self.quest_card.set_quest(quest, reward_chips(quest_list))

    def set_suggestions(self, suggestions: tuple[str, ...]) -> None:
        self._suggestions = tuple(suggestions)
        if not self.choice_grid.combat_actions:
            self.choice_grid.set_choices(self._suggestions)

    def set_combat(self, encounter: CombatEncounterView | None) -> None:
        """Active encounter: Encounter card and combat actions. Otherwise: quest card and choices (D2)."""

        if encounter is not None and encounter.status == "active":
            enemy_ids = active_enemy_ids(encounter)
            if self.choice_grid.target_id not in enemy_ids:
                self.choice_grid.target_id = enemy_ids[0] if enemy_ids else None
            if self.encounter_card is None:
                self.encounter_card = EncounterCard(encounter, self.choice_grid.target_id)
                self.encounter_card.target_selected.connect(self.select_target)
                self.card_slot.insertWidget(0, self.encounter_card)
            else:
                self.encounter_card.set_encounter(encounter, self.choice_grid.target_id)
            self.encounter_card.show()
            self.quest_card.hide()
            if encounter.generated and not encounter.intro_complete:
                self.choice_grid.set_combat_actions(
                    tuple((label, CombatAction.PREPARE) for label, _key in PREPARATION_CHOICES)
                )
                return
            player_turn = any(c.side == "player" and c.active_turn for c in encounter.combatants)
            self.choice_grid.set_combat_actions(COMBAT_ACTIONS, enabled=player_turn)
            return
        if self.encounter_card is not None:
            self.encounter_card.hide()
        self.quest_card.show()
        self.choice_grid.target_id = None
        self.choice_grid.set_choices(self._suggestions)

    def select_target(self, target_id: str | None) -> None:
        """Pick the enemy for attacks and casts; ignored unless it is an active, pickable enemy."""

        card = self.encounter_card
        if card is None or card.isHidden() or target_id not in card.rows:
            return
        if not card.rows[target_id].property("targetable"):
            return
        self.choice_grid.target_id = target_id
        card.mark_target(target_id)

    def set_conversation(self, widget: QWidget) -> None:
        """Phase 6 puts the ConversationView here, replacing the placeholder."""

        self.conversation_slot.removeWidget(self.conversation_placeholder)
        self.conversation_placeholder.deleteLater()
        self.conversation_placeholder = widget
        widget.setMinimumHeight(CONVERSATION_MIN_HEIGHT)
        self.conversation_slot.addWidget(widget)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        # Narrow scene (1280 px window): the card yields width to the location heading.
        width = round(0.45 * (self.width() - 40))
        self.card_scroll.setFixedWidth(max(240, min(SCENE_CARD_WIDTH, width)))

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        paint_backdrop(QPainter(self), self.rect(), self._art, self._overlay)


def paint_backdrop(painter: QPainter, rect, art: QPixmap | None, overlay: QColor) -> None:  # type: ignore[no-untyped-def]
    """Cover-fit ``art`` into ``rect`` under the overlay gradient (also used by check_scene_contrast)."""

    if art is not None:
        scaled = art.size().scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding)
        x = (scaled.width() - rect.width()) / 2
        y = (scaled.height() - rect.height()) * ART_FOCUS_Y
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(QRectF(-x, -y, scaled.width(), scaled.height()), art, QRectF(art.rect()))
    gradient = QLinearGradient(QPointF(0, 0), QPointF(0, rect.height()))
    for position, alpha in OVERLAY_STOPS:
        color = QColor(overlay)
        color.setAlphaF(alpha)
        gradient.setColorAt(position, color)
    gradient.setColorAt(1.0, overlay)
    painter.fillRect(rect, gradient)
