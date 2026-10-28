from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QSplitter, QWidget

from dd_simulator.state import GameStateDatabase, GameStateError, GameStateService
from dd_simulator.ui.main_window import MainWindow
from dd_simulator.ui.services.ui_preferences import UiPreferencesStore
from dd_simulator.ui.themes.theme_manager import ThemeManager
from dd_simulator.ui.widgets.crafting_results_dialog import CraftingResultsDialog


THEMES_ROOT = Path(__file__).parents[1] / "src" / "dd_simulator" / "ui" / "themes"


def _service() -> GameStateService:
    database = GameStateDatabase.in_memory()
    service = GameStateService(database)
    assert service.initialize() == 24
    service.ensure_demo_campaign()
    return service


def _recipe(service: GameStateService, name: str):  # type: ignore[no-untyped-def]
    return next(value for value in service.load_active_dashboard().crafting_recipes if value.name == name)


def _quantity(service: GameStateService, name: str) -> int:
    return sum(
        value.quantity for value in service.load_active_dashboard().inventory_preview
        if value.name == name
    )


def test_success_consumes_materials_adds_output_xp_event_and_pending_result() -> None:
    service = _service()
    recipe = _recipe(service, "Field Bandages")
    cloth_before = _quantity(service, "Cloth")
    bandages_before = _quantity(service, "Bandages")

    result = service.craft_recipe(recipe.id)
    dashboard = service.load_active_dashboard()

    assert result.success and result.quality == "Fine"
    assert result.output_rarity == "uncommon"
    assert _quantity(service, "Cloth") == cloth_before - 2
    assert _quantity(service, "Bandages") == bandages_before + 2
    assert dashboard.pending_crafting_result is not None
    assert dashboard.pending_crafting_result.id == result.id
    with service.database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM events WHERE summary = ?", (result.summary,)
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_state_audits WHERE event_type = 'crafting'"
        ).fetchone()[0] == 1


def test_failed_attempt_preserves_materials_and_tool_uses_but_awards_small_xp() -> None:
    service = _service()
    recipe = _recipe(service, "Lockpick Set")
    iron_before = _quantity(service, "Iron Scraps")
    with service.database.connect() as connection:
        tool_before = int(connection.execute(
            "SELECT charges FROM inventory_items WHERE name = 'Flint & Steel'"
        ).fetchone()[0])

    result = service.craft_recipe(recipe.id)

    assert not result.success
    assert result.ingredients_consumed == () and result.tool_uses == ()
    assert result.crafting_xp == 7
    assert _quantity(service, "Iron Scraps") == iron_before
    with service.database.connect() as connection:
        assert int(connection.execute(
            "SELECT charges FROM inventory_items WHERE name = 'Flint & Steel'"
        ).fetchone()[0]) == tool_before


def test_tool_recipe_consumes_one_use_and_blocks_until_acknowledged() -> None:
    service = _service()
    recipe = _recipe(service, "Restorative Draught")
    with service.database.transaction() as connection:
        connection.execute(
            "UPDATE skills SET level = 50 WHERE name = 'Crafting' AND character_id IN "
            "(SELECT id FROM characters WHERE is_player = 1)"
        )
    herbs_before = _quantity(service, "Herbs")
    water_before = _quantity(service, "Water Flask")

    result = service.craft_recipe(recipe.id)
    with service.database.connect() as connection:
        uses = int(connection.execute(
            "SELECT charges FROM inventory_items WHERE name = 'Healer''s Kit'"
        ).fetchone()[0])
    assert result.success and result.tool_uses == (("Healer's Kit", 1),)
    assert herbs_before - _quantity(service, "Herbs") == 2
    assert water_before - _quantity(service, "Water Flask") == 1
    assert uses == 4

    with pytest.raises(GameStateError, match="acknowledged"):
        service.craft_recipe(_recipe(service, "Field Bandages").id)
    service.acknowledge_crafting_result(result.id)
    assert service.load_active_dashboard().pending_crafting_result is None


def test_crafting_ui_popup_and_people_splitter_layout(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    service = _service()
    result = service.craft_recipe(_recipe(service, "Field Bandages").id)
    preferences = UiPreferencesStore(tmp_path / "preferences.json")
    themes = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "theme.json",
        default_theme_id="high_fantasy",
    ).available_themes()
    window = MainWindow(
        themes, service.load_active_dashboard(),
        game_state_service=service, preferences_store=preferences,
    )
    window.resize(1600, 900)
    window.show()
    window.controller.navigate("people")
    app.processEvents()

    # Crafting lives on the `crafting` page, opened from the Character Sheet and back.
    assert window.crafting_page.parentWidget() is window.content_stack.widget(window.page_indices["crafting"])
    assert len(window.crafting_page.findChildren(QWidget, "craftRecipeButton")) == 3
    window.controller.navigate("character_sheet")
    window.navigation_pages["character_sheet"].findChild(QWidget, "characterSheetCraftingButton").click()
    assert window.current_page == "crafting"
    window.findChild(QWidget, "craftingBackButton").click()
    assert window.current_page == "character_sheet"
    window.controller.navigate("people")
    app.processEvents()
    dialog = window.findChild(CraftingResultsDialog, "craftingResultsDialog")
    assert dialog is not None and dialog.isVisible() and dialog.isModal()
    assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert dialog.findChild(QWidget, "themedDialogTitleBar") is not None
    assert dialog.result.id == result.id
    dialog.reject()
    assert dialog.isVisible()

    splitter = window.findChild(QSplitter, "peopleTradeConversationSplitter")
    trade = window.findChild(QWidget, "merchantTradePanel")
    conversation = window.findChild(QWidget, "peopleConversationRegion")
    assert splitter is not None and trade is not None and conversation is not None
    # A horizontal divider between Conversation and Trade; Trade takes about two fifths.
    assert splitter.orientation().name == "Horizontal"
    assert splitter.handleWidth() == window.concept_splitter.handleWidth()
    page_width = window.navigation_pages["people"].width()
    assert 0.3 * page_width < trade.width() < 0.45 * page_width
    assert conversation.width() > trade.width() * 2

    splitter.setSizes([600, 450])
    expected = splitter.sizes()
    window.save_ui_preferences()
    assert preferences.load_ui()["splitters"]["people"] == expected

    dialog.continued.emit(result.id)
    dialog.allow_close()
    dialog.accept()
    window.close()
