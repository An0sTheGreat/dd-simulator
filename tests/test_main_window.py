from __future__ import annotations

import os
import json
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QProgressBar, QWidget

from dd_simulator.app import build_application
from dd_simulator.state import (
    CombatAction,
    GameStateDatabase,
    GameStateService,
)
from dd_simulator.state.combat import CombatService, EnemySpec
from dd_simulator.ui.main_window import MainWindow
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
    # Concept T regions replace the sidebar, narrative, minimap and utility tabs.
    assert window.concept_splitter.objectName() == "conceptTSplitter"
    assert window.concept_splitter.count() == 2
    for name in (
        "characterStrip", "paperdollPanel", "skillDetailList", "inventoryCard",
        "powersCard", "codexCardRow", "sceneView", "questProgressCard", "choiceGrid",
    ):
        assert window.findChild(QWidget, name) is not None, name
    assert window.conversation_view.parentWidget() is not None
    for retired in ("narrativePanel", "minimapPanel", "utilityTabBar", "resourceIndicatorStrip"):
        assert window.findChild(object, retired) is None, retired
    window.close()
    window.deleteLater()
    app.processEvents()


def test_phase_four_window_binds_mock_presentation_data(tmp_path: Path) -> None:
    app, window = build_window(tmp_path)
    assert window.character_strip.name_label.text() == "Kaelen Stormborne"
    assert window.scene_view.title.text() == "Greystone Road"
    assert window.scene_view.quest_card.title.text() == "The Lost Heirloom"
    assert window.character_strip.bars[0].value() == 42
    assert len(window.character_strip.findChildren(QProgressBar, "codexResourceBar")) == 5
    grid = window.scene_view.choice_grid
    assert sum(bool(button.text_label.full_text) for button in grid.choice_buttons) == 6
    action_input = window.findChild(QLineEdit, "sceneActionInput")
    assert action_input.isEnabled()
    assert not action_input.isReadOnly()
    assert action_input.placeholderText() == "Or write what Kaelen does…"
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
    # "Begin Encounter" was retired (combat starts from free text and travel);
    # outside combat the PowersCard offers Short Rest instead.
    app, window = build_window(tmp_path)
    assert window.findChild(object, "startCombatButton") is None
    rest = window.findChild(QWidget, "powersCardRest")
    assert rest is window.powers_card.rest_button
    assert not rest.isHidden()
    window._resolve_combat_action = lambda command: commands.append(command)  # type: ignore[method-assign]
    commands: list = []
    spy = QSignalSpy(window.powers_card.rest_requested)
    rest.click()
    assert spy.count() == 1
    assert [command.action for command in commands] == [CombatAction.RECOVER]
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
    # One enemy: automatic target (no picking); actions: six combat choices;
    # class abilities: the PowersCard; Short Rest hidden while the encounter runs.
    grid = window.scene_view.choice_grid
    assert window.scene_view.encounter_card is not None
    goblin = next(c for c in window.dashboard.combat.combatants if c.side == "enemy")
    assert grid.target_id == goblin.id
    assert len(grid.combat_actions) == 6
    assert all(button.isEnabled() for button in grid.choice_buttons)
    assert len(window.powers_card.ability_column.entries) == len(window.dashboard.abilities) == 4
    assert window.powers_card.rest_button.isHidden()
    assert not window.findChild(QLineEdit, "sceneActionInput").isEnabled()
    window.scene_view.combat_action_requested.disconnect(window._resolve_combat_action)
    spy = QSignalSpy(window.scene_view.combat_action_requested)
    grid.choice_buttons[0].click()
    assert spy.count() == 1
    assert spy.at(0)[0].action is CombatAction.ATTACK
    assert spy.at(0)[0].target_id == goblin.id
    window.close()
    window.deleteLater()
    app.processEvents()
    database.close()


