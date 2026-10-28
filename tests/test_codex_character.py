from __future__ import annotations

from dataclasses import replace
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from dd_simulator.state import GameStateDatabase, GameStateService, ItemAction, ItemCommand
from dd_simulator.ui.power_icons import FALLBACK_ICON
from dd_simulator.ui.services.mock_data import build_phase_three_dashboard
from dd_simulator.ui.widgets.codex_character import (
    CharacterStrip,
    PaperdollPanel,
    SkillDetailList,
)
from dd_simulator.ui.widgets.inventory_grid import INVENTORY_SLOT_MIME, EquipmentGrid


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_character_strip_shows_identity_purse_carry_and_five_bars() -> None:
    _app()
    dashboard = build_phase_three_dashboard()
    strip = CharacterStrip(dashboard)

    assert strip.name_label.text() == dashboard.player.name
    assert strip.class_label.text() == (
        f"LEVEL {dashboard.player.level} {dashboard.player.character_class} · "
        f"{dashboard.campaign_name}"
    ).upper()
    assert strip.purse_label.text() == f"{dashboard.player.currency:,} gold"
    assert strip.carry_label.text() == (
        f"Carry {dashboard.player.carry_weight} / {dashboard.player.carry_capacity}"
    )
    assert [bar.property("resourceType") for bar in strip.bars] == [
        "health", "stamina", "focus", "resolve", "experience",
    ]
    assert all(not bar.isTextVisible() and bar.accessibleName() for bar in strip.bars)


def test_paperdoll_places_nine_labelled_slots_in_mockup_order() -> None:
    _app()
    dashboard = build_phase_three_dashboard()
    doll = PaperdollPanel(dashboard.player, dashboard.equipment)

    assert isinstance(doll, EquipmentGrid)
    assert [slot.slot.slot_name for slot in doll.slots] == [
        "Ring", "Head", "Neck", "Main Hand", "Body", "Hands",
        "Off Hand", "Ammunition", "Feet",
    ]
    assert [caption.text() for caption in doll.captions] == [
        "RING", "HEAD", "NECK", "MAIN HAND", "BODY", "HANDS", "OFF HAND", "AMMO", "FEET",
    ]
    positions = {slot.slot.slot_name: (slot.x(), slot.y()) for slot in doll.slots}
    assert positions["Ring"][1] == positions["Head"][1] == positions["Neck"][1]
    assert positions["Main Hand"][0] == positions["Body"][0] == positions["Hands"][0]
    assert positions["Off Hand"][0] == positions["Ammunition"][0] == positions["Feet"][0]
    assert doll.stats_label.text() == (
        f"AC {dashboard.player.armor_class} · PROF +{dashboard.player.proficiency_bonus}"
    )
    with_attack = PaperdollPanel(dashboard.player, dashboard.equipment, attack_bonus=6)
    assert "ATK +6" in with_attack.stats_label.text()


def test_paperdoll_drop_still_requests_the_equip_and_the_service_equips() -> None:
    _app()
    database = GameStateDatabase.in_memory()
    service = GameStateService(database)
    service.initialize()
    service.load_active_dashboard()
    service.execute_item_command(ItemCommand(ItemAction.UNEQUIP, 0, destination_index=27))
    dashboard = service.load_active_dashboard()
    assert dashboard.inventory_preview[27].name == "Iron Dagger"
    doll = PaperdollPanel(dashboard.player, dashboard.equipment)
    spy = QSignalSpy(doll.inventory_drop_requested)
    main_hand = next(slot for slot in doll.slots if slot.slot.slot_name == "Main Hand")
    mime = QMimeData()
    mime.setData(INVENTORY_SLOT_MIME, b"27")

    class FakeDropEvent:
        accepted = False

        def mimeData(self):  # type: ignore[no-untyped-def]
            return mime

        def acceptProposedAction(self) -> None:
            self.accepted = True

        def ignore(self) -> None:
            self.accepted = False

    enter = FakeDropEvent()
    main_hand.dragEnterEvent(enter)
    assert enter.accepted
    event = FakeDropEvent()
    main_hand.dropEvent(event)

    assert event.accepted
    assert spy.count() == 1
    source, target = spy.at(0)
    assert (source, target) == (27, main_hand.index)
    service.execute_item_command(ItemCommand(ItemAction.EQUIP, source, destination_index=target))
    assert service.load_active_dashboard().equipment[target].item_name == "Iron Dagger"


def test_paperdoll_shows_portrait_or_falls_back_to_initials() -> None:
    _app()
    dashboard = build_phase_three_dashboard()
    player = replace(dashboard.player, portrait_path="")
    doll = PaperdollPanel(player, dashboard.equipment)
    assert doll.portrait.text() == player.portrait_initials
    assert doll.portrait.property("hasPortrait") is False

    pictured = replace(player, portrait_path=str(FALLBACK_ICON))
    doll = PaperdollPanel(pictured, dashboard.equipment)
    assert doll.portrait.property("hasPortrait") is True
    assert not doll.portrait.pixmap().isNull()
    assert doll.portrait.text() == ""


def test_skill_rows_show_description_value_and_xp_fraction() -> None:
    _app()
    skills = build_phase_three_dashboard().skills
    detail = SkillDetailList(skills)

    assert len(detail.rows) == len(skills)
    for row, skill in zip(detail.rows, skills):
        assert row.name_label.text() == skill.name
        assert row.value_label.text() == str(skill.level)
        assert row.description_label.text() == skill.description
        assert (row.xp_bar.value(), row.xp_bar.maximum()) == (
            skill.current_xp, skill.next_level_xp,
        )
        assert f"XP: {skill.current_xp} / {skill.next_level_xp}" in row.toolTip()
        assert not row.icon_label.pixmap().isNull()
