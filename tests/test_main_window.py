from __future__ import annotations

import os
import json
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QLineEdit, QProgressBar, QWidget

from dd_simulator.app import build_application
from dd_simulator.state import (
    CombatAction,
    GameStateDatabase,
    GameStateService,
    SkillCheckResult,
)
from dd_simulator.state.combat import CombatService, EnemySpec
from dd_simulator.ui.main_window import MainWindow, SkillCheckPopup
from dd_simulator.ui.panels.common import highlight_recent_turn
from dd_simulator.ui.models.presentation import ConversationView, NpcView
from dd_simulator.ui.services.mock_data import build_phase_three_dashboard
from dd_simulator.ui.themes.theme_manager import ThemeManager


THEMES_ROOT = (
    Path(__file__).parents[1]
    / "src"
    / "dd_simulator"
    / "ui"
    / "themes"
)


def build_window(tmp_path: Path) -> tuple[QApplication, MainWindow]:
    app = QApplication.instance() or QApplication([])
    theme_manager = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "preferences.json",
        default_theme_id="high_fantasy",
    )
    window = MainWindow(
        theme_manager.available_themes(),
        build_phase_three_dashboard(),
    )
    return app, window


def test_phase_four_window_preserves_required_regions(tmp_path: Path) -> None:
    app, window = build_window(tmp_path)
    assert window.minimumWidth() == 1280
    assert window.minimumHeight() == 720
    assert window.right_sidebar.minimumWidth() == 360
    assert window.findChild(object, "narrativePanel") is not None
    assert window.findChild(object, "questObjectivePanel") is not None
    assert window.findChild(object, "minimapPanel") is not None
    assert window.findChild(object, "resourceIndicatorStrip") is None
    assert window.findChild(object, "playerResourceGrid") is not None
    assert window.findChild(object, "utilityTabBar") is not None
    window.close()
    window.deleteLater()
    app.processEvents()


def test_phase_four_window_binds_mock_presentation_data(tmp_path: Path) -> None:
    app, window = build_window(tmp_path)
    assert window.findChild(QLabel, "playerName").text() == "Kaelen Stormborne"
    assert window.findChild(QLabel, "sceneTitle").text() == "Greystone Road"
    assert window.findChild(QLabel, "activeQuestTitle").text() == "The Lost Heirloom"
    assert window.findChild(QProgressBar, "resourceBar").value() == 42
    assert len(window.findChild(object, "playerSummaryPanel").findChildren(QProgressBar, "resourceBar")) == 5
    assert len(window.findChildren(object, "suggestedActionButton")) == 6
    assert window.findChild(QLineEdit, "playerActionInput").isEnabled()
    assert not window.findChild(QLineEdit, "playerActionInput").isReadOnly()
    window.close()
    window.deleteLater()
    app.processEvents()


def test_header_uses_active_campaign_name(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    theme_manager = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "title-preferences.json",
        default_theme_id="high_fantasy",
    )
    dashboard = replace(
        build_phase_three_dashboard(), campaign_name="The Ashen Crown"
    )
    window = MainWindow(theme_manager.available_themes(), dashboard)

    assert window.application_title.text() == "The Ashen Crown"
    assert window.windowTitle() == "The Ashen Crown"
    window.close()
    window.deleteLater()
    app.processEvents()


def test_preset_campaign_header_hides_badge_and_window_title_stays_clean(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    theme_manager = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "preset-title-preferences.json",
        default_theme_id="high_fantasy",
    )
    dashboard = replace(
        build_phase_three_dashboard(),
        campaign_name="The Last Orrery of Sol",
        is_preset_campaign=True,
    )
    window = MainWindow(theme_manager.available_themes(), dashboard)
    badge = window.findChild(QLabel, "presetCampaignBadge")
    assert badge is not None and badge.text() == "- PRESET CAMPAIGN"
    assert badge.isHidden()
    assert window.windowTitle() == "The Last Orrery of Sol"
    window.close()
    window.deleteLater()
    app.processEvents()


def test_dashboard_reload_preserves_selected_people_conversation(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    theme_manager = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "people-selection-preferences.json",
        default_theme_id="high_fantasy",
    )
    conversations = tuple(
        ConversationView(
            npc=NpcView(
                id=f"npc-{index}",
                name=name,
                title="Local",
                portrait_initials=name[:1],
                status="neutral",
                disposition="neutral",
                relationship_score=0,
                available=True,
            ),
            messages=(),
            suggested_responses=(),
        )
        for index, name in enumerate(("First Person", "Second Person"), start=1)
    )
    dashboard = replace(
        build_phase_three_dashboard(), npc_conversations=conversations
    )
    window = MainWindow(theme_manager.available_themes(), dashboard)
    people_page = window.navigation_pages["people"]
    people_page.open_npc("npc-2")

    window._reload_dashboard(dashboard, target_page="people")

    assert window.navigation_pages["people"].selected_id == "npc-2"
    window.close()
    window.deleteLater()
    app.processEvents()


def test_item_move_refreshes_grids_without_rebuilding_content_stack(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    theme_manager = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "item-preferences.json",
        default_theme_id="high_fantasy",
    )
    database = GameStateDatabase.in_memory()
    service = GameStateService(database)
    service.initialize()
    service.ensure_demo_campaign()
    window = MainWindow(
        theme_manager.available_themes(),
        service.load_active_dashboard(),
        game_state_service=service,
    )
    old_stack = window.content_stack
    source = next(
        index
        for index, item in enumerate(window.dashboard.inventory_preview)
        if not item.is_empty
    )
    destination = next(
        index
        for index, item in enumerate(window.dashboard.inventory_preview)
        if item.is_empty
    )

    window._move_inventory_item(source, destination)
    app.processEvents()

    assert window.content_stack is old_stack
    assert not window.dashboard.inventory_preview[destination].is_empty
    assert window.dashboard.inventory_preview[source].is_empty
    window.close()
    window.deleteLater()
    app.processEvents()
    database.close()


