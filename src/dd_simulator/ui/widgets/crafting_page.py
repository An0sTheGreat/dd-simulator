"""Theme-aware deterministic crafting recipe browser."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from dd_simulator.ui.models.presentation import CraftingRecipeView
from dd_simulator.ui.item_icons import item_icon_label
from dd_simulator.ui.panels.common import semantic_label
from dd_simulator.ui.widgets.semantic_button import SemanticButton


class CraftingPage(QWidget):
    craft_requested = Signal(str)

    def __init__(self, recipes: tuple[CraftingRecipeView, ...]) -> None:
        super().__init__()
        self.setObjectName("craftingUtilityPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(semantic_label(
            "CRAFTING RECIPES", object_name="utilitySectionTitle", text_role="accent"
        ))
        layout.addWidget(semantic_label(
            "Ingredients and tool uses are consumed only after a successful deterministic attempt.",
            text_role="secondary", word_wrap=True,
        ))
        scroll = QScrollArea()
        scroll.setObjectName("craftingRecipeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("craftingRecipeContent")
        recipes_layout = QVBoxLayout(content)
        recipes_layout.setContentsMargins(0, 0, 4, 0)
        recipes_layout.setSpacing(6)
        if not recipes:
            recipes_layout.addWidget(semantic_label(
                "No crafting recipes are available in this campaign.", text_role="muted"
            ))
        for recipe in recipes:
            card = QFrame()
            card.setObjectName("craftingRecipeCard")
            card.setProperty("available", recipe.available)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 7, 8, 7)
            card_layout.setSpacing(4)
            heading = QHBoxLayout()
            heading.addWidget(item_icon_label(
                recipe.output_name,
                rarity=recipe.output_rarity,
                context=recipe.description,
                size=32,
                object_name="craftingItemIcon",
            ))
            heading.addWidget(semantic_label(
                recipe.name, object_name="craftingRecipeName", text_role="accent"
            ), 1)
            heading.addWidget(semantic_label(
                f"{recipe.skill_name} {recipe.skill_level} / Difficulty {recipe.difficulty}",
                text_role="secondary",
            ))
            card_layout.addLayout(heading)
            card_layout.addWidget(semantic_label(
                recipe.description, text_role="body", word_wrap=True
            ))
            ingredients = ", ".join(
                f"{value.name} {value.owned}/{value.required}"
                for value in recipe.ingredients
            ) or "None"
            tool = (
                f"{recipe.required_tool} ({recipe.tool_use_cost} use)"
                if recipe.required_tool else "None"
            )
            card_layout.addWidget(semantic_label(
                f"Ingredients: {ingredients}\nTool: {tool}\n"
                f"Creates: {recipe.output_quantity} x {recipe.output_name} "
                f"({recipe.output_rarity.title()}) | {recipe.crafting_xp} Crafting XP",
                object_name="craftingRecipeDetails", text_role="secondary", word_wrap=True,
            ))
            button = SemanticButton(
                "Craft", role="primary", object_name="craftRecipeButton"
            )
            button.setEnabled(recipe.available)
            button.setToolTip(
                recipe.unavailable_reason or f"Craft {recipe.output_name}"
            )
            button.clicked.connect(
                lambda _checked=False, recipe_id=recipe.id:
                self.craft_requested.emit(recipe_id)
            )
            card_layout.addWidget(button)
            recipes_layout.addWidget(card)
        recipes_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
