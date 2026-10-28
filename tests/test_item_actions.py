from __future__ import annotations

import os
from pathlib import Path
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from dd_simulator.app import build_application
from dd_simulator.state import (
    GameStateDatabase,
    GameStateError,
    GameStateService,
    ItemAction,
    ItemActionError,
    ItemCommand,
)
from dd_simulator.state.migrations import LATEST_SCHEMA_VERSION, MIGRATIONS
from dd_simulator.state.seed import DEMO_CAMPAIGN_ID, seed_demo_campaign
from dd_simulator.ui.widgets.inventory_grid import InventoryGrid, ItemHoverCard


def seeded_service(path: Path | None = None) -> tuple[GameStateDatabase, GameStateService]:
    database = GameStateDatabase.in_memory() if path is None else GameStateDatabase(path)
    database.initialize()
    seed_demo_campaign(database)
    return database, GameStateService(database)


def inventory_row(database: GameStateDatabase, slot_index: int):  # type: ignore[no-untyped-def]
    with database.connect() as connection:
        return connection.execute(
            "SELECT * FROM inventory_items WHERE character_id = 'demo-kaelen' "
            "AND slot_index = ?",
            (slot_index,),
        ).fetchone()


def visible_slot(service: GameStateService, name: str) -> int:
    return next(
        index for index, item in enumerate(service.load_active_dashboard().inventory_preview)
        if item.name == name
    )


def test_schema_v3_adds_item_rules_and_stable_equipment_links() -> None:
    database, _service = seeded_service()
    assert database.schema_version() == LATEST_SCHEMA_VERSION == 22

    potion = inventory_row(database, 2)
    assert potion["item_type"] == "consumable"
    assert potion["consumable"] == 1
    assert '"health":15' in potion["use_effect_json"]
    with database.connect() as connection:
        main_hand = connection.execute(
            "SELECT inventory_item_id FROM equipment_slots "
            "WHERE character_id = 'demo-kaelen' AND slot_name = 'Main Hand'"
        ).fetchone()
    assert main_hand["inventory_item_id"] == "item-0"


def test_existing_schema_v2_inventory_migrates_without_data_loss(tmp_path: Path) -> None:
    path = tmp_path / "phase6.db"
    connection = sqlite3.connect(path)
    connection.executescript(MIGRATIONS[0][1])
    connection.executescript(MIGRATIONS[1][1])
    connection.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
        "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    connection.executemany(
        "INSERT INTO schema_migrations(version) VALUES (?)",
        ((1,), (2,)),
    )
    connection.execute("INSERT INTO campaigns(id, name) VALUES ('old', 'Old Campaign')")
    connection.execute(
        "INSERT INTO characters(id, campaign_id, name, inventory_capacity, is_player) "
        "VALUES ('old-player', 'old', 'Old Hero', 20, 1)"
    )
    connection.execute(
        "INSERT INTO inventory_items(id, character_id, slot_index, name, quantity) "
        "VALUES ('old-potion', 'old-player', 0, 'Health Potion', 2)"
    )
    connection.execute(
        "INSERT INTO equipment_slots(id, character_id, slot_index, slot_name, item_name) "
        "VALUES ('old-hand', 'old-player', 0, 'Main Hand', 'Health Potion')"
    )
    connection.commit()
    connection.close()

    database = GameStateDatabase(path)
    assert database.initialize() == 22
    with database.connect() as migrated:
        potion = migrated.execute(
            "SELECT quantity, item_type, consumable, use_effect_json "
            "FROM inventory_items WHERE id = 'old-potion'"
        ).fetchone()
        equipment = migrated.execute(
            "SELECT inventory_item_id FROM equipment_slots WHERE id = 'old-hand'"
        ).fetchone()

    assert tuple(potion[:3]) == (2, "consumable", 1)
    assert '"health":15' in potion["use_effect_json"]
    assert equipment["inventory_item_id"] == "old-potion"


