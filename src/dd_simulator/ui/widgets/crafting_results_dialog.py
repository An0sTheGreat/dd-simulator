"""Persistent themed acknowledgement popup for crafting outcomes."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from dd_simulator.ui.models.presentation import CraftingResultView
from dd_simulator.ui.item_icons import item_icon_label
from dd_simulator.ui.widgets.semantic_button import SemanticButton
from dd_simulator.ui.widgets.themed_dialog import ThemedDialog


class CraftingResultsDialog(ThemedDialog):
    continued = Signal(str)

    def __init__(self, result: CraftingResultView, parent: QWidget | None = None) -> None:
        super().__init__("Crafting Results", parent)
        self.result = result
        self._allow_close = False
        self.setObjectName("craftingResultsDialog")
        self.setModal(True)
        self.setMinimumSize(540, 430)
        layout = self.content_layout

        title = QLabel("CRAFTING SUCCESS" if result.success else "CRAFTING FAILED")
        title.setObjectName("craftingResultsTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        summary = QLabel(result.summary)
        summary.setObjectName("craftingResultsSummary")
        summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        summary.setWordWrap(True)
        layout.addWidget(summary)

        totals = QFrame()
        totals.setObjectName("craftingResultTotals")
        totals_layout = QHBoxLayout(totals)
        for label, value in (
            ("Crafting Score", result.score),
            ("Difficulty", result.difficulty),
            ("Crafting XP", result.crafting_xp),
        ):
            total = QLabel(f"{label}\n{value}")
            total.setObjectName("craftingResultTotal")
            total.setAlignment(Qt.AlignmentFlag.AlignCenter)
            totals_layout.addWidget(total, 1)
        layout.addWidget(totals)

        output = QFrame()
        output.setObjectName("craftingResultItem")
        output.setProperty("rarity", result.output_rarity or "common")
        output_layout = QVBoxLayout(output)
        output_layout.addWidget(
            item_icon_label(
                result.output_name,
                rarity=result.output_rarity or "common",
                context=f"crafted {result.recipe_name} {result.quality}",
                size=48,
                object_name="craftingItemIcon",
            ),
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        output_text = (
            f"{result.output_name} x{result.output_quantity}\n"
            f"{result.quality} | {result.output_rarity.title()}"
            if result.success else "No item was created."
        )
        output_label = QLabel(output_text)
        output_label.setObjectName("craftingResultItemText")
        output_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        output_layout.addWidget(output_label)
        layout.addWidget(output)

        materials = ", ".join(
            f"{name} x{quantity}" for name, quantity in result.ingredients_consumed
        ) or "None"
        tools = ", ".join(
            f"{name}: {uses} use" for name, uses in result.tool_uses
        ) or "None"
        detail = QLabel(
            f"Materials consumed: {materials}\nTool durability or uses consumed: {tools}"
        )
        detail.setObjectName("craftingResultDetail")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        layout.addStretch(1)

        acknowledge = SemanticButton(
            "Continue Adventure", role="primary", object_name="continueAfterCraftingButton"
        )
        acknowledge.clicked.connect(self._continue)
        layout.addWidget(acknowledge)

    def allow_close(self) -> None:
        self._allow_close = True

    def reject(self) -> None:
        if self._allow_close:
            super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._allow_close:
            super().closeEvent(event)
        else:
            event.ignore()

    def _continue(self) -> None:
        self.continued.emit(self.result.id)
        if self._allow_close:
            self.accept()
