"""Theme-aware deterministic crafting recipe browser."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import Qt as GuiQt
from PySide6.QtWidgets import QGridLayout, QScrollArea, QVBoxLayout, QWidget

from dd_simulator.ui.models.presentation import CraftingRecipeView
from dd_simulator.ui.item_icons import item_icon_label
from dd_simulator.ui.widgets.codex_cards import codex_card, icon_row, plain_label
from dd_simulator.ui.widgets.semantic_button import SemanticButton

RECIPE_COLUMNS = 3


class CraftingPage(QWidget):
    craft_requested = Signal(str)

    def __init__(self, recipes: tuple[CraftingRecipeView, ...]) -> None:
        super().__init__()
        self.setObjectName("craftingUtilityPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("craftingRecipeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("craftingRecipeContent")
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 2, 4, 0)
        grid.setSpacing(8)
        grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        if not recipes:
            grid.addWidget(plain_label(
                "No crafting recipes are available in this campaign.", "pageCardMeta"
            ), 0, 0)
        for index, recipe in enumerate(recipes):
            card, card_layout = codex_card(recipe.name, "craftingRecipeCard")
            card.setProperty("available", recipe.available)
            card_layout.addWidget(icon_row(
                item_icon_label(
                    recipe.output_name,
                    rarity=recipe.output_rarity,
                    context=recipe.description,
                    size=34,
                    object_name="craftingItemIcon",
                ),
                f"{recipe.output_quantity} × {recipe.output_name}",
                f"{recipe.skill_name} {recipe.skill_level} / Difficulty {recipe.difficulty}",
                rarity=recipe.output_rarity.casefold(),
            ))
            card_layout.addWidget(plain_label(recipe.description, "pageCardValue", word_wrap=True))
            ingredients = ", ".join(
                f"{value.name} {value.owned}/{value.required}"
                for value in recipe.ingredients
            ) or "None"
            tool = (
                f"{recipe.required_tool} ({recipe.tool_use_cost} use)"
                if recipe.required_tool else "None"
            )
            details = QGridLayout()
            details.setHorizontalSpacing(12)
            details.setVerticalSpacing(3)
            for row, (label, value) in enumerate((
                ("Ingredients", ingredients),
                ("Tool", tool),
                ("Creates", f"{recipe.output_rarity.title()} · {recipe.crafting_xp} Crafting XP"),
            )):
                details.addWidget(plain_label(label.upper(), "pageCardLabel"), row, 0)
                details.addWidget(plain_label(value, "pageCardValue", word_wrap=True), row, 1)
            details.setColumnStretch(1, 1)
            card_layout.addLayout(details)
            card_layout.addStretch(1)
            button = SemanticButton(
                "Craft", role="primary", object_name="craftRecipeButton"
            )
            button.setEnabled(recipe.available)
            button.setToolTip(GuiQt.convertFromPlainText(
                recipe.unavailable_reason or f"Craft {recipe.output_name}"
            ))
            button.clicked.connect(
                lambda _checked=False, recipe_id=recipe.id:
                self.craft_requested.emit(recipe_id)
            )
            card_layout.addWidget(button)
            grid.addWidget(card, index // RECIPE_COLUMNS, index % RECIPE_COLUMNS)
        for column in range(RECIPE_COLUMNS):
            grid.setColumnStretch(column, 1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
