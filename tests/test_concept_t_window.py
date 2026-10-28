from __future__ import annotations

import os
from pathlib import Path
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

from dd_simulator.app import build_application
from dd_simulator.state import GameStateDatabase, GameStateService, ProposedStateChange
from dd_simulator.state.combat import CombatService, EnemySpec
from dd_simulator.ui.main_window import MainWindow
from dd_simulator.ui.services.mock_data import build_phase_three_dashboard
from dd_simulator.ui.services.ui_preferences import UiPreferencesStore
from dd_simulator.ui.themes.theme_manager import ThemeManager
from tests.test_action_resolution import FixedProvider, outcome


THEMES_ROOT = Path(__file__).parents[1] / "src" / "dd_simulator" / "ui" / "themes"

TWO_ENEMIES = (
    EnemySpec("Training Goblin", 10, 10, 2, 4, distance_feet=5),
    EnemySpec("Training Wolf", 10, 10, 2, 4, distance_feet=5),
)


def build_window(tmp_path: Path) -> tuple[QApplication, MainWindow]:
    app = QApplication.instance() or QApplication([])
    theme_manager = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "preferences.json",
        default_theme_id="high_fantasy",
    )
    window = MainWindow(theme_manager.available_themes(), build_phase_three_dashboard())
    return app, window


def close(app: QApplication, window: MainWindow) -> None:
    window.close()
    window.deleteLater()
    app.processEvents()


def combat_window(tmp_path: Path):  # type: ignore[no-untyped-def]
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
    service.start_combat(enemies=TWO_ENEMIES)
    window = MainWindow(
        theme_manager.available_themes(),
        service.load_active_dashboard(),
        game_state_service=service,
    )
    return app, window, database


def test_journal_page_keeps_its_event_filter_across_a_dashboard_reload(tmp_path: Path) -> None:
    app, window = build_window(tmp_path)
    window.controller.navigate("journal")
    assert window.current_page == "journal"
    journal = window.navigation_pages["journal"]
    assert journal.quest_list.quests == window.dashboard.quest_list
    assert journal.event_log.events == window.dashboard.event_log
    journal.event_log.set_current_filter(1)

    window._reload_dashboard(window.dashboard, target_page="journal")

    rebuilt = window.navigation_pages["journal"]
    assert rebuilt is not journal
    assert rebuilt.event_log.current_filter() == 1
    rebuilt.back_requested.emit()
    assert window.current_page == "dashboard"
    window.close()
    window.deleteLater()
    app.processEvents()


def test_system_events_such_as_inventory_additions_have_a_themed_colour() -> None:
    for theme in ("high_fantasy", "modern_proof"):
        qss = (THEMES_ROOT / theme / "theme.qss").read_text(encoding="utf-8")
        assert 'QLabel[textRole="system"]' in qss, theme


def test_dashboard_exposes_the_concept_t_regions(tmp_path: Path) -> None:
    app, window = build_window(tmp_path)
    window.show()
    app.processEvents()
    for name in (
        "character_strip", "paperdoll_panel", "skill_detail_list", "inventory_card",
        "powers_card", "scene_view", "conversation_view",
    ):
        assert getattr(window, name).isVisible(), name
    for name in ("narrative_panel", "utility_panel", "player_summary_panel"):
        assert not hasattr(window, name), name
    close(app, window)


