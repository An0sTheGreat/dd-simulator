from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QSplitter, QWidget

from dd_simulator.ui.main_window import MainWindow
from dd_simulator.ui.models.presentation import (
    EventView,
    EquipmentSlotView,
    InventorySlotView,
    QuestListItemView,
    ResourceView,
    SkillView,
)
from dd_simulator.ui.panels.activity_panels import EventLogPanel, RecentEventsPanel
from dd_simulator.ui.services.mock_data import build_phase_three_dashboard
from dd_simulator.ui.themes.theme_manager import ThemeManager
from dd_simulator.ui.widgets.inventory_grid import (
    EquipmentGrid,
    EquipmentSlotWidget,
    InventoryGrid,
    InventorySlotWidget,
    ItemHoverCard,
)
from dd_simulator.ui.widgets.quest_list import QuestListItem, QuestListWidget
from dd_simulator.ui.widgets.resource_bar import ResourceBar
from dd_simulator.ui.widgets.codex_character import SkillDetailRow
from dd_simulator.ui.widgets.skills_grid import SkillGridItem
from dd_simulator.ui.widgets.skills_grid import SkillsGrid


THEMES_ROOT = (
    Path(__file__).parents[1]
    / "src"
    / "dd_simulator"
    / "ui"
    / "themes"
)


def test_phase_three_mock_data_has_configurable_widget_states() -> None:
    dashboard = build_phase_three_dashboard()
    assert len(dashboard.inventory_preview) == 20
    assert sum(item.is_empty for item in dashboard.inventory_preview) == 3
    assert sum(item.selected for item in dashboard.inventory_preview) == 1
    assert sum(item.quest_item for item in dashboard.inventory_preview) == 2
    assert len(dashboard.equipment) == 9
    assert len(dashboard.skills) == 8
    assert len(dashboard.quest_list) == 3


def test_phase_three_window_binds_counts_selection_and_tooltips(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    manager = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "preferences.json",
        default_theme_id="high_fantasy",
    )
    mock = build_phase_three_dashboard()
    occupied = tuple(item for item in mock.inventory_preview if not item.is_empty)
    window = MainWindow(manager.available_themes(), replace(mock, inventory=occupied))

    inventory = window.inventory_card.grid.findChildren(InventorySlotWidget)
    equipment = window.paperdoll_panel.findChildren(EquipmentSlotWidget)
    skills = window.skill_detail_list.findChildren(SkillDetailRow)
    resources = window.character_strip.findChildren(ResourceBar)

    # The card lays the bag out at real positions: a 5x5 viewport, not a fixed 36-slot preview.
    assert len(inventory) == window.inventory_card.grid.slot_count == 25
    assert sum(not bool(slot.property("empty")) for slot in inventory) == len(occupied)
    assert len(equipment) == 9
    assert len(skills) == 8
    assert len(resources) == 5
    # The quest list is gone from the window; the scene's quest card carries the quest.
    assert window.findChildren(QuestListItem) == []
    assert sum(bool(slot.property("selected")) for slot in inventory) == 1
    assert all(
        widget.hover_card is None
        for widget in (*inventory, *equipment)
        if not bool(widget.property("empty"))
    )
    for skill in skills:
        skill_card = skill.build_hover_card()
        assert skill.skill.name in skill_card.text_content()
        skill_card.deleteLater()

    window.close()
    window.deleteLater()
    app.processEvents()


def test_dashboard_resize_handles_match_the_summary_divider(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    manager = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "preferences.json",
        default_theme_id="high_fantasy",
    )
    window = MainWindow(manager.available_themes(), build_phase_three_dashboard())

    # Only the concept splitter and the people splitter remain; their handles must match.
    window.resize(1600, 900)
    window.show()
    app.processEvents()
    reference_width = window.concept_splitter.handleWidth()
    people = window.findChild(QSplitter, "peopleTradeConversationSplitter")
    assert people is not None and people.handleWidth() == reference_width
    assert {s.objectName() for s in window.findChildren(QSplitter)} == {
        "conceptTSplitter", "peopleTradeConversationSplitter"
    }

    for theme_id in ("high_fantasy", "modern_proof"):
        stylesheet = manager.load_theme(theme_id).stylesheet
        assert "QSplitter#narrativeQuestSplitter::handle" not in stylesheet
        assert "QSplitter#dashboardRowsSplitter::handle" not in stylesheet
        assert "QSplitter#summarySplitter::handle" not in stylesheet

    window.close()
    window.deleteLater()
    app.processEvents()