def test_use_consumable_updates_resource_quantity_and_event_atomically() -> None:
    database, service = seeded_service()
    with database.transaction() as connection:
        connection.execute(
            "UPDATE character_resources SET current_value = 20 "
            "WHERE character_id = 'demo-kaelen' AND resource_type = 'health'"
        )

    result = service.execute_item_command(ItemCommand(ItemAction.USE, visible_slot(service, "Health Potion")))

    assert result.item_name == "Health Potion"
    assert "Health 20 to 35" in result.summary
    assert inventory_row(database, 2)["quantity"] == 2
    dashboard = service.load_active_dashboard()
    health = next(resource for resource in dashboard.sidebar_resources if resource.resource_type == "health")
    assert health.current == 35
    assert dashboard.recent_events[-1].category == "inventory"
    assert "Health Potion" in dashboard.recent_events[-1].summary


def test_no_effect_does_not_consume_item_or_record_event() -> None:
    database, service = seeded_service()
    with database.connect() as connection:
        before_events = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    with pytest.raises(ItemActionError, match="no effect"):
        service.execute_item_command(ItemCommand(ItemAction.USE, visible_slot(service, "Health Potion")))

    assert inventory_row(database, 2)["quantity"] == 3
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before_events


def test_last_consumable_is_removed_and_charged_item_remains_at_zero() -> None:
    database, service = seeded_service()
    with database.transaction() as connection:
        connection.execute(
            "UPDATE character_resources SET current_value = 10 "
            "WHERE character_id = 'demo-kaelen' AND resource_type = 'health'"
        )
        connection.execute("UPDATE inventory_items SET quantity = 1 WHERE id = 'item-2'")
        connection.execute("UPDATE inventory_items SET charges = 1 WHERE id = 'item-12'")

    service.execute_item_command(ItemCommand(ItemAction.USE, visible_slot(service, "Health Potion")))
    assert inventory_row(database, 2) is None

    flint_slot = visible_slot(service, "Flint & Steel")
    service.execute_item_command(ItemCommand(ItemAction.USE, flint_slot))
    assert inventory_row(database, 12)["charges"] == 0
    with pytest.raises(ItemActionError, match="no charges"):
        service.execute_item_command(ItemCommand(ItemAction.USE, flint_slot))
    assert inventory_row(database, 12)["charges"] == 0


def test_durable_item_use_updates_inventory_and_equipment_condition() -> None:
    database, service = seeded_service()

    service.execute_item_command(ItemCommand(ItemAction.UNEQUIP, 0))
    service.execute_item_command(ItemCommand(ItemAction.USE, visible_slot(service, "Iron Dagger")))

    assert inventory_row(database, 0)["durability"] == 81
    dashboard = service.load_active_dashboard()
    assert dashboard.equipment[0].item_name is None


def test_equip_unequip_drop_and_quest_item_guards() -> None:
    database, service = seeded_service()

    service.execute_item_command(ItemCommand(ItemAction.UNEQUIP, 7))
    assert service.load_active_dashboard().equipment[7].item_name is None
    ring_slot = visible_slot(service, "Silver Ring")
    service.execute_item_command(ItemCommand(ItemAction.EQUIP, ring_slot))
    assert service.load_active_dashboard().equipment[7].item_name == "Silver Ring"
    assert all(item.name != "Silver Ring" for item in service.load_active_dashboard().inventory_preview)
    service.execute_item_command(ItemCommand(ItemAction.UNEQUIP, 7))
    service.execute_item_command(ItemCommand(ItemAction.DROP, visible_slot(service, "Silver Ring")))
    assert inventory_row(database, 14) is None

    with pytest.raises(ItemActionError, match="quest item"):
        service.execute_item_command(ItemCommand(ItemAction.DROP, visible_slot(service, "Map Fragment")))
    assert inventory_row(database, 3) is not None


