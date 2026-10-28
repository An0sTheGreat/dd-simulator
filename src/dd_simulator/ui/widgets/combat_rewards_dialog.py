"""Theme-aware post-combat reward and outcome popup."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from dd_simulator.ui.models.presentation import CombatEncounterView, PlayerSummaryView
from dd_simulator.ui.item_icons import item_icon_label
from dd_simulator.ui.widgets.semantic_button import SemanticButton
from dd_simulator.ui.widgets.themed_dialog import ThemedDialog


class CombatRewardsDialog(ThemedDialog):
    claim_item_requested = Signal(str)
    claim_all_requested = Signal(str)
    continued = Signal(str)

    def __init__(
        self,
        encounter: CombatEncounterView,
        player: PlayerSummaryView,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Encounter Results", parent)
        if encounter.reward is None:
            raise ValueError("A reward dialog requires a persisted encounter reward.")
        self.encounter = encounter
        self.reward = encounter.reward
        self.setObjectName("combatRewardsDialog")
        self.setModal(True)
        self.setMinimumSize(560, 480)
        self.resize(680, 600)

        layout = self.content_layout
        title = QLabel(
            {
                "victory": "VICTORY REWARDS",
                "defeat": "ENCOUNTER DEFEAT",
                "escaped": "ESCAPED ENCOUNTER",
                "resolved": "ENCOUNTER RESOLVED",
            }.get(self.reward.outcome, "ENCOUNTER RESULTS")
        )
        title.setObjectName("combatRewardsTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        outcome = QLabel(encounter.end_reason or self.reward.outcome.title())
        outcome.setObjectName("combatRewardsOutcome")
        outcome.setWordWrap(True)
        outcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(outcome)

        totals = QFrame()
        totals.setObjectName("combatRewardTotals")
        totals_layout = QHBoxLayout(totals)
        for label, value in (
            ("Character XP", self.reward.experience),
            ("Skill XP", self.reward.skill_experience),
            ("Gold", self.reward.currency),
        ):
            value_label = QLabel(f"{label}\n{value}")
            value_label.setObjectName("combatRewardTotal")
            value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            totals_layout.addWidget(value_label, 1)
        layout.addWidget(totals)

        resources = ", ".join(
            f"{resource.name} {resource.current}/{resource.maximum}"
            for resource in player.resources
            if resource.resource_type != "experience"
        )
        player_combatant = next(
            (row for row in encounter.combatants if row.side == "player"), None
        )
        injuries = "None"
        if player_combatant is not None and player_combatant.conditions:
            injuries = ", ".join(player_combatant.conditions)
        detail = QLabel(f"Remaining resources: {resources}\nConditions or injuries: {injuries}")
        detail.setObjectName("combatRewardDetail")
        detail.setWordWrap(True)
        layout.addWidget(detail)

        item_title = QLabel("RECOVERED ITEMS")
        item_title.setObjectName("combatRewardSectionTitle")
        layout.addWidget(item_title)

        scroll = QScrollArea()
        scroll.setObjectName("combatRewardItemsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("combatRewardItems")
        self.items_layout = QVBoxLayout(content)
        self.item_buttons: dict[str, SemanticButton] = {}
        if not self.reward.items:
            empty = QLabel("No items were recovered from this encounter.")
            empty.setObjectName("combatRewardEmpty")
            self.items_layout.addWidget(empty)
        for item in self.reward.items:
            row = QFrame()
            row.setObjectName("combatRewardItem")
            row.setProperty("rarity", item.rarity)
            row_layout = QHBoxLayout(row)
            row_layout.addWidget(item_icon_label(
                item.name,
                rarity=item.rarity,
                context=item.description,
                size=40,
                object_name="rewardItemIcon",
            ))
            text = QLabel(
                f"{item.name} ×{item.quantity}\n{item.rarity.title()} — {item.description}"
            )
            text.setObjectName("combatRewardItemText")
            text.setWordWrap(True)
            row_layout.addWidget(text, 1)
            button = SemanticButton(
                "Claimed" if item.claimed else "Claim",
                role="default",
                object_name="claimRewardItemButton",
            )
            button.setEnabled(not item.claimed)
            button.clicked.connect(
                lambda _checked=False, item_id=item.id:
                self.claim_item_requested.emit(item_id)
            )
            row_layout.addWidget(button)
            self.item_buttons[item.id] = button
            self.items_layout.addWidget(row)
        self.items_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        self.feedback = QLabel("")
        self.feedback.setObjectName("combatRewardFeedback")
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)

        controls = QHBoxLayout()
        self.claim_all = SemanticButton(
            "Claim All Available", role="default", object_name="claimAllRewardsButton"
        )
        self.claim_all.setEnabled(any(not item.claimed for item in self.reward.items))
        self.claim_all.clicked.connect(
            lambda: self.claim_all_requested.emit(self.reward.id)
        )
        controls.addWidget(self.claim_all)
        continue_button = SemanticButton(
            "Continue Adventure", role="primary", object_name="continueAfterCombatButton"
        )
        continue_button.clicked.connect(self._continue)
        controls.addWidget(continue_button)
        layout.addLayout(controls)

    def mark_claimed(self, item_id: str) -> None:
        button = self.item_buttons.get(item_id)
        if button is not None:
            button.setText("Claimed")
            button.setEnabled(False)
        self.claim_all.setEnabled(any(button.isEnabled() for button in self.item_buttons.values()))
        self.feedback.setText("Reward added to inventory.")
        self.feedback.setProperty("feedbackState", "success")
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)

    def mark_all_claimed(self, unclaimed_ids: set[str]) -> None:
        for item_id, button in self.item_buttons.items():
            if item_id not in unclaimed_ids:
                button.setText("Claimed")
                button.setEnabled(False)
        self.claim_all.setEnabled(bool(unclaimed_ids))

    def show_warning(self, text: str) -> None:
        self.feedback.setText(text)
        self.feedback.setProperty("feedbackState", "warning")
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)

    def _continue(self) -> None:
        self.continued.emit(self.reward.id)
        self.accept()
