"""Skills-style compact quest grid with expandable inline objectives."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from dd_simulator.ui.models.presentation import QuestListItemView


class QuestListItem(QFrame):
    toggled = Signal(str, bool)
    COLLAPSED_HEIGHT = 52

    def __init__(self, quest: QuestListItemView, *, expanded: bool = False) -> None:
        super().__init__()
        self.quest = quest
        self.expanded = False
        self.completed = quest.status in {"complete", "completed"}
        self.setObjectName("questListItem")
        self.setProperty("questStatus", quest.status)
        self.setProperty("selected", quest.selected)
        self.setProperty("completed", self.completed)
        self.setProperty("expanded", False)
        self.setAccessibleName(f"{quest.title}, {quest.status}")
        self.setAccessibleDescription(
            "Completed quest; objectives are no longer available."
            if self.completed
            else "Press Enter or Space to show or hide quest objectives."
        )
        self.setFocusPolicy(
            Qt.FocusPolicy.NoFocus if self.completed else Qt.FocusPolicy.StrongFocus
        )
        self.setCursor(
            Qt.CursorShape.ArrowCursor
            if self.completed
            else Qt.CursorShape.PointingHandCursor
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 3, 5, 3)
        layout.setSpacing(2)
        header = QHBoxLayout()
        title = QLabel(quest.title)
        title.setObjectName("questListTitle")
        header.addWidget(title, 1)
        state = "Completed" if self.completed else quest.status.title()
        self.state_label = QLabel(f"{state}  {'›' if not self.completed else ''}".rstrip())
        self.state_label.setObjectName("questListState")
        header.addWidget(self.state_label)
        layout.addLayout(header)

        progress = QProgressBar()
        progress.setObjectName("questProgress")
        progress.setRange(0, max(1, quest.progress_maximum))
        progress.setValue(quest.progress_current)
        progress.setFormat(f"{state}: %v / {quest.progress_maximum}")
        progress.setTextVisible(not self.completed)
        layout.addWidget(progress)

        self.details = QWidget()
        self.details.setObjectName("questObjectiveDropdown")
        detail_layout = QVBoxLayout(self.details)
        detail_layout.setContentsMargins(4, 5, 4, 3)
        detail_layout.setSpacing(3)
        if quest.summary:
            summary = QLabel(quest.summary)
            summary.setObjectName("questExpandedSummary")
            summary.setWordWrap(True)
            detail_layout.addWidget(summary)
        objective_title = QLabel("OBJECTIVES")
        objective_title.setObjectName("questObjectiveTitle")
        detail_layout.addWidget(objective_title)
        if quest.objectives:
            for objective in quest.objectives:
                marker = "[x]" if objective.completed else "[ ]"
                optional = " Optional:" if objective.optional else ""
                label = QLabel(f"{marker}{optional} {objective.text}")
                label.setObjectName("questObjectiveEntry")
                label.setProperty("objectiveComplete", objective.completed)
                label.setWordWrap(True)
                detail_layout.addWidget(label)
        else:
            empty = QLabel("No visible objectives are recorded.")
            empty.setObjectName("questObjectiveEmpty")
            detail_layout.addWidget(empty)
        if quest.deadline:
            deadline = QLabel(f"Deadline: {quest.deadline}")
            deadline.setObjectName("questDeadline")
            detail_layout.addWidget(deadline)
        if quest.reward_summary:
            reward = QLabel(f"Reward: {quest.reward_summary}")
            reward.setObjectName("questRewardPreview")
            detail_layout.addWidget(reward)
        self.details.setVisible(False)
        layout.addWidget(self.details)

        tooltip = [quest.title, f"Status: {quest.status}"]
        if quest.deadline:
            tooltip.append(f"Deadline: {quest.deadline}")
        if not self.completed:
            tooltip.append("Click to view objectives")
        self.setToolTip("\n".join(tooltip))
        self._set_expanded(expanded and not self.completed, emit=False)

    def _set_expanded(self, expanded: bool, *, emit: bool = True) -> None:
        if self.completed:
            expanded = False
        self.expanded = expanded
        self.details.setVisible(expanded)
        self.setProperty("expanded", expanded)
        if not self.completed:
            self.state_label.setText(f"{self.quest.status.title()}  {'⌄' if expanded else '›'}")
        if expanded:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            if self.layout() is not None:
                self.layout().invalidate()
                self.layout().activate()
                self.setMinimumHeight(self.layout().sizeHint().height())
        else:
            self.setFixedHeight(self.COLLAPSED_HEIGHT)
        self.style().unpolish(self)
        self.style().polish(self)
        if emit:
            self.toggled.emit(self.quest.id, expanded)

    def toggle(self) -> None:
        if not self.completed:
            self._set_expanded(not self.expanded)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self.completed:
            self.toggle()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space}:
            self.toggle()
            event.accept()
            return
        super().keyPressEvent(event)


class QuestListWidget(QScrollArea):
    """Lay quests vertically first, adding up to six equal-width columns."""

    ITEM_PITCH = 58
    MAX_COLUMNS = 6

    def __init__(self, quests: tuple[QuestListItemView, ...]) -> None:
        super().__init__()
        self.quests = quests
        self.expanded_ids: set[str] = set()
        self._row_capacity = 0
        self.setObjectName("questList")
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content.setObjectName("questListContent")
        self.content.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(4)
        self.grid.setVerticalSpacing(6)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setWidget(self.content)
        self._populate(max(1, len(quests)))

    def _populate(self, row_capacity: int) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._row_capacity = max(1, row_capacity)
        # Only occupied columns stretch, so one column of quests fills the width.
        used = min(self.MAX_COLUMNS, max(1, -(-len(self.quests) // self._row_capacity)))
        for column in range(self.MAX_COLUMNS):
            self.grid.setColumnStretch(column, 1 if column < used else 0)
        if not self.quests:
            empty = QLabel("No known quests")
            empty.setObjectName("questListEmptyState")
            empty.setToolTip("Quest records will appear here when discovered")
            self.grid.addWidget(empty, 0, 0)
            return
        for index, quest in enumerate(self.quests):
            column = min(self.MAX_COLUMNS - 1, index // self._row_capacity)
            row = index - column * self._row_capacity
            card = QuestListItem(
                quest, expanded=quest.id in self.expanded_ids
            )
            card.toggled.connect(self._quest_toggled)
            self.grid.addWidget(card, row, column, Qt.AlignmentFlag.AlignTop)

    def _quest_toggled(self, quest_id: str, expanded: bool) -> None:
        if expanded:
            self.expanded_ids.add(quest_id)
        else:
            self.expanded_ids.discard(quest_id)
        self.content.adjustSize()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if not self.quests:
            return
        capacity = max(
            1,
            (self.viewport().height() + self.grid.verticalSpacing()) // self.ITEM_PITCH,
        )
        capacity = min(capacity, len(self.quests))
        if capacity != self._row_capacity:
            self._populate(capacity)