def test_data_widgets_present_empty_states() -> None:
    app = QApplication.instance() or QApplication([])
    inventory = InventoryGrid((), columns=2, slot_count=4)
    equipment = EquipmentGrid(())
    skills = SkillsGrid(())
    quests = QuestListWidget(())
    recent_events = RecentEventsPanel(())

    slots = inventory.findChildren(InventorySlotWidget)
    assert len(slots) == 4
    assert all(bool(slot.property("empty")) for slot in slots)
    assert equipment.findChild(QLabel, "equipmentGridEmptyState") is not None
    assert skills.findChild(QLabel, "skillsGridEmptyState") is not None
    assert quests.findChild(QLabel, "questListEmptyState") is not None
    assert recent_events.findChild(QLabel, "recentEventsEmptyState") is not None

    inventory.deleteLater()
    equipment.deleteLater()
    skills.deleteLater()
    quests.deleteLater()
    recent_events.deleteLater()
    app.processEvents()


def test_item_hover_card_uses_two_columns_and_dismisses_on_interaction() -> None:
    app = QApplication.instance() or QApplication([])
    slot = InventorySlotWidget(
        InventorySlotView(
            "Iron Dagger",
            quantity=1,
            rarity="uncommon",
            durability=82,
            maximum_durability=100,
            description="A balanced dagger recovered on Greystone Road.",
            equip_slot="Main Hand",
            damage="1d4 piercing",
            category="weapon",
            weight=1.0,
            value_gp=4,
            compatible_slots=("Main Hand", "Off Hand"),
        ),
        0,
    )
    slot.resize(180, 50)
    slot.show()
    app.processEvents()

    card = slot.hover_card
    assert card is not None
    card.show_near(slot.mapToGlobal(QPoint(slot.width(), 0)))
    app.processEvents()
    assert card.isVisible()
    assert {name: label.text() for name, label in card.rows.items()} == {
        "Damage": "1d4 piercing",
        "Durability": "82 / 100",
        "Weight": "1.0 lb",
        "Value": "4 gold",
    }
    assert card.subtitle_label.text() == "Uncommon · Weapon · Main Hand or Off Hand"
    assert card.description_label.font().italic()

    QTest.mouseClick(slot, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert not card.isVisible()
    assert slot.hover_card is None

    slot.close()
    slot.deleteLater()
    app.processEvents()


def test_inventory_hover_compares_matching_equipped_item() -> None:
    app = QApplication.instance() or QApplication([])
    candidate = InventorySlotView(
        "Steel Dagger",
        equip_slot="Main Hand",
        compatible_slots=("Main Hand", "Off Hand"),
        category="weapon",
    )
    equipped = InventorySlotView(
        "Iron Sword",
        equip_slot="Main Hand",
        compatible_slots=("Main Hand",),
        category="weapon",
    )
    grid = InventoryGrid(
        (candidate,),
        slot_count=1,
        equipment=(EquipmentSlotView("Main Hand", "Iron Sword", item=equipped),),
    )
    slot = grid.slots[0]
    assert slot.comparison_item is not None
    assert slot.comparison_item.name == "Iron Sword"
    assert slot.comparison_item.status == "Equipped"

    slot.hover_card = ItemHoverCard(slot.item, slot)
    slot.comparison_hover_card = ItemHoverCard(
        slot.comparison_item, slot, equipped_comparison=True
    )
    assert "Equipped" in slot.comparison_hover_card.subtitle_label.text().split(" · ")
    slot.hide_hover_card()
    grid.deleteLater()
    app.processEvents()


def test_vertical_fill_skills_use_six_equal_columns_after_filling_rows() -> None:
    app = QApplication.instance() or QApplication([])
    skills = tuple(SkillView(f"Skill {index}", index) for index in range(18))
    grid = SkillsGrid(skills, columns=6, vertical_fill=True)
    grid.resize(1200, 160)
    grid.show()
    app.processEvents()

    positions = {
        item.accessibleName().split(", level", 1)[0]: grid.grid.getItemPosition(
            grid.grid.indexOf(item)
        )
        for item in grid.findChildren(SkillGridItem)
    }
    assert positions["Skill 0"][:2] == (0, 0)
    assert positions["Skill 2"][:2] == (2, 0)
    assert positions["Skill 3"][:2] == (0, 1)
    assert positions["Skill 17"][:2] == (2, 5)
    widths = [grid.grid.cellRect(0, column).width() for column in range(6)]
    assert min(widths) > 0
    assert max(widths) - min(widths) <= 1
    first_column = sorted(
        (
            item
            for item in grid.findChildren(SkillGridItem)
            if positions[item.accessibleName().split(", level", 1)[0]][1] == 0
        ),
        key=lambda item: item.y(),
    )
    gaps = [
        following.y() - (current.y() + current.height())
        for current, following in zip(first_column, first_column[1:])
    ]
    assert gaps and all(4 <= gap <= 8 for gap in gaps)

    grid.close()
    grid.deleteLater()
    app.processEvents()


def test_event_panels_scroll_instead_of_compressing_text() -> None:
    app = QApplication.instance() or QApplication([])
    events = tuple(
        EventView(
            f"Day 1, turn {index}",
            "combat" if index % 2 else "system",
            "A complete event summary remains readable when the dashboard row is resized. "
            * 2,
        )
        for index in range(20)
    )
    event_log = EventLogPanel(events)
    recent = RecentEventsPanel(events)
    event_log.resize(520, 180)
    recent.resize(520, 180)
    event_log.show()
    recent.show()
    app.processEvents()

    assert event_log.entries.alignment() == Qt.AlignmentFlag.AlignBottom
    recent_entries = recent.findChild(QWidget, "recentEventEntries").layout()
    assert recent_entries.alignment() == Qt.AlignmentFlag.AlignBottom

    event_scroll = event_log.findChild(QScrollArea, "eventLogScrollArea")
    recent_scroll = recent.findChild(QScrollArea, "recentEventsScrollArea")
    assert event_scroll.verticalScrollBar().maximum() > 0
    assert recent_scroll.verticalScrollBar().maximum() > 0
    event_font = event_log.findChild(QLabel, "eventLogEntry").font().pointSizeF()
    recent_font = recent.findChild(QLabel, "recentEventEntry").font().pointSizeF()
    event_log.resize(520, 110)
    recent.resize(520, 110)
    app.processEvents()
    assert event_log.findChild(QLabel, "eventLogEntry").font().pointSizeF() == event_font
    assert recent.findChild(QLabel, "recentEventEntry").font().pointSizeF() == recent_font

    event_log.close()
    recent.close()
    event_log.deleteLater()
    recent.deleteLater()
    app.processEvents()


def test_quest_rows_are_compact_and_scroll_after_ten_visible_entries() -> None:
    app = QApplication.instance() or QApplication([])
    quests = tuple(
        QuestListItemView(f"Quest {index}", "active", 1, 3)
        for index in range(12)
    )
    quest_list = QuestListWidget(quests)
    quest_list.resize(900, 560)
    quest_list.show()
    app.processEvents()

    rows = quest_list.findChildren(QuestListItem)
    assert len(rows) == 12
    assert all(row.height() == 52 for row in rows)
    assert rows[9].geometry().bottom() <= quest_list.viewport().height()
    assert quest_list.verticalScrollBar().maximum() == 0
    assert rows[10].geometry().left() > rows[0].geometry().left()

    quest_list.close()
    quest_list.deleteLater()
    app.processEvents()


def test_resource_bar_rebinds_from_presentation_data() -> None:
    app = QApplication.instance() or QApplication([])
    bar = ResourceBar(ResourceView("Focus", 4, 10, "focus", "Technique energy"))
    assert bar.value() == 4
    assert bar.toolTip() == "Technique energy"

    bar.update_view(ResourceView("Focus", 7, 12, "focus"))
    assert bar.value() == 7
    assert bar.maximum() == 12
    assert "Focus" in bar.format()

    bar.deleteLater()
    app.processEvents()


def test_resource_bar_animates_and_can_update_immediately() -> None:
    app = QApplication.instance() or QApplication([])
    bar = ResourceBar(ResourceView("Health", 10, 20, "health"))

    bar.update_view(ResourceView("Health", 16, 20, "health"), animate=True)
    assert bar._animation is not None
    assert bar._animation.endValue() == 16
    bar._animation.setCurrentTime(ResourceBar.ANIMATION_DURATION_MS)
    assert bar.value() == 16

    bar.update_view(ResourceView("Health", 7, 20, "health"), animate=False)
    assert bar.value() == 7
    bar.deleteLater()
    app.processEvents()


def test_equipment_grid_rebinds_without_replacing_grid() -> None:
    app = QApplication.instance() or QApplication([])
    grid = EquipmentGrid(
        (EquipmentSlotView("Head", None, ""),),
        slot_names=("Head",),
    )
    layout = grid.grid
    grid.set_slots((EquipmentSlotView("Head", "Iron Helm", "90/100"),))

    assert grid.grid is layout
    assert len(grid.slots) == 1
    assert grid.slots[0].slot.item_name == "Iron Helm"
    grid.deleteLater()
    app.processEvents()


def test_item_selection_does_not_add_a_theme_outline(tmp_path: Path) -> None:
    manager = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "preferences.json",
        default_theme_id="high_fantasy",
    )
    for theme_id in ("high_fantasy", "modern_proof"):
        stylesheet = manager.load_theme(theme_id).stylesheet
        assert 'inventorySlot[selected="true"]' not in stylesheet
        assert 'equipmentSlot[selected="true"]' not in stylesheet
        assert "inventorySlot:focus" not in stylesheet
        assert "equipmentSlot:focus" not in stylesheet


def test_item_hover_surfaces_are_fully_opaque(tmp_path: Path) -> None:
    manager = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "preferences.json",
        default_theme_id="high_fantasy",
    )
    expected = {
        "high_fantasy": "background: rgba(33, 30, 22, 255);",
        "modern_proof": "background: rgba(27, 27, 29, 255);",
    }
    for theme_id, declaration in expected.items():
        assert declaration in manager.load_theme(theme_id).stylesheet
