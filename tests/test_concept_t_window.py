from __future__ import annotations

import os
from pathlib import Path
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QThreadPool, Qt
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyle,
    QStyleOptionButton,
)

from dd_simulator.app import build_application
from dd_simulator.state import (
    GameStateDatabase,
    GameStateService,
    ItemAction,
    ItemCommand,
    ProposedStateChange,
)
from dd_simulator.state.combat import CombatService, EnemySpec
from dd_simulator.ui.main_window import MainWindow
from dd_simulator.ui.widgets.scene_view import CONVERSATION_MIN_HEIGHT, ElidedButton, ElidedLabel
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


def test_journal_event_filter_persists_and_resets(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = _persisting_window(tmp_path)
    window.navigation_pages["journal"].event_log.set_current_filter(2)
    window.save_ui_preferences()
    close(app, window)

    restored = _persisting_window(tmp_path)
    log = restored.navigation_pages["journal"].event_log
    assert log.current_filter() == 2
    restored._reset_ui_preferences()
    assert log.current_filter() == 0
    close(app, restored)


@pytest.mark.parametrize("action", ["sort", "equip"])
def test_item_refresh_keeps_the_paperdoll_attack_bonus(tmp_path: Path, action: str) -> None:
    app, window, database = combat_window(tmp_path)
    assert "ATK" in window.paperdoll_panel.stats_label.text()
    if action == "sort":
        window._auto_sort_inventory()
    else:
        service = window.game_state_service
        service.execute_item_command(ItemCommand(ItemAction.UNEQUIP, 7))
        bag = service.load_active_dashboard().inventory_preview
        window._equip_inventory_to_equipment(
            next(i for i, item in enumerate(bag) if item.name == "Silver Ring"), 7
        )
        assert window.dashboard.equipment[7].item_name == "Silver Ring"
    assert "ATK" in window.paperdoll_panel.stats_label.text()
    close(app, window)
    database.close()


def test_dashboard_fits_1280x720_at_150_percent_font(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.font_size_requested.emit(150)
    window.resize(1280, 720)
    window.show()
    window.controller.navigate("dashboard")
    for _ in range(3):
        app.processEvents()

    def rect(widget, ancestor):  # type: ignore[no-untyped-def]
        return widget.rect().translated(widget.mapTo(ancestor, widget.rect().topLeft()))

    # A layout whose minimum exceeds 1280x720 grows the window instead of fitting it.
    assert (window.width(), window.height()) == (1280, 720)
    codex, scene = window.concept_splitter.widget(0), window.scene_view
    for widget, column in (
        (window.character_strip, codex), (window.paperdoll_panel, codex),
        (window.skill_detail_list, codex), (window.codex_card_row, codex),
        (scene.tabs, scene), (scene.card_scroll, scene),
        (window.conversation_view, scene), (scene.choice_grid, scene),
    ):
        assert widget.width() > 0 and widget.height() > 0, widget.objectName()
        assert column.rect().contains(rect(widget, column)), widget.objectName()
    stacked = [
        rect(w, codex) for w in (window.character_strip, window.paperdoll_panel, window.codex_card_row)
    ]
    for upper, lower in zip(stacked, stacked[1:]):
        assert upper.bottom() < lower.top()
    assert rect(window.skill_detail_list, codex).bottom() < stacked[2].top()
    # Rows keep their natural height (the list scrolls) instead of being squeezed together.
    assert all(r.height() >= r.minimumSizeHint().height() for r in window.skill_detail_list.rows)
    assert window.paperdoll_panel.scale < 1.0
    assert window.inventory_card.scroll.height() < 5 * 50
    assert window.conversation_view.height() >= CONVERSATION_MIN_HEIGHT
    assert rect(scene.card_scroll, scene).bottom() < rect(window.conversation_view, scene).top()
    assert rect(window.conversation_view, scene).bottom() < rect(scene.choice_grid, scene).top()
    window.font_size_requested.emit(100)
    close(app, window)


def _clipped_texts(window: MainWindow) -> list[str]:
    """Visible single-line labels and buttons whose text overflows without an ellipsis and tooltip."""

    clipped = []
    for widget in (*window.findChildren(QLabel), *window.findChildren(QPushButton)):
        text = widget.text()
        if not widget.isVisible() or not text:
            continue
        if isinstance(widget, QLabel):
            if widget.wordWrap() or (widget.textFormat() != Qt.TextFormat.PlainText and "<" in text):
                continue
            room = widget.contentsRect().width()
        else:
            option = QStyleOptionButton()
            widget.initStyleOption(option)
            room = widget.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, widget).width()
        # A label wider than the scroll viewport it sits in is cut off by the viewport edge.
        ancestor = widget.parentWidget()
        while ancestor is not None:
            if isinstance(ancestor, QAbstractScrollArea) and ancestor.viewport().isAncestorOf(widget):
                viewport = ancestor.viewport()
                left = widget.mapTo(viewport, QPoint(0, 0)).x() + widget.contentsRect().left()
                room = min(room, viewport.width() - left)
            ancestor = ancestor.parentWidget()
        if widget.fontMetrics().horizontalAdvance(text) <= room:
            continue
        full = getattr(widget, "full_text", "")
        tips = f"{widget.toolTip()} {widget.parentWidget().toolTip()}".casefold()
        if not (full and text.endswith("…") and full.casefold() in tips):
            clipped.append(f"{widget.objectName()}: {text!r}")
    return clipped


def test_no_dashboard_text_is_cut_off_at_1280x720_and_150_percent(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.font_size_requested.emit(150)
    window.resize(1280, 720)
    window.show()
    window.controller.navigate("dashboard")
    for _ in range(3):
        app.processEvents()
    assert _clipped_texts(window) == []
    # The long tab label is elided, not dropped: its full name stays in the tooltip.
    tab = window.scene_view.tabs.buttons["character_sheet"]
    assert tab.text() != tab.full_text and "Character Sheet" in tab.toolTip()
    # Every tab keeps its first letters: short labels such as MAP are not squeezed to "…".
    for button in window.scene_view.tabs.buttons.values():
        assert button.text() == button.full_text or len(button.text().rstrip("…")) >= 3, button.full_text
    assert window.scene_view.tabs.buttons["map"].text() == "MAP"
    assert len(window.scene_view.tabs.clock_label.text().rstrip("…")) >= 3  # the clock row shares the room
    window.font_size_requested.emit(100)
    close(app, window)


def test_elided_text_keeps_its_full_text_as_the_accessible_name(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.font_size_requested.emit(150)
    window.resize(1280, 720)
    window.show()
    window.controller.navigate("dashboard")
    for _ in range(3):
        app.processEvents()
    scene = window.scene_view
    elided = [
        widget for widget in (*window.findChildren(ElidedLabel), *window.findChildren(ElidedButton))
        if widget.isVisible() and widget.text() != widget.full_text
    ]
    kinds = {widget.objectName() for widget in elided}
    assert {"sceneChip", "codexResourceName", "sceneNavTab"} <= kinds, kinds
    for widget in elided:
        name = widget.accessibleName()
        assert widget.full_text.casefold() in name.casefold() or widget.property("navigationTarget"), name
    # Tabs keep their own descriptive names ("Character Sheet tab"), never the shortened text.
    assert scene.tabs.buttons["character_sheet"].accessibleName() == "Character Sheet tab"
    scene.time_chip.set_full_text("DAY 18 · EVENING")
    assert scene.time_chip.accessibleName() == "DAY 18 · EVENING"
    window.font_size_requested.emit(100)
    close(app, window)
