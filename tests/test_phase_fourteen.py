from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtCore import QMimeData
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from dd_simulator.state import (
    GameStateDatabase,
    GameStateService,
    ItemAction,
    ItemActionError,
    ItemCommand,
)
from dd_simulator.state.migrations import LATEST_SCHEMA_VERSION
from dd_simulator.state.seed import DEMO_CAMPAIGN_ID
from dd_simulator.ui.widgets.scene_view import ChoiceGrid
from dd_simulator.ui.services.mock_data import build_phase_three_dashboard
from dd_simulator.ui.widgets.inventory_grid import EQUIPMENT_SLOT_MIME, InventoryGrid


def phase_fourteen_service() -> tuple[GameStateDatabase, GameStateService]:
    database = GameStateDatabase.in_memory()
    service = GameStateService(database)
    service.initialize()
    service.load_active_dashboard()
    return database, service


def test_schema_twelve_migrates_inventory_and_npc_conversations() -> None:
    database, service = phase_fourteen_service()
    dashboard = service.load_active_dashboard()

    assert database.schema_version() == LATEST_SCHEMA_VERSION == 23
    assert len(dashboard.inventory_preview) == 36
    visible = {item.name for item in dashboard.inventory_preview if item.name}
    equipped = {slot.item_name for slot in dashboard.equipment if slot.item_name}
    assert "Iron Dagger" in equipped and "Iron Dagger" not in visible
    assert "Oak Shield" in equipped and "Oak Shield" not in visible
    assert dashboard.present_npcs[0].name == "Roadside Merchant"


def test_inventory_move_sort_equip_and_unequip_are_atomic() -> None:
    _database, service = phase_fourteen_service()
    dashboard = service.load_active_dashboard()
    first_id = dashboard.inventory_preview[0].id
    second_id = dashboard.inventory_preview[1].id

    service.move_inventory_item(0, 1)
    swapped = service.load_active_dashboard().inventory_preview
    assert swapped[0].id == second_id and swapped[1].id == first_id

    service.execute_item_command(ItemCommand(ItemAction.UNEQUIP, 7))
    unequipped = service.load_active_dashboard()
    assert unequipped.equipment[7].item_name is None
    ring_index = next(
        index for index, item in enumerate(unequipped.inventory_preview)
        if item.name == "Silver Ring"
    )
    service.execute_item_command(ItemCommand(ItemAction.EQUIP, ring_index))
    reequipped = service.load_active_dashboard()
    assert reequipped.equipment[7].item_name == "Silver Ring"
    assert all(item.name != "Silver Ring" for item in reequipped.inventory_preview)

    service.auto_sort_inventory()
    sorted_items = [item for item in service.load_active_dashboard().inventory_preview if item.name]
    assert sorted_items[0].quest_item


def test_inventory_auto_sort_modes_are_deterministic() -> None:
    _database, service = phase_fourteen_service()
    rarity_rank = {"legendary": 0, "epic": 1, "rare": 2, "uncommon": 3, "common": 4}

    service.auto_sort_inventory("rarity")
    items = [item for item in service.load_active_dashboard().inventory_preview if item.name]
    assert [rarity_rank.get(item.rarity.casefold(), 5) for item in items] == sorted(
        rarity_rank.get(item.rarity.casefold(), 5) for item in items
    )

    service.auto_sort_inventory("type")
    items = [item for item in service.load_active_dashboard().inventory_preview if item.name]
    assert [item.item_type.casefold() for item in items] == sorted(
        item.item_type.casefold() for item in items
    )

    service.auto_sort_inventory("value")
    items = [item for item in service.load_active_dashboard().inventory_preview if item.name]
    assert [item.value_gp for item in items] == sorted(
        (item.value_gp for item in items), reverse=True
    )

    with pytest.raises(ItemActionError, match="Unknown inventory sort mode"):
        service.auto_sort_inventory("random")


def test_equipment_can_be_dropped_into_a_chosen_empty_inventory_slot() -> None:
    _database, service = phase_fourteen_service()
    service.execute_item_command(
        ItemCommand(ItemAction.UNEQUIP, 7, destination_index=27)
    )
    dashboard = service.load_active_dashboard()

    assert dashboard.equipment[7].item_name is None
    assert dashboard.inventory_preview[27].name == "Silver Ring"

    with pytest.raises(ItemActionError, match="empty inventory slot"):
        service.execute_item_command(
            ItemCommand(ItemAction.UNEQUIP, 0, destination_index=0)
        )
    assert service.load_active_dashboard().equipment[0].item_name == "Iron Dagger"

    service.auto_sort_inventory()
    sorted_dashboard = service.load_active_dashboard()
    assert sorted_dashboard.equipment[0].item_name == "Iron Dagger"
    assert all(item.name != "Iron Dagger" for item in sorted_dashboard.inventory_preview)


def test_equipment_drop_mime_is_forwarded_with_destination_slot() -> None:
    _app = QApplication.instance() or QApplication([])
    grid = InventoryGrid((), columns=4, slot_count=32)
    spy = QSignalSpy(grid.equipment_drop_requested)
    mime = QMimeData()
    mime.setData(EQUIPMENT_SLOT_MIME, b"7")

    class FakeDropEvent:
        accepted = False

        def mimeData(self):  # type: ignore[no-untyped-def]
            return mime

        def acceptProposedAction(self) -> None:
            self.accepted = True

        def ignore(self) -> None:
            self.accepted = False

    event = FakeDropEvent()
    grid.slots[27].dropEvent(event)

    assert event.accepted
    assert spy.count() == 1
    assert spy.at(0) == [7, 27]


def test_dialogue_persists_player_first_check_relationship_and_history() -> None:
    database, service = phase_fourteen_service()
    result = service.resolve_npc_dialogue(
        "npc-roadside-merchant", "Try to persuade them to share more."
    )
    dashboard = service.load_active_dashboard()
    conversation = dashboard.npc_conversations[0]

    assert result.check_summary.startswith("Persuasion check: d20")
    assert [message.kind for message in conversation.messages[-3:]] == [
        "player", "monologue", "spoken"
    ]
    assert conversation.messages[-3].text == result.player_text
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM npc_conversations").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM npc_memories").fetchone()[0] == 1


def test_story_location_is_discovered_and_highlighted_on_map() -> None:
    database, service = phase_fourteen_service()
    with database.transaction() as connection:
        connection.execute(
            "UPDATE locations SET is_current = 0 WHERE campaign_id = ?",
            (DEMO_CAMPAIGN_ID,),
        )
        connection.execute(
            "UPDATE locations SET is_current = 1, discovered = 0 "
            "WHERE id = 'location-greystone-keep'"
        )

    dashboard = service.load_active_dashboard()
    assert dashboard.world_map is not None
    assert dashboard.world_map.current_location_id == "location-greystone-keep"
    keep = next(location for location in dashboard.world_map.locations if location.name == "Greystone Keep")
    assert keep.current and keep.visited
    assert dashboard.present_npcs[0].name == "Lord Aric"


def test_suggested_narrative_response_submits_immediately() -> None:
    _app = QApplication.instance() or QApplication([])
    panel = ChoiceGrid(build_phase_three_dashboard().narrative.suggested_actions)
    spy = QSignalSpy(panel.submission_requested)
    panel.choice_buttons[0].click()
    assert spy.count() == 1
    assert spy.at(0)[0] == panel.choice_buttons[0].text_label.full_text
    assert spy.at(0)[0] == build_phase_three_dashboard().narrative.suggested_actions[0]