def test_combat_tab_exposes_start_control_without_an_encounter(tmp_path: Path) -> None:
    app, window = build_window(tmp_path)
    start = window.findChild(object, "startCombatButton")
    assert start is not None
    assert window.findChild(object, "combatRestButton") is not None
    spy = QSignalSpy(window.utility_panel.combat_start_requested)
    start.click()
    assert spy.count() == 1
    window.close()
    window.deleteLater()
    app.processEvents()


def test_active_combat_tab_binds_targets_actions_and_locks_freeform_input(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    theme_manager = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "combat-preferences.json",
        default_theme_id="high_fantasy",
    )
    database = GameStateDatabase.in_memory()
    service = GameStateService(database)
    service.initialize()
    service.ensure_demo_campaign()
    rolls = iter((20, 1))
    service.combat = CombatService(database, roll=lambda _a, _b: next(rolls))
    service.start_combat(
        enemies=(EnemySpec("Training Goblin", 10, 10, 2, 4, distance_feet=5),)
    )
    window = MainWindow(
        theme_manager.available_themes(),
        service.load_active_dashboard(),
        game_state_service=service,
    )
    target = window.findChild(QComboBox, "combatTargetSelector")
    buttons = window.findChildren(object, "combatActionButton")

    assert target is not None and target.count() == 1
    assert len(buttons) == 7
    ability_selector = window.findChild(QComboBox, "combatClassAbilitySelector")
    assert ability_selector is not None and ability_selector.count() == 4
    assert not ability_selector.isEditable()
    assert not window.findChild(QLineEdit, "playerActionInput").isEnabled()
    window.utility_panel.combat_action_requested.disconnect(
        window._resolve_combat_action
    )
    spy = QSignalSpy(window.utility_panel.combat_action_requested)
    attack = next(button for button in buttons if button.property("combatAction") == "attack")
    attack.click()
    assert spy.count() == 1
    assert spy.at(0)[0].action is CombatAction.ATTACK
    window.close()
    window.deleteLater()
    app.processEvents()
    database.close()


def test_phase_four_window_keeps_panels_usable_at_minimum_size(tmp_path: Path) -> None:
    app, window = build_window(tmp_path)
    window.resize(1280, 720)
    window.show()
    app.processEvents()

    assert window.right_sidebar.width() >= 360
    for object_name in (
        "playerSummaryPanel",
        "locationSummaryPanel",
        "narrativePanel",
        "questObjectivePanel",
        "eventLogPanel",
        "recentEventsPanel",
        "minimapPanel",
        "utilityContentStack",
    ):
        panel = window.findChild(object, object_name)
        assert panel is not None
        assert panel.width() >= 120
        assert panel.height() >= 70

    window.close()
    window.deleteLater()
    app.processEvents()


def test_settings_font_size_applies_live_and_persists(tmp_path: Path) -> None:
    app, window, theme_manager = build_application([], config_dir=tmp_path)
    default_stylesheet = app.styleSheet()
    default_point_size = app.font().pointSizeF()
    window.settings_panel.font_size_increase.click()
    app.processEvents()

    assert window.font_size_preference == 105
    assert theme_manager.font_scale == 1.05
    assert app.styleSheet() != default_stylesheet
    assert app.font().pointSizeF() > default_point_size
    saved = json.loads((tmp_path / "preferences.json").read_text(encoding="utf-8"))
    assert saved["ui"]["font_size"] == 105
    assert window.settings_panel.font_size_value.text() == "105%"

    theme_index = window.theme_selector.findData("modern_proof")
    window.theme_selector.setCurrentIndex(theme_index)
    assert theme_manager.current_theme_id == "modern_proof"
    assert theme_manager.font_scale == 1.05

    window.close()
    window.deleteLater()
    app.processEvents()
    if window.game_state_service is not None:
        window.game_state_service.database.close()


def test_recent_turn_highlight_fades_smoothly_for_three_seconds() -> None:
    app = QApplication.instance() or QApplication([])
    owner = QWidget()
    player = QLabel("Player action", owner)
    response = QLabel("Resolved response", owner)

    highlight_recent_turn(owner, [player, response], reduced_motion=False)

    animations = owner._recent_turn_animations  # type: ignore[attr-defined]
    assert len(animations) == 2
    assert all(animation.duration() == 3000 for animation in animations)
    assert all(animation.startValue() == 255 for animation in animations)
    assert all(animation.endValue() == 0 for animation in animations)
    assert "rgba(255, 210, 80, 255)" in player.styleSheet()
    owner._recent_turn_clear()  # type: ignore[attr-defined]
    owner.deleteLater()
    app.processEvents()


def test_skill_check_popup_is_transient_and_complete(tmp_path: Path) -> None:
    app, window = build_window(tmp_path)
    result = SkillCheckResult("Persuasion", 14, 3, 17, 15, True)
    popup = SkillCheckPopup(result, window)

    assert popup.windowFlags() & Qt.WindowType.Popup
    assert popup.findChild(QLabel, "skillCheckOutcome").text() == "SUCCESS"
    text = "\n".join(label.text() for label in popup.findChildren(QLabel))
    assert "Player roll: 14" in text
    assert "Required to pass: 15" in text

    popup.close()
    window.close()
    window.deleteLater()
    app.processEvents()