def test_free_text_turn_lands_in_the_conversation_with_its_notes(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    release = Event()

    finish = tuple(
        ProposedStateChange(
            "complete_objective", "quest_objective", f"objective-{i}",
            "completed", True, "Done",
        )
        for i in range(3)
    )

    class QuestProvider(FixedProvider):
        def resolve_action(self, *, action, context):  # type: ignore[no-untyped-def]
            assert release.wait(3)
            return super().resolve_action(action=action, context=context)

    window.action_resolver = QuestProvider(outcome(*finish))
    window.controller.navigate("dashboard")
    grid = window.scene_view.choice_grid
    grid.action_input.setText("study the road")
    grid._request_submission()
    release.set()
    assert QThreadPool.globalInstance().waitForDone(5000)
    app.processEvents()

    view = window.conversation_view
    assert any(r.role == "player" and "study the road" in r.text_label.text() for r in view.rows)
    assert any(
        r.role == "narrator" and "The merchant nods" in r.text_label.text() for r in view.rows
    )
    assert "+150 XP" in [tag.text() for notes in view.note_rows for tag in notes.tags]
    close(app, window)


def test_older_requested_prepends_earlier_messages_in_order(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    service = window.game_state_service
    for index in range(45):
        service.resolve_player_action(f"Action {index}", FixedProvider(outcome()))
    window._reload_dashboard(service.load_active_dashboard())
    view = window.conversation_view
    assert len(view.messages) == 40
    first = min(m.turn_number for m in view.messages)
    shown = list(view.messages)

    view.older_requested.emit(first)

    assert len(view.messages) > 40
    assert view.messages[-40:] == shown
    turns = [m.turn_number for m in view.messages]
    assert turns == sorted(turns) and turns[0] < first
    assert all(m.turn_number < first for m in view.messages[:-40])
    close(app, window)


def test_combat_swaps_in_the_encounter_card_and_locks_free_text(tmp_path: Path) -> None:
    app, window, database = combat_window(tmp_path)
    scene = window.scene_view
    assert scene.encounter_card is not None and not scene.encounter_card.isHidden()
    assert scene.quest_card.isHidden()
    assert len(scene.choice_grid.combat_actions) == 6
    assert not window.findChild(QLineEdit, "sceneActionInput").isEnabled()
    close(app, window)
    database.close()


def test_power_cast_uses_the_picked_second_enemy(tmp_path: Path) -> None:
    app, window, database = combat_window(tmp_path)
    commands: list = []
    window._resolve_combat_action = commands.append  # type: ignore[method-assign]
    enemies = [c.id for c in window.dashboard.combat.combatants if c.side == "enemy"]
    assert len(enemies) == 2

    window.scene_view.select_target(enemies[1])
    key = window.dashboard.abilities[0].key
    window.powers_card.action_activated.emit(key)

    assert commands[-1].target_id == enemies[1] and commands[-1].ability_key == key
    close(app, window)
    database.close()


@pytest.mark.parametrize("page", ["map", "people", "character_sheet", "settings", "journal"])
def test_back_returns_to_the_dashboard(tmp_path: Path, page: str) -> None:
    app, window = build_window(tmp_path)
    window.controller.navigate(page)
    assert window.current_page == page
    source = window.settings_panel if page == "settings" else window.navigation_pages[page]
    source.back_requested.emit()
    assert window.current_page == "dashboard"
    close(app, window)


def test_back_from_crafting_returns_to_the_character_sheet(tmp_path: Path) -> None:
    app, window = build_window(tmp_path)
    window.controller.navigate("crafting")
    assert window.current_page == "crafting"
    window.findChild(QPushButton, "craftingBackButton").click()
    assert window.current_page == "character_sheet"
    close(app, window)


def _persisting_window(tmp_path: Path) -> MainWindow:
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "preferences.json"
    manager = ThemeManager(
        themes_root=THEMES_ROOT, preferences_path=path, default_theme_id="high_fantasy"
    )
    window = MainWindow(
        manager.available_themes(),
        build_phase_three_dashboard(),
        preferences_store=UiPreferencesStore(path),
        config_dir=tmp_path,
    )
    window.resize(1600, 900)
    window.show()
    app.processEvents()
    return window


def test_concept_splitter_sizes_persist_across_windows(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = _persisting_window(tmp_path)
    current = window.concept_splitter.sizes()
    window.concept_splitter.setSizes([current[0] + 60, current[1] - 60])
    expected = window.concept_splitter.sizes()
    assert expected != current
    window.save_ui_preferences()
    close(app, window)

    restored = _persisting_window(tmp_path)
    for got, want in zip(restored.concept_splitter.sizes(), expected, strict=True):
        assert abs(got - want) <= 4
    close(app, restored)