def test_legacy_equipment_without_inventory_link_moves_to_free_slot() -> None:
    database, service = seeded_service()

    result = service.execute_item_command(ItemCommand(ItemAction.UNEQUIP, 3))

    assert result.item_name == "Warden Coat"
    with database.connect() as connection:
        row = connection.execute(
            "SELECT * FROM inventory_items WHERE character_id = 'demo-kaelen' "
            "AND name = 'Warden Coat'"
        ).fetchone()
    assert row is not None
    assert row["name"] == "Warden Coat"
    assert row["equip_slot"] == "Body"
    assert row["durability"] == 91


def test_event_failure_rolls_back_resource_and_consumption() -> None:
    database, service = seeded_service()
    with database.transaction() as connection:
        connection.execute(
            "UPDATE character_resources SET current_value = 20 "
            "WHERE character_id = 'demo-kaelen' AND resource_type = 'health'"
        )
        connection.execute(
            "CREATE TRIGGER reject_inventory_event BEFORE INSERT ON events "
            "WHEN NEW.category = 'inventory' BEGIN SELECT RAISE(ABORT, 'event rejected'); END"
        )

    with pytest.raises(GameStateError, match="event rejected"):
        service.execute_item_command(ItemCommand(ItemAction.USE, visible_slot(service, "Health Potion")))

    assert inventory_row(database, 2)["quantity"] == 3
    with database.connect() as connection:
        health = connection.execute(
            "SELECT current_value FROM character_resources "
            "WHERE character_id = 'demo-kaelen' AND resource_type = 'health'"
        ).fetchone()[0]
    assert health == 20


def test_item_mutation_persists_after_database_reopen(tmp_path: Path) -> None:
    path = tmp_path / "persistent.db"
    database, service = seeded_service(path)
    service.execute_item_command(ItemCommand(ItemAction.USE, visible_slot(service, "Torch")))
    database.close()

    reopened = GameStateDatabase(path)
    reopened.initialize()
    dashboard = GameStateService(reopened).load_campaign(DEMO_CAMPAIGN_ID)
    assert dashboard.inventory_preview[visible_slot(GameStateService(reopened), "Torch")].quantity == 3
    assert any("Lit a Torch" in event.summary for event in dashboard.recent_events)


def test_state_backed_ui_action_refreshes_inventory_and_preserves_page(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.controller.navigate("dashboard")
    window.utility_panel.set_current_tab(2)

    torch_slot = visible_slot(window.game_state_service, "Torch")
    window.controller.request_context_action("inventory", torch_slot, "use")
    app.processEvents()

    assert window.current_page == "dashboard"
    assert window.utility_panel.current_tab() == 2
    assert window.dashboard.inventory_preview[torch_slot].quantity == 3
    assert "Lit a Torch" in window.statusBar().currentMessage()
    assert any("Lit a Torch" in event.summary for event in window.dashboard.recent_events)
    window.close()
    window.deleteLater()
    app.processEvents()


def test_inventory_menu_disables_actions_that_rules_reject() -> None:
    database, service = seeded_service()
    grid = InventoryGrid(service.load_active_dashboard().inventory_preview)

    potion_actions = {action.text(): action.isEnabled() for action in grid.slots[visible_slot(service, "Health Potion")].build_context_menu().actions()}
    quest_actions = {action.text(): action.isEnabled() for action in grid.slots[visible_slot(service, "Map Fragment")].build_context_menu().actions()}

    assert all(item.name != "Iron Dagger" for item in service.load_active_dashboard().inventory_preview)
    assert all(item.name != "Silver Ring" for item in service.load_active_dashboard().inventory_preview)
    assert potion_actions == {"Inspect": True, "Use": True, "Equip": False, "Drop": True}
    assert quest_actions["Drop"] is False
    assert quest_actions["Use"] is False
    flint = grid.slots[visible_slot(service, "Flint & Steel")].item
    hover = ItemHoverCard(flint, grid)
    assert "Uses: 20/20" in [label.text() for label in hover.detail_labels]
    hover.deleteLater()

    grid.deleteLater()
    database.close()
