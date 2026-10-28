from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QScrollArea, QWidget

from dd_simulator.app import build_application
from dd_simulator.state.item_catalog import TIER_WEIGHTS, catalog_items
from dd_simulator.state.turns import ActionOutcome, NarrativeSegment, ProposedStateChange
from dd_simulator.ui.item_icons import item_icon_label, item_icon_pixmap, resolve_icon
from dd_simulator.ui.models.presentation import EquipmentSlotView, InventorySlotView
from dd_simulator.ui.widgets.inventory_grid import (
    ART_ROOT,
    EquipmentGrid,
    EquipmentSlotWidget,
    InventorySlotWidget,
    _themed_artwork,
)
from dd_simulator.ui.widgets.codex_cards import CARD_COLUMNS, InventoryCard, bag_slots
from dd_simulator.ui.widgets.codex_character import PAPERDOLL_SLOT_NAMES
from dd_simulator.ui.widgets.scene_view import ChoiceGrid
from dd_simulator.ui.widgets.themed_dialog import ThemedDialog


def test_all_semantic_svgs_are_eligible_and_exact_items_use_exact_art() -> None:
    items = catalog_items()
    assert len(items) == 1686
    assert len({item.id for item in items}) == 1686
    assert all(weight > 0 for weight in TIER_WEIGHTS)
    assert all(left > right for left, right in zip(TIER_WEIGHTS, TIER_WEIGHTS[1:]))
    assert resolve_icon("Greater Healing Potion").index == 918
    assert resolve_icon("Health Potion").index == 919
    assert resolve_icon("Minor Healing Vial").index == 920
    assert resolve_icon("Arrows").subtype == "arrow"
    app = QApplication.instance() or QApplication([])
    app.setProperty("themeId", "high_fantasy")
    assert not item_icon_pixmap("Health Potion", force=True, size=64).isNull()


def test_release_26_5_uses_distinct_semantic_skill_and_item_icons() -> None:
    skills = (
        "Attack", "Strength", "Defense", "Ranged", "Survival", "Magic", "Herblore",
        "Crafting", "Warden's Mark", "Quick Shot", "Field Dressing", "Shield Wall",
    )
    indexes = [resolve_icon(name, category="skill").index for name in skills]
    assert len(set(indexes)) == len(indexes)
    assert resolve_icon("Iron Dagger").index == 320
    assert resolve_icon("Oak Shield").index == 610
    assert resolve_icon("Warden Coat").index == 719
    assert resolve_icon("Merchant Letter").index == 1191


def test_inventory_card_sizes_the_bag_by_capacity_with_scroll_and_sort_controls() -> None:
    app = QApplication.instance() or QApplication([])
    inventory = tuple(
        InventorySlotView(f"Item {index}", id=f"item-{index}") for index in range(37)
    )
    assert len(bag_slots(inventory, 320)) == 45  # eight occupied rows plus one spare row
    card = InventoryCard(inventory, capacity=40)
    card.show()
    app.processEvents()
    assert card.grid.columns == CARD_COLUMNS == 5
    assert len(card.grid.slots) == 40  # the capacity stops the bag short of the spare row
    bar = card.scroll.verticalScrollBar()
    assert bar.isVisible() and bar.maximum() > 0
    assert card.count_label.text() == "37 items \u00b7 12 below"
    card.scroll_to_position(36)
    app.processEvents()
    assert bar.value() == bar.maximum()
    assert card.count_label.text() == "37 items \u00b7 0 below"
    assert card.grid.slots[36].index == 36
    assert card.grid.slots[36].item.name == "Item 36"
    sort_modes: list[str] = []
    card.auto_sort_requested.connect(sort_modes.append)
    value_action = next(
        action for action in card.auto_sort_button.menu().actions()
        if action.text() == "Value"
    )
    value_action.trigger()
    assert sort_modes == ["value"]
    card.close()
    card.deleteLater()
    app.processEvents()