def test_picked_enemy_is_the_power_target_and_survives_a_dashboard_reload(
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
    rolls = iter((20, 10, 1))
    service.combat = CombatService(database, roll=lambda _a, _b: next(rolls))
    service.start_combat(
        enemies=(
            EnemySpec("Training Goblin", 10, 10, 2, 4, distance_feet=5),
            EnemySpec("Training Wolf", 10, 10, 2, 4, distance_feet=5),
        )
    )
    window = MainWindow(
        theme_manager.available_themes(),
        service.load_active_dashboard(),
        game_state_service=service,
    )
    commands: list = []
    window._resolve_combat_action = commands.append  # type: ignore[method-assign]
    grid = window.scene_view.choice_grid
    enemies = [c.id for c in window.dashboard.combat.combatants if c.side == "enemy"]
    picked = next(e for e in enemies if e != grid.target_id)
    QTest.mouseClick(
        window.scene_view.encounter_card.rows[picked], Qt.MouseButton.LeftButton
    )
    assert grid.target_id == picked
    key = window.dashboard.abilities[0].key
    window.powers_card.action_activated.emit(key)
    assert commands[-1].target_id == picked and commands[-1].ability_key == key

    window._reload_dashboard(service.load_active_dashboard())
    assert window.scene_view.choice_grid.target_id == picked
    assert window.scene_view.encounter_card.rows[picked].property("targetSelected") is True
    window.close()
    window.deleteLater()
    app.processEvents()
    database.close()


def test_phase_four_window_keeps_panels_usable_at_minimum_size(tmp_path: Path) -> None:
    app, window = build_window(tmp_path)
    window.resize(1280, 720)
    window.show()
    app.processEvents()

    assert min(window.concept_splitter.sizes()) >= 360
    # The character strip is a one-line strip by design: it must keep its natural height.
    strip = window.character_strip
    assert strip.width() >= 120 and strip.height() >= strip.minimumSizeHint().height()
    for object_name in (
        "paperdollPanel",
        "skillDetailList",
        "inventoryCard",
        "powersCard",
        "sceneView",
        "questProgressCard",
        "choiceGrid",
    ):
        panel = window.findChild(object, object_name)
        assert panel is not None
        assert panel.width() >= 120
        assert panel.height() >= 70

    window.close()
    window.deleteLater()
    app.processEvents()


def test_scene_clock_shows_the_campaign_turn_counter(tmp_path: Path) -> None:
    # campaign_clock.turn_number is the live counter: every accepted turn increments it
    # and stamps its transcript rows with it. The seed's opening scene is turn 0.
    app = QApplication.instance() or QApplication([])
    themes = ThemeManager(
        themes_root=THEMES_ROOT, preferences_path=tmp_path / "clock.json", default_theme_id="high_fantasy",
    ).available_themes()
    database = GameStateDatabase.in_memory()
    service = GameStateService(database)
    service.initialize()
    service.ensure_demo_campaign()
    opening = MainWindow(themes, service.load_active_dashboard(), game_state_service=service)
    assert {m.turn_number for m in opening.dashboard.narrative.messages} == {0}
    assert opening.scene_view.tabs.clock_label.text() == "DAY 17 · TURN 0"
    opening.close()
    with database.transaction() as connection:
        connection.execute("UPDATE campaign_clock SET turn_number = 3")
    window = MainWindow(themes, service.load_active_dashboard(), game_state_service=service)
    assert window.scene_view.tabs.clock_label.text() == "DAY 17 · TURN 3"
    window.close()
    window.deleteLater()
    opening.deleteLater()
    app.processEvents()
    database.close()


def test_settings_font_size_applies_live_and_persists(tmp_path: Path) -> None:
    app, window, theme_manager = build_application([], config_dir=tmp_path)
    default_stylesheet = app.styleSheet()
    default_point_size = app.font().pointSizeF()
    panel = window.settings_panel
    panel.font_size_slider.setValue(105)
    # moving the slider only previews the value; Apply restyles the window
    assert window.font_size_preference == 100
    assert panel.font_size_value.text() == "105%" and panel.font_size_apply.isEnabled()
    panel.font_size_slider.setValue(107)  # snaps to whole 5% steps
    assert panel.font_size_slider.value() == 105
    panel.font_size_apply.click()
    app.processEvents()

    assert not panel.font_size_apply.isEnabled()
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
