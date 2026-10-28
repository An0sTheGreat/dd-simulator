from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QMimeData, QPointF
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from dd_simulator.state import (
    GameStateDatabase,
    GameStateService,
    ItemAction,
    ItemActionError,
    ItemCommand,
)
from dd_simulator.state.item_actions import build_item_metadata
from dd_simulator.ui.widgets.codex_cards import PowersCard
from dd_simulator.ui.widgets.codex_character import SkillDetailList
from dd_simulator.ui.widgets.inventory_grid import (
    INVENTORY_SLOT_MIME,
    EquipmentGrid,
)
from dd_simulator.ui.widgets.skills_grid import CombatSkillGridItem, SkillGridItem
from dd_simulator.ui.widgets.skills_grid import CombatSkillsGrid, SkillsGrid


def release_fifteen_service() -> tuple[GameStateDatabase, GameStateService]:
    database = GameStateDatabase.in_memory()
    service = GameStateService(database)
    service.initialize()
    service.load_active_dashboard()
    return database, service


def test_schema_thirteen_backfills_item_details_and_equipment_links() -> None:
    database, service = release_fifteen_service()
    dashboard = service.load_active_dashboard()
    lockpick = next(item for item in dashboard.inventory_preview if item.name == "Lockpick")
    potion = next(item for item in dashboard.inventory_preview if item.name == "Health Potion")
    coat = next(slot for slot in dashboard.equipment if slot.item_name == "Warden Coat")

    assert lockpick.category == "tool"
    assert "locked doors" in lockpick.description
    assert lockpick.weight > 0 and lockpick.value_gp > 0
    assert potion.healing == 15
    assert coat.item is not None and coat.item.compatible_slots == ("Body",)
    with database.connect() as connection:
        character = connection.execute(
            "SELECT carry_weight, equipment_armor_bonus FROM characters WHERE id = 'demo-kaelen'"
        ).fetchone()
    assert character["carry_weight"] > 0
    assert character["equipment_armor_bonus"] >= 3


def test_difficulty_changes_generated_healing_without_model_authority() -> None:
    story = build_item_metadata("Health Potion", difficulty="Story")
    adventurer = build_item_metadata("Health Potion", difficulty="Adventurer")
    deadly = build_item_metadata("Health Potion", difficulty="Deadly")

    assert story["healing_value"] == 18
    assert adventurer["healing_value"] == 15
    assert deadly["healing_value"] == 12


def test_inventory_item_equips_only_to_compatible_drop_target() -> None:
    _database, service = release_fifteen_service()
    service.execute_item_command(
        ItemCommand(ItemAction.UNEQUIP, 0, destination_index=27)
    )

    with pytest.raises(ItemActionError, match="can only be equipped"):
        service.execute_item_command(
            ItemCommand(ItemAction.EQUIP, 27, destination_index=2)
        )
    assert service.load_active_dashboard().inventory_preview[27].name == "Iron Dagger"

    service.execute_item_command(
        ItemCommand(ItemAction.EQUIP, 27, destination_index=1)
    )
    dashboard = service.load_active_dashboard()
    assert dashboard.equipment[1].item_name == "Iron Dagger"
    assert dashboard.inventory_preview[27].name == "Oak Shield"
    assert all(item.name != "Iron Dagger" for item in dashboard.inventory_preview)


def test_equipment_drop_widget_forwards_inventory_source_and_target() -> None:
    _app = QApplication.instance() or QApplication([])
    _database, service = release_fifteen_service()
    grid = EquipmentGrid(service.load_active_dashboard().equipment, columns=4)
    spy = QSignalSpy(grid.inventory_drop_requested)
    mime = QMimeData()
    mime.setData(INVENTORY_SLOT_MIME, b"39")

    class FakeDropEvent:
        accepted = False

        def mimeData(self):  # type: ignore[no-untyped-def]
            return mime

        def acceptProposedAction(self) -> None:
            self.accepted = True

        def ignore(self) -> None:
            self.accepted = False

    event = FakeDropEvent()
    grid.slots[1].dropEvent(event)
    assert event.accepted
    assert spy.count() == 1
    assert spy.at(0) == [39, 1]


def test_codex_preserves_skills_and_ability_spell_columns() -> None:
    _app = QApplication.instance() or QApplication([])
    _database, service = release_fifteen_service()
    dashboard = service.load_active_dashboard()
    skills = SkillDetailList(dashboard.skills)
    powers = PowersCard(dashboard.abilities, dashboard.spells)

    assert dashboard.skills and dashboard.abilities
    assert [row.skill.name for row in skills.rows] == [skill.name for skill in dashboard.skills]
    # Abilities and spells sit in two columns; a column with no entries hides.
    assert len(powers.ability_column.entries) == len(dashboard.abilities)
    assert len(powers.spell_column.entries) == len(dashboard.spells)
    assert not powers.ability_column.isHidden()
    assert powers.spell_column.isHidden() == (not dashboard.spells)
    skills.deleteLater()
    powers.deleteLater()


def test_item_hover_text_contains_mechanics_or_fallback_description() -> None:
    _app = QApplication.instance() or QApplication([])
    _database, service = release_fifteen_service()
    dashboard = service.load_active_dashboard()
    grid = EquipmentGrid(dashboard.equipment, columns=4)
    dagger = next(slot for slot in grid.slots if slot.slot.item_name == "Iron Dagger")
    charm = next(slot for slot in grid.slots if slot.slot.item_name == "Greenstone Charm")

    dagger.enterEvent(QEnterEvent(QPointF(), QPointF(), QPointF()))
    charm.enterEvent(QEnterEvent(QPointF(), QPointF(), QPointF()))
    assert dagger.hover_card.rows["Damage"].text() == "1d4 piercing"
    assert "Main Hand or Off Hand" in dagger.hover_card.subtitle_label.text()
    assert charm.hover_card.title_label.text() == "Greenstone Charm"
    assert dagger.hover_card.description_label.font().italic()
    assert charm.slot.item is not None and charm.slot.item.description