def test_item_slots_are_icon_only_artwork_with_lazy_hover_details() -> None:
    app = QApplication.instance() or QApplication([])
    app.setProperty("themeId", "high_fantasy")
    item = InventorySlotView("Health Potion", quantity=3, category="potion")
    inventory = InventorySlotWidget(item, 0)
    equipment = EquipmentSlotWidget(
        EquipmentSlotView("Body", "Warden Coat", "91/100", item=item), 0
    )
    long_text = "A generated response long enough to be clipped in a narrow choice grid"
    choices = ChoiceGrid(("Wait", long_text))
    short, long = choices.choice_buttons[:2]
    assert inventory.hover_card is None
    assert equipment.hover_card is None
    assert getattr(long, "hover_card", None) is None
    choices.resize(2400, 200)
    choices.show()
    app.processEvents()
    # The full text is only offered as a tooltip once the label has to clip it.
    assert short.toolTip() == "" and long.toolTip() == ""
    assert long.text_label.text() == long_text
    choices.resize(260, 200)
    app.processEvents()
    assert long.text_label.text() != long_text
    assert long.toolTip() == long_text
    assert short.accessibleName() == "Choice 1: Wait"
    assert long.accessibleName() == f"Choice 2: {long_text}"
    assert inventory.size().width() == inventory.size().height() == 96
    assert equipment.size().width() == equipment.size().height() == 100
    assert inventory.findChild(QLabel, "inventorySlotName") is None
    assert equipment.findChild(QLabel, "equipmentItemName") is None
    assert inventory.icon_label.width() == 68
    assert equipment.icon_label.width() == 200
    assert inventory.findChild(QLabel, "inventorySlotArtwork") is not None
    assert inventory.findChild(QLabel, "itemQuantityBadge").text() == "3"
    inventory.deleteLater()
    equipment.deleteLater()
    choices.close()
    choices.deleteLater()
    app.processEvents()


def test_equipment_uses_named_single_slot_artwork_in_requested_groups() -> None:
    app = QApplication.instance() or QApplication([])
    app.setProperty("themeId", "modern_proof")
    slots = tuple(
        EquipmentSlotView(name, "Iron Dagger" if name == "Main Hand" else None)
        for name in (
            "Main Hand", "Off Hand", "Head", "Body", "Hands",
            "Feet", "Neck", "Ring", "Ammunition",
        )
    )
    top = EquipmentGrid(
        slots,
        columns=5,
        slot_names=("Main Hand", "Off Hand", "Neck", "Ring", "Ammunition"),
        slot_size=96,
    )
    left = EquipmentGrid(
        slots,
        columns=1,
        slot_names=("Head", "Body", "Hands", "Feet"),
        slot_size=96,
    )
    assert tuple(slot.slot.slot_name for slot in top.slots) == (
        "Main Hand", "Off Hand", "Neck", "Ring", "Ammunition",
    )
    assert tuple(slot.slot.slot_name for slot in left.slots) == (
        "Head", "Body", "Hands", "Feet",
    )
    assert all(slot.width() == slot.height() == 96 for slot in (*top.slots, *left.slots))
    assert all(
        slot.artwork_label.pixmap() is not None
        and not slot.artwork_label.pixmap().isNull()
        and slot.artwork_label.pixmap().size() == slot.artwork_label.size()
        for slot in (*top.slots, *left.slots)
    )
    assert top.slots[0].artwork_asset.endswith("inv_main_hand.png")
    assert left.slots[0].artwork_asset.endswith("inv_head.png")
    assert not top.slots[0].occupied_artwork_label.isHidden()
    assert left.slots[0].occupied_artwork_label.isHidden()
    top.deleteLater()
    left.deleteLater()
    app.processEvents()


def test_inventory_artwork_keeps_source_colors_across_themes() -> None:
    app = QApplication.instance() or QApplication([])
    source = QPixmap(str(ART_ROOT / "Inventory_Example_01.png"))
    fantasy = _themed_artwork("Inventory_Example_01.png", 80, "high_fantasy")
    dark = _themed_artwork("Inventory_Example_01.png", 80, "modern_proof")
    assert fantasy.toImage() == source.toImage()
    assert dark.toImage() == source.toImage()


def test_default_icon_does_not_show_as_a_parentless_window() -> None:
    app = QApplication.instance() or QApplication([])
    app.setProperty("themeId", "high_fantasy")
    parentless_shows: list[QLabel] = []

    class Recorder(QObject):
        def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
            if (
                event.type() == QEvent.Type.Show
                and isinstance(watched, QLabel)
                and watched.objectName() == "itemIcon"
                and watched.parentWidget() is None
            ):
                parentless_shows.append(watched)
            return False

    recorder = Recorder()
    app.installEventFilter(recorder)
    icon = item_icon_label("Health Potion", category="potion", size=42)
    host = QWidget()
    layout = QHBoxLayout(host)
    layout.addWidget(icon)
    host.show()
    app.processEvents()
    assert not parentless_shows
    assert icon.isVisible()
    host.close()
    host.deleteLater()
    app.removeEventFilter(recorder)
    app.processEvents()


