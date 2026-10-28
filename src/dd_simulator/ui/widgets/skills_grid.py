"""Configurable skills grid with level, XP, bonus, and lock metadata."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QHBoxLayout,
    QProgressBar,
    QSizePolicy,
    QWidget,
    QVBoxLayout,
)

from dd_simulator.ui.models.presentation import CombatActionOptionView, SkillView
from dd_simulator.ui.item_icons import item_icon_label, refresh_item_icon
from dd_simulator.ui.widgets.hover_card import PositionedHoverCard


class AbilityHoverCard(PositionedHoverCard):
    def __init__(self, action: CombatActionOptionView, parent: QWidget) -> None:
        super().__init__(parent, object_name="abilityHoverCard", card_kind=action.kind)
        self.setProperty("available", action.available)
        self.setMinimumWidth(460)
        self.setMaximumWidth(600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(7)

        title = QLabel(action.name)
        title.setObjectName("hoverCardTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        classification = QLabel(action.kind.upper())
        classification.setObjectName("hoverCardClassification")
        classification.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(classification)

        divider = QFrame()
        divider.setObjectName("hoverCardDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)

        body = QHBoxLayout()
        icon = item_icon_label(
            action.name,
            category="spell" if action.kind.casefold() == "spell" else "skill",
            context=f"{action.kind} {action.description}",
            size=82,
            object_name="abilityHoverIcon",
        )
        body.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
        stats = QGridLayout()
        stats.setHorizontalSpacing(16)
        stats.setVerticalSpacing(3)
        for index, (name, value) in enumerate(action.stats):
            row, column = index % 5, (index // 5) * 2
            label = QLabel(f"{name}:")
            label.setObjectName("abilityHoverStatName")
            detail = QLabel(value or "None")
            detail.setObjectName("abilityHoverStatValue")
            detail.setWordWrap(True)
            stats.addWidget(label, row, column)
            stats.addWidget(detail, row, column + 1)
        body.addLayout(stats, 1)
        layout.addLayout(body)

        if action.unavailable_reason:
            unavailable = QLabel(f"Unavailable: {action.unavailable_reason}")
            unavailable.setObjectName("abilityHoverUnavailable")
            unavailable.setWordWrap(True)
            layout.addWidget(unavailable)

        divider = QFrame()
        divider.setObjectName("hoverCardDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)
        description = QLabel(action.description or "No description is available.")
        description.setObjectName("abilityHoverDescription")
        description.setWordWrap(True)
        font = description.font(); font.setItalic(True); description.setFont(font)
        layout.addWidget(description)


def skill_tooltip(skill: SkillView) -> str:
    tooltip = [f"{skill.name}: level {skill.level}"]
    if skill.next_level_xp:
        tooltip.append(f"XP: {skill.current_xp} / {skill.next_level_xp}")
    if skill.bonus:
        tooltip.append(f"Temporary bonus: +{skill.bonus}")
    if skill.locked:
        tooltip.append("Locked")
    if skill.recently_increased:
        tooltip.append("Recently increased")
    return "\n".join(tooltip)


class SkillGridItem(QFrame):
    def __init__(self, skill: SkillView) -> None:
        super().__init__()
        self.setObjectName("skillGridItem")
        self.setProperty("locked", skill.locked)
        self.setProperty("recentlyIncreased", skill.recently_increased)
        self.setAccessibleName(f"{skill.name}, level {skill.level}")
        self.setMinimumHeight(42)
        self.setMaximumHeight(48)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 2, 3, 2)
        layout.setSpacing(1)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.icon_label = item_icon_label(
            skill.name,
            category="skill",
            context="player skill",
            size=24,
            object_name="skillIcon",
        )
        name = QLabel(skill.name)
        name.setObjectName("skillName")
        level = QLabel(str(skill.level))
        level.setObjectName("skillLevel")
        level.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.icon_label)
        row.addWidget(name, 1)
        row.addWidget(level)
        layout.addLayout(row)

        progress = QProgressBar()
        progress.setObjectName("skillExperienceBar")
        progress.setRange(0, max(1, skill.next_level_xp))
        progress.setValue(min(skill.current_xp, progress.maximum()))
        progress.setTextVisible(False)
        progress.setFixedHeight(3)
        progress.setAccessibleName(
            f"{skill.name} experience {skill.current_xp} of {skill.next_level_xp}"
        )
        layout.addWidget(progress)

        self.setToolTip(skill_tooltip(skill))
        self._icon_name = skill.name

    def refresh_theme_icon(self) -> None:
        refresh_item_icon(
            self.icon_label,
            self._icon_name,
            category="skill",
            context="player skill",
        )


class SkillsGrid(QWidget):
    ITEM_PITCH = 54

    def __init__(
        self,
        skills: tuple[SkillView, ...],
        *,
        columns: int = 2,
        vertical_fill: bool = False,
    ) -> None:
        super().__init__()
        self.setObjectName("skillsGrid")
        self.skills = skills
        self.columns = max(1, columns)
        self.vertical_fill = vertical_fill
        self._row_capacity = 0
        vertical_policy = (
            QSizePolicy.Policy.Expanding
            if vertical_fill
            else QSizePolicy.Policy.Maximum
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, vertical_policy)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(3)
        self.grid.setVerticalSpacing(6)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        for column in range(self.columns):
            self.grid.setColumnStretch(column, 1)
        if not skills:
            empty = QLabel("No skills available")
            empty.setObjectName("skillsGridEmptyState")
            empty.setToolTip("Skills will appear when supplied by the campaign rules")
            self.grid.addWidget(empty, 0, 0)
            return
        initial_capacity = (
            (len(skills) + self.columns - 1) // self.columns
            if vertical_fill
            else 0
        )
        self._populate(initial_capacity)

    def _populate(self, row_capacity: int) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._row_capacity = max(1, row_capacity) if self.vertical_fill else 0
        for index, skill in enumerate(self.skills):
            if self.vertical_fill:
                column = index // self._row_capacity
                if column >= self.columns:
                    column = self.columns - 1
                    row = index - (self.columns - 1) * self._row_capacity
                else:
                    row = index % self._row_capacity
            else:
                row = index // self.columns
                column = index % self.columns
            self.grid.addWidget(SkillGridItem(skill), row, column)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if not self.vertical_fill or not self.skills:
            return
        row_capacity = max(
            1,
            (event.size().height() + self.grid.verticalSpacing()) // self.ITEM_PITCH,
        )
        row_capacity = min(row_capacity, len(self.skills))
        if row_capacity != self._row_capacity:
            self._populate(row_capacity)


class _LegacyCombatSkillsGrid(QWidget):
    """Compact, separate list of all unlocked combat abilities and spells."""

    def __init__(self, actions: tuple[CombatActionOptionView, ...]) -> None:
        super().__init__()
        self.setObjectName("combatSkillsGrid")
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        if not actions:
            layout.addWidget(QLabel("No combat abilities unlocked"), 0, 0)
            return
        for index, action in enumerate(actions):
            card = QFrame()
            card.setObjectName("combatSkillItem")
            card.setProperty("available", action.available)
            card.setMinimumHeight(58)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(6, 4, 6, 4)
            title = QLabel(f"{action.name}  ·  {action.kind.title()}")
            title.setObjectName("combatSkillName")
            detail = QLabel(action.resource_label)
            detail.setObjectName("combatSkillCost")
            detail.setWordWrap(True)
            card_layout.addWidget(title)
            card_layout.addWidget(detail)
            card.setToolTip(
                action.description
                + (f"\nUnavailable: {action.unavailable_reason}" if action.unavailable_reason else "")
            )
            layout.addWidget(card, index // 2, index % 2)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)


class CombatSkillGridItem(QFrame):
    def __init__(self, action: CombatActionOptionView) -> None:
        super().__init__()
        self.setObjectName("combatSkillItem")
        self.setProperty("available", action.available)
        self.setMinimumHeight(50)
        self.setMaximumHeight(58)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.action = action
        self.hover_card: AbilityHoverCard | None = None
        self._hover_suppressed = False
        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(5, 3, 5, 3)
        card_layout.setSpacing(1)
        title_row = QHBoxLayout()
        self._icon_name = action.name
        self._icon_category = "spell" if "spell" in action.kind.casefold() else "skill"
        self._icon_context = f"{action.kind} {action.description}"
        self.icon_label = item_icon_label(
            self._icon_name,
            category=self._icon_category,
            context=self._icon_context,
            size=24,
            object_name="combatSkillIcon",
        )
        title = QLabel(f"{action.name} · {action.kind.title()}")
        title.setObjectName("combatSkillName")
        detail = QLabel(action.resource_label)
        detail.setObjectName("combatSkillCost")
        detail.setWordWrap(True)
        title_row.addWidget(self.icon_label)
        title_row.addWidget(title, 1)
        card_layout.addLayout(title_row)
        card_layout.addWidget(detail)
        self.setToolTip(
            action.description
            + (f"\nUnavailable: {action.unavailable_reason}" if action.unavailable_reason else "")
        )

    def enterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if not self._hover_suppressed:
            self.hover_card = AbilityHoverCard(self.action, self)
            self.hover_card.show_near(QCursor.pos())
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.hover_card is not None:
            self.hover_card.close()
            self.hover_card.deleteLater()
            self.hover_card = None
        self._hover_suppressed = False
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._hover_suppressed = True
        if self.hover_card is not None:
            self.hover_card.close()
            self.hover_card.deleteLater()
            self.hover_card = None
        super().mousePressEvent(event)

    def refresh_theme_icon(self) -> None:
        refresh_item_icon(
            self.icon_label,
            self._icon_name,
            category=self._icon_category,
            context=self._icon_context,
        )


class CombatSkillsGrid(QWidget):
    """Compact, separately wrapped list of unlocked combat abilities and spells."""

    ITEM_PITCH = 62

    def __init__(
        self,
        actions: tuple[CombatActionOptionView, ...],
        *,
        columns: int = 2,
        vertical_fill: bool = False,
    ) -> None:
        super().__init__()
        self.setObjectName("combatSkillsGrid")
        self.actions = actions
        self.columns = max(1, columns)
        self.vertical_fill = vertical_fill
        self._row_capacity = 0
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding if vertical_fill else QSizePolicy.Policy.Maximum,
        )
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(3)
        self.grid.setVerticalSpacing(6)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        for column in range(self.columns):
            self.grid.setColumnStretch(column, 1)
        if not actions:
            self.grid.addWidget(QLabel("No combat abilities unlocked"), 0, 0)
            return
        initial_capacity = (
            (len(actions) + self.columns - 1) // self.columns
            if vertical_fill else 0
        )
        self._populate(initial_capacity)

    def _populate(self, row_capacity: int) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._row_capacity = max(1, row_capacity) if self.vertical_fill else 0
        for index, action in enumerate(self.actions):
            if self.vertical_fill:
                column = min(index // self._row_capacity, self.columns - 1)
                row = (
                    index % self._row_capacity
                    if column < self.columns - 1
                    else index - (self.columns - 1) * self._row_capacity
                )
            else:
                row = index // self.columns
                column = index % self.columns
            self.grid.addWidget(CombatSkillGridItem(action), row, column)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if not self.vertical_fill or not self.actions:
            return
        row_capacity = max(
            1,
            (event.size().height() + self.grid.verticalSpacing()) // self.ITEM_PITCH,
        )
        row_capacity = min(row_capacity, len(self.actions))
        if row_capacity != self._row_capacity:
            self._populate(row_capacity)
