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
from dd_simulator.ui.power_icons import action_icon_path, skill_icon_path
from dd_simulator.ui.widgets.hover_card import HoverCardHost, TooltipCard, card_icon


class AbilityHoverCard(TooltipCard):
    """Ability or spell card built from the action's stats; the badge is its status."""

    def __init__(self, action: CombatActionOptionView, parent: QWidget) -> None:
        stats = dict(action.stats)
        kind = action.kind.casefold()
        status = action.status_label or ("Ready" if action.available else "")
        super().__init__(
            parent,
            object_name="abilityHoverCard",
            card_kind=action.kind,
            title=action.name,
            tone="spell" if "spell" in kind else "ability",
            subtitle=" · ".join(dict.fromkeys(
                part for part in (action.kind.title(), stats.get("Type", "")) if part
            )),
            icon=card_icon(action_icon_path(action.key)),
            badge=status,
            badge_tone="ready" if action.available else "cooldown",
            rows=[(name, value) for name, value in action.stats if name != "Type"],
            description=action.description or "No description is available.",
            footer=f"Unavailable: {action.unavailable_reason}" if action.unavailable_reason else "",
        )
        self.setProperty("available", action.available)


class SkillHoverCard(TooltipCard):
    """Skill card: value, progress to the next level, XP bar, description, bonus."""

    def __init__(self, skill: SkillView, parent: QWidget) -> None:
        rows: list[tuple[str, str]] = []
        extras: list[QWidget] = []
        if skill.next_level_xp:
            percent = min(100, skill.current_xp * 100 // skill.next_level_xp)
            rows.append(("Progress", f"{percent}% to {skill.level + 1}"))
            rows.append(("Next level", f"{skill.current_xp:,} / {skill.next_level_xp:,} XP"))
            bar = QProgressBar()
            bar.setObjectName("tooltipXpBar")
            bar.setTextVisible(False)
            bar.setRange(0, skill.next_level_xp)
            bar.setValue(min(skill.current_xp, skill.next_level_xp))
            bar.setAccessibleName(f"{skill.name} experience {percent}%")
            extras.append(bar)
        if skill.bonus:
            rows.append(("Bonus", f"{skill.bonus:+d} temporary"))
        if skill.recently_increased:
            rows.append(("Status", "Recently increased"))
        super().__init__(
            parent,
            object_name="skillHoverCard",
            card_kind="skill",
            title=f"{skill.name} · {skill.level}",
            tone="skill",
            subtitle="Skill · Locked" if skill.locked else "Skill",
            icon=card_icon(skill_icon_path(skill.name)),
            rows=rows,
            extras=extras,
            description=skill.description,
        )
        self.skill = skill


class SkillGridItem(HoverCardHost, QFrame):
    def __init__(self, skill: SkillView) -> None:
        super().__init__()
        self.skill = skill
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

        self._icon_name = skill.name

    def build_hover_card(self) -> SkillHoverCard:
        return SkillHoverCard(self.skill, self)

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