def test_player_resources_no_longer_create_icons(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.theme_requested.emit("high_fantasy")
    assert not window.findChildren(QLabel, "resourceIcon")
    assert len(window.character_strip.bars) == 5
    assert len(window.findChildren(QWidget, "codexResourceBar")) == 5
    window.close()
    window.deleteLater()
    app.processEvents()


def test_release_26_3_custom_chrome_centers_title_and_dims_for_dialogs(
    tmp_path: Path,
) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.resize(1600, 900)
    window.show()
    app.processEvents()
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    left = window.findChild(QWidget, "titleBarLeft")
    right = window.findChild(QWidget, "titleBarRight")
    title = window.findChild(QLabel, "applicationTitle")
    assert left.width() == right.width() == 320
    title_center = title.mapTo(window, title.rect().center()).x()
    assert abs(title_center - window.rect().center().x()) <= 1

    dialog = ThemedDialog("Focused popup", window)
    dialog.show()
    app.processEvents()
    assert window.findChild(QFrame, "dialogDimmer").isVisible()
    dialog.close()
    app.processEvents()
    assert not window.findChild(QFrame, "dialogDimmer").isVisible()
    window.close()
    window.deleteLater()
    app.processEvents()


def test_codex_column_consolidates_equipment_and_scene_frames_location(
    tmp_path: Path,
) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.resize(1600, 900)
    window.show()
    window.controller.navigate("dashboard")
    app.processEvents()
    # Equipment and inventory share the codex column instead of utility tabs.
    codex = window.concept_splitter.widget(0)
    paperdoll = window.paperdoll_panel
    inventory = window.inventory_card
    assert codex.isAncestorOf(paperdoll) and codex.isAncestorOf(inventory)
    assert [slot.slot.slot_name for slot in paperdoll.slots] == list(PAPERDOLL_SLOT_NAMES)
    assert inventory.grid.columns == CARD_COLUMNS
    paperdoll_bottom = paperdoll.mapTo(window, paperdoll.rect().bottomLeft()).y()
    assert paperdoll_bottom < inventory.mapTo(window, inventory.rect().topLeft()).y()
    for name in ("inventoryUtilityPage", "equipmentUtilityPage"):
        assert window.findChild(QWidget, name) is None
    # The scene, not a minimap or a summary label, frames the location art.
    assert window.findChild(QWidget, "minimapCanvas") is None
    assert window.findChild(QLabel, "locationVisualPlaceholder") is None
    assert window.scene_view.image_path is not None and window.scene_view.image_path.is_file()
    window.close()
    window.deleteLater()
    app.processEvents()


def test_search_can_award_only_a_bounded_semantic_loot_candidate(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    service = window.game_state_service
    context = service.build_action_context()
    available = context["available_loot"]
    assert len(available) == 8
    chosen = available[0]

    class Provider:
        def resolve_action(self, *, action: str, context: dict[str, object]) -> ActionOutcome:
            return ActionOutcome(
                narration=f"You discover {chosen['name']}.",
                state_changes=(ProposedStateChange(
                    "discover_item", "loot_item", str(chosen["id"]), None, True,
                    "Found during an explicit search.",
                ),),
                quest_notes=(),
                suggested_actions=tuple(f"Option {index}" for index in range(6)),
                narrative_segments=(NarrativeSegment("narrative", "The search turns up useful loot."),),
            )

    service.resolve_player_action("Search the nearby chest", Provider())
    assert any(item.name == chosen["name"] for item in service.load_active_dashboard().inventory_preview)
    window.close()
    window.deleteLater()
    app.processEvents()


def test_trade_routes_to_people_and_dialogue_projects_back_to_adventure(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    captured: list[tuple[str, str]] = []
    window._resolve_npc_dialogue = lambda npc_id, text: captured.append((npc_id, text))
    assert window._route_trade_action("I want to trade with the Roadside Merchant")
    assert window.current_page == "people"
    assert captured and captured[0][1] == "I want to trade with the Roadside Merchant"

    service = window.game_state_service
    npc_id = captured[0][0]
    result = service.resolve_npc_dialogue(npc_id, "Show me your wares")
    messages = service.load_active_dashboard().narrative.messages
    assert any(message.kind == "player" and message.text == result.player_text for message in messages)
    assert any(message.kind == "spoken" and message.text == result.npc_text for message in messages)
    window.close()
    window.deleteLater()
    app.processEvents()


def test_free_text_wares_request_does_not_invent_an_addressed_person(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    captured: list[tuple[str, str]] = []
    window._resolve_npc_dialogue = lambda npc_id, text: captured.append((npc_id, text))

    action = "I ask the tavern barmaid if she has any wares for purchase"
    assert not window._route_trade_action(action)
    assert captured == []
    assert all(
        value.npc.name != "Tavern Barmaid"
        for value in window.game_state_service.load_active_dashboard().npc_conversations
    )
    window.close()
    window.deleteLater()
    app.processEvents()
