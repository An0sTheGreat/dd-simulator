"""Theme-aware quest completion and reward popup."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from dd_simulator.ui.models.presentation import QuestRewardView
from dd_simulator.ui.item_icons import item_icon_label
from dd_simulator.ui.widgets.semantic_button import SemanticButton
from dd_simulator.ui.widgets.themed_dialog import ThemedDialog


class QuestRewardsDialog(ThemedDialog):
    claim_item_requested = Signal(str)
    continued = Signal(str)

    def __init__(self, reward: QuestRewardView, parent: QWidget | None = None) -> None:
        super().__init__("Quest Completed", parent)
        self.reward = reward
        self.setObjectName("questRewardsDialog")
        self.setModal(True)
        self.setMinimumSize(520, 380)
        layout = self.content_layout

        title = QLabel("QUEST COMPLETED")
        title.setObjectName("questRewardsTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        quest = QLabel(reward.quest_title)
        quest.setObjectName("questRewardsQuestTitle")
        quest.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(quest)

        totals = QFrame()
        totals.setObjectName("questRewardTotals")
        totals_layout = QHBoxLayout(totals)
        values = [("Character XP", reward.experience), ("Gold", reward.currency)]
        if reward.reputation:
            values.append((f"{reward.faction or 'Faction'} Reputation", reward.reputation))
        for label, value in values:
            total = QLabel(f"{label}\n{value:+d}" if "Reputation" in label else f"{label}\n{value}")
            total.setObjectName("questRewardTotal")
            total.setAlignment(Qt.AlignmentFlag.AlignCenter)
            totals_layout.addWidget(total, 1)
        layout.addWidget(totals)

        section = QLabel("QUEST REWARDS")
        section.setObjectName("questRewardSectionTitle")
        layout.addWidget(section)
        self.item_buttons: dict[str, SemanticButton] = {}
        if not reward.items:
            empty = QLabel("No item rewards were granted.")
            empty.setObjectName("questRewardEmpty")
            layout.addWidget(empty)
        for item in reward.items:
            row = QFrame()
            row.setObjectName("questRewardItem")
            row.setProperty("rarity", item.rarity)
            row_layout = QHBoxLayout(row)
            row_layout.addWidget(item_icon_label(
                item.name,
                rarity=item.rarity,
                context=item.description,
                size=40,
                object_name="rewardItemIcon",
            ))
            text = QLabel(f"{item.name} x{item.quantity}\n{item.description}")
            text.setObjectName("questRewardItemText")
            text.setWordWrap(True)
            row_layout.addWidget(text, 1)
            button = SemanticButton(
                "Claimed" if item.claimed else "Claim",
                object_name="claimQuestRewardItemButton",
            )
            button.setEnabled(not item.claimed)
            button.clicked.connect(
                lambda _checked=False, item_id=item.id:
                self.claim_item_requested.emit(item_id)
            )
            row_layout.addWidget(button)
            self.item_buttons[item.id] = button
            layout.addWidget(row)
        layout.addStretch(1)
        self.feedback = QLabel("")
        self.feedback.setObjectName("questRewardFeedback")
        layout.addWidget(self.feedback)
        continue_button = SemanticButton(
            "Continue Adventure",
            role="primary",
            object_name="continueAfterQuestButton",
        )
        continue_button.clicked.connect(self._continue)
        layout.addWidget(continue_button)

    def mark_claimed(self, item_id: str) -> None:
        button = self.item_buttons.get(item_id)
        if button is not None:
            button.setText("Claimed")
            button.setEnabled(False)
        self.feedback.setText("Quest reward added to inventory.")
        self.feedback.setProperty("feedbackState", "success")
        self._refresh_feedback_style()

    def show_warning(self, message: str) -> None:
        self.feedback.setText(message)
        self.feedback.setProperty("feedbackState", "warning")
        self._refresh_feedback_style()

    def _refresh_feedback_style(self) -> None:
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)

    def _continue(self) -> None:
        self.continued.emit(self.reward.id)
        self.accept()
