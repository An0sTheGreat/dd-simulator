from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QRect, QThreadPool, Qt
from PySide6.QtWidgets import (
    QSplitter,
    QAbstractScrollArea,
    QApplication,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyle,
    QStyleOptionButton,
    QWidget,
)

from dd_simulator.app import build_application
from dd_simulator.state import (
    GameStateError,
    GameStateDatabase,
    GameStateService,
    ItemAction,
    ItemCommand,
    ProposedStateChange,
)
from dd_simulator.state.combat import CombatService, EnemySpec
from dd_simulator.ui.main_window import MainWindow
from dd_simulator.ui.widgets.quest_list import QuestListItem
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


@pytest.mark.parametrize("failure", ["error", "no_campaign"])
def test_scrolling_to_the_top_again_retries_a_failed_older_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    service = window.game_state_service
    for index in range(45):
        service.resolve_player_action(f"Action {index}", FixedProvider(outcome()))
    window._reload_dashboard(service.load_active_dashboard())
    window.resize(1280, 720)
    window.show()
    app.processEvents()
    view = window.conversation_view
    bar = view.verticalScrollBar()
    assert bar.maximum() > bar.minimum() and view.has_older
    requests: list[int] = []
    view.older_requested.connect(requests.append)

    def fail(*_args):  # type: ignore[no-untyped-def]
        raise GameStateError("ledger busy")

    if failure == "error":
        monkeypatch.setattr(service, "older_messages", fail)
    else:
        monkeypatch.setattr(service.campaigns, "active_campaign_id", lambda: None)
    bar.setValue(bar.maximum())
    bar.setValue(bar.minimum())
    assert len(requests) == 1 and len(view.messages) == 40
    monkeypatch.undo()

    bar.setValue(bar.maximum())
    bar.setValue(bar.minimum())
    assert len(requests) == 2
    assert len(view.messages) > 40
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


PAGE_ACTIONS = {
    "map": ("navigationBackButton",),
    "people": ("navigationBackButton",),
    "character_sheet": ("characterSheetCraftingButton", "navigationBackButton"),
    "journal": ("navigationBackButton",),
    "settings": ("settingsBackButton",),
    "crafting": ("craftingBackButton",),
}


def test_page_action_buttons_sit_compact_in_one_top_row(tmp_path: Path) -> None:
    app, window = build_window(tmp_path)
    window.resize(1600, 900)
    window.show()
    for page, names in PAGE_ACTIONS.items():
        window.controller.navigate(page)
        app.processEvents()
        host = window.content_stack.currentWidget()
        buttons = [host.findChild(QPushButton, name) for name in names]
        assert all(button is not None and button.isVisible() for button in buttons), page
        tops = {button.mapTo(host, QPoint(0, 0)).y() for button in buttons}
        assert len(tops) == 1, (page, tops)
        assert max(tops) + buttons[0].height() <= host.height() * 0.2, (page, tops)
        # Sized to the text, never stretched: about 220 px with Segoe UI, but the offscreen
        # fallback font draws text about twice as wide, so allow text width plus padding.
        for button in buttons:
            limit = max(220, button.fontMetrics().horizontalAdvance(button.text()) + 48)
            assert button.width() <= limit, (page, button.objectName(), button.width())
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


def _left_share(window: MainWindow) -> float:
    left, right = window.concept_splitter.sizes()
    return left / (left + right)


def _assert_even(window: MainWindow, where: object = "") -> None:
    left, right = window.concept_splitter.sizes()
    assert abs(left - right) <= 4, (where, left, right)


def _drag_split(window: MainWindow, offset: int) -> None:
    """A user drag: moveSplitter emits splitterMoved, as the handle does."""

    splitter = window.concept_splitter
    splitter.moveSplitter(splitter.sizes()[0] + offset, 1)
    QApplication.processEvents()


def _themed_window(config_dir: Path, size: tuple[int, int]):  # type: ignore[no-untyped-def]
    # The shipped app always applies a theme; unthemed, the platform style's wider
    # widgets push the codex minimum past half of 1280 px.
    app, window, _manager = build_application([], config_dir=config_dir)
    window.resize(*size)
    window.show()
    window.controller.navigate("dashboard")
    app.processEvents()
    return app, window


def test_concept_columns_split_evenly_by_default_at_any_window_size(tmp_path: Path) -> None:
    for size in ((1600, 900), (1280, 720)):
        app, window = _themed_window(tmp_path / f"{size[0]}", size)
        _assert_even(window, size)
        close(app, window)


def test_untouched_concept_split_stays_even_when_the_window_resizes(tmp_path: Path) -> None:
    app, window = _themed_window(tmp_path, (1600, 900))
    for size in ((1280, 720), (1920, 1080), (1600, 900)):
        window.resize(*size)
        app.processEvents()
        _assert_even(window, size)
    window.showMaximized()
    app.processEvents()
    _assert_even(window, "maximized")
    # Nothing the user chose, so nothing is saved for the split.
    window.save_ui_preferences()
    saved = json.loads((tmp_path / "preferences.json").read_text(encoding="utf-8"))
    assert set(saved["ui"]["splitters"]) == {"people_row"}
    close(app, window)


def test_a_dragged_concept_split_keeps_its_ratio_and_persists_across_windows(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = _persisting_window(tmp_path)
    _drag_split(window, 160)
    share = _left_share(window)
    assert share > 0.55
    window.resize(1920, 1080)
    app.processEvents()
    assert abs(_left_share(window) - share) < 0.01  # a resize keeps the user's ratio
    window._reload_dashboard(window.dashboard)
    app.processEvents()
    assert abs(_left_share(window) - share) < 0.01  # so does a dashboard rebuild
    window.save_ui_preferences()
    saved = json.loads((tmp_path / "preferences.json").read_text(encoding="utf-8"))
    assert abs(saved["ui"]["splitters"]["concept_t_ratio"] - share) < 0.01
    close(app, window)

    restored = _persisting_window(tmp_path)
    assert abs(_left_share(restored) - share) < 0.01
    close(app, restored)


def test_full_size_dashboard_shows_68_px_bag_slots_beside_unclipped_abilities(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.resize(1920, 1080)
    window.show()
    window.controller.navigate("dashboard")
    app.processEvents()
    card, powers = window.inventory_card, window.powers_card
    assert card.grid.slot_size == 68
    slot = next(slot for slot in card.grid.slots if not slot.item.is_empty)
    assert slot.width() == slot.height() == 68
    inner = slot.contentsRect()
    assert abs(slot.icon_label.width() - min(inner.width(), inner.height()) * 7 // 8) <= 1
    codex = window.concept_splitter.widget(0)
    powers_rect = QRect(powers.mapTo(codex, QPoint(0, 0)), powers.size())
    assert codex.rect().contains(powers_rect)
    assert powers.width() >= powers.minimumSizeHint().width()
    close(app, window)


def test_old_saved_concept_sizes_are_ignored_for_the_even_default(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    # Older builds wrote these pixel sizes on every save, chosen by the user or not.
    (tmp_path / "preferences.json").write_text(
        json.dumps({"ui": {"splitters": {"concept_t": [724, 857], "people": [300, 400]}}}),
        encoding="utf-8",
    )
    window = _persisting_window(tmp_path)
    _assert_even(window)
    # The old vertical People sizes ([trade, conversation]) must not land on the row split.
    window.controller.navigate("people")
    app.processEvents()
    conversation, trade = window.findChild(QSplitter, "peopleTradeConversationSplitter").sizes()
    assert conversation > trade
    close(app, window)


def test_reset_ui_defaults_returns_the_concept_split_to_even(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = _persisting_window(tmp_path)
    _drag_split(window, 160)
    window.save_ui_preferences()
    window._reset_ui_preferences()
    app.processEvents()
    _assert_even(window)
    window.resize(1920, 1080)
    app.processEvents()
    _assert_even(window, "after reset and resize")
    window.save_ui_preferences()
    saved = json.loads((tmp_path / "preferences.json").read_text(encoding="utf-8"))
    assert "concept_t_ratio" not in saved["ui"]["splitters"]
    close(app, window)


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


@pytest.fixture
def large_font_window(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Dashboard at 1280x720 and 150% font; the app font is reset even when the test fails."""

    app, window, _manager = build_application([], config_dir=tmp_path)
    try:
        window.font_size_requested.emit(150)
        window.resize(1280, 720)
        window.show()
        window.controller.navigate("dashboard")
        for _ in range(3):
            app.processEvents()
        yield app, window
    finally:
        window.font_size_requested.emit(100)
        close(app, window)


def test_dashboard_fits_1280x720_at_150_percent_font(large_font_window) -> None:
    app, window = large_font_window

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
    assert window.inventory_card.scroll.height() < 5 * 68
    assert window.conversation_view.height() >= CONVERSATION_MIN_HEIGHT
    assert rect(scene.card_scroll, scene).bottom() < rect(window.conversation_view, scene).top()
    assert rect(window.conversation_view, scene).bottom() < rect(scene.choice_grid, scene).top()


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


def test_no_dashboard_text_is_cut_off_at_1280x720_and_150_percent(large_font_window) -> None:
    app, window = large_font_window
    assert _clipped_texts(window) == []
    # The long tab label is elided, not dropped: its full name stays in the tooltip.
    tab = window.scene_view.tabs.buttons["character_sheet"]
    assert tab.text() != tab.full_text and "Character Sheet" in tab.toolTip()
    # Every tab keeps its first letters: short labels such as MAP are not squeezed to "…".
    for button in window.scene_view.tabs.buttons.values():
        assert button.text() == button.full_text or len(button.text().rstrip("…")) >= 3, button.full_text
    assert window.scene_view.tabs.buttons["map"].text() == "MAP"
    assert len(window.scene_view.tabs.clock_label.text().rstrip("…")) >= 3  # the clock row shares the room


def test_elided_text_keeps_its_full_text_as_the_accessible_name(large_font_window) -> None:
    app, window = large_font_window
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


def test_character_sheet_and_map_use_the_shared_page_card(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.show()
    app.processEvents()
    sheet = window.navigation_pages["character_sheet"]
    sheet_cards = [frame for frame in sheet.findChildren(QFrame) if frame.property("pageCard")]
    assert {card.accessibleName() for card in sheet_cards} >= {
        "Identity", "Ability Scores", "Combat Summary", "Skills", "Equipment",
        "Possessions & Currency",
    }
    # Abilities & Spells is a section inside the Skills card, not a card of its own.
    assert sheet.findChild(QWidget, "characterSheetPowers").accessibleName() == "Abilities & Spells"
    map_cards = {
        frame.objectName()
        for frame in window.navigation_pages["map"].findChildren(QFrame)
        if frame.property("pageCard")
    }
    assert {"worldMapCanvas", "travelDetailsPanel", "mapCampCard"} <= map_cards
    assert all(card.property("codexCard") for card in sheet_cards)
    close(app, window)


def test_crafting_recipes_are_page_cards_with_back_on_the_title_row(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.resize(1600, 900)
    window.show()
    window.controller.navigate("crafting")
    app.processEvents()
    page = window.content_stack.currentWidget()
    cards = [card for card in page.findChildren(QFrame, "craftingRecipeCard") if card.property("pageCard")]
    assert len(cards) == len(window.dashboard.crafting_recipes) > 0
    assert all(card.property("codexCard") for card in cards)
    title = page.findChild(QLabel, "navigationPageTitle")
    back = page.findChild(QPushButton, "craftingBackButton")
    assert title.text() == "CRAFTING RECIPES"
    # Back shares the title row and the Return buttons' secondary role.
    title_middle = title.mapTo(page, QPoint(0, title.height() // 2)).y()
    back_top = back.mapTo(page, QPoint(0, 0)).y()
    assert back_top <= title_middle <= back_top + back.height() + title.height()
    assert back.property("buttonRole") == "secondary"
    close(app, window)


def test_journal_and_settings_sections_are_page_cards(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.resize(1600, 900)
    window.show()
    journal = window.navigation_pages["journal"]
    sections = [journal.quest_panel, journal.event_log, journal.recent_events]
    settings_cards = window.settings_panel.findChildren(QFrame)
    sections += [card for card in settings_cards if card.property("pageCard")]
    sections.append(window.campaign_browser)
    assert len(sections) == 3 + 4 + 1
    assert all(card.property("pageCard") and card.property("codexCard") for card in sections)
    window.controller.navigate("settings")
    app.processEvents()
    page = window.content_stack.currentWidget()
    # Settings has a page title row like the other pages, with Back on it.
    assert page.findChild(QLabel, "navigationPageTitle").text() == "SETTINGS"
    assert page.findChild(QPushButton, "settingsBackButton") is window.settings_panel.back_button
    close(app, window)


def test_people_sections_are_page_cards(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.resize(1600, 900)
    window.show()
    window.controller.navigate("people")
    app.processEvents()
    page = window.navigation_pages["people"]
    names = (
        "npcSelectorCard", "npcIdentityCard", "npcConversationCard",
        "merchantTradePanel", "npcBottomControls",
    )
    sections = [page.findChild(QFrame, name) for name in names]
    assert all(card is not None and card.property("pageCard") and card.property("codexCard") for card in sections)
    # The NPC exchange uses the Adventure conversation's thread; replies keep their heading.
    assert page.thread.objectName() == "conversationView"
    assert page.action_host.findChild(QLabel, "codexCardHeading").text() == "YOUR REPLY"
    close(app, window)


def test_people_page_runs_conversation_trade_then_people_column(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.resize(1600, 900)
    window.show()
    window.controller.navigate("people")
    app.processEvents()
    page = window.navigation_pages["people"]

    def rect(card):  # type: ignore[no-untyped-def]
        return card.geometry().translated(card.parentWidget().mapTo(page, card.geometry().topLeft()) - card.geometry().topLeft())

    trade_card = page.findChild(QFrame, "merchantTradePanel")
    assert trade_card is not None
    people, identity, conversation, trade = (
        rect(page.selector_card), rect(page.identity_card), rect(page.conversation_card),
        rect(trade_card),
    )
    # Left to right: Conversation, Trade, then People above Speaking with.
    assert conversation.right() < trade.left() < trade.right() < people.left()
    assert abs(people.left() - identity.left()) <= 1
    assert people.top() > identity.bottom()  # Speaking with sits above People
    assert people.height() > identity.height()  # People takes the spare height
    # The row's full height: Trade and the column run from the Conversation's top to the bottom.
    assert conversation.top() == trade.top() == identity.top()
    assert abs(trade.bottom() - people.bottom()) <= 1
    # HEAD 83240e2 gave the Conversation 291 px at a 14 px line (about 21 lines); now about 1.8x.
    assert conversation.height() >= 36 * page.fontMetrics().height()
    close(app, window)


def test_people_replies_and_trade_fit_at_small_window(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.resize(1280, 720)
    window.show()
    window.controller.navigate("people")
    for _ in range(3):
        app.processEvents()
    page = window.navigation_pages["people"]
    replies = page.findChildren(QPushButton, "npcSuggestedResponse")
    assert len(replies) == 6
    for button in replies:
        option = QStyleOptionButton()
        button.initStyleOption(option)
        room = button.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, button)
        metrics = button.fontMetrics()
        fits_one_line = metrics.horizontalAdvance(button.text()) <= room.width()
        # Or it wraps: every word fits the width and the button is tall enough for its lines.
        wraps = (
            button.hasHeightForWidth()
            and button.height() >= button.heightForWidth(button.width())
            and all(metrics.horizontalAdvance(word) <= room.width() for word in button.text().split())
        )
        assert fits_one_line or wraps, button.text()
    scroll = page.findChild(QAbstractScrollArea, "merchantTradeScroll")
    assert scroll is not None and not scroll.horizontalScrollBar().isVisible()
    # Stock and sell rows keep their item text on one line.
    entries = [label for label in scroll.widget().findChildren(QLabel) if label.wordWrap() and label.text()]
    assert entries
    for label in entries:
        assert label.fontMetrics().horizontalAdvance(label.text()) <= label.contentsRect().width(), label.text()
    close(app, window)


def test_character_sheet_story_cards_put_each_label_beside_its_value(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.resize(1600, 900)
    window.show()
    window.controller.navigate("character_sheet")
    app.processEvents()
    sheet = window.navigation_pages["character_sheet"]
    for title in ("Appearance & Biography", "Role & Character"):
        card = next(frame for frame in sheet.findChildren(QFrame) if frame.accessibleName() == title)
        labels = card.findChildren(QLabel, "pageCardLabel")
        values = card.findChildren(QLabel, "pageCardValue")
        assert labels and len(labels) == len(values)
        for label, value in zip(labels, values):
            assert label.mapTo(card, QPoint(0, 0)).y() == value.mapTo(card, QPoint(0, 0)).y(), title
            assert label.mapTo(card, QPoint(0, 0)).x() < value.mapTo(card, QPoint(0, 0)).x(), title
    close(app, window)


@pytest.mark.parametrize("size", [(1280, 720), (1600, 900)])
def test_character_sheet_combat_summary_values_keep_apart(tmp_path: Path, size) -> None:  # type: ignore[no-untyped-def]
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.resize(*size)
    window.show()
    window.controller.navigate("character_sheet")
    for _ in range(3):
        app.processEvents()
    page = window.navigation_pages["character_sheet"]
    values = page.findChildren(QLabel, "characterSheetVitalValue")
    assert len(values) == 5
    rects = [label.geometry().translated(label.parentWidget().mapTo(page, QPoint(0, 0))) for label in values]
    for index, (label, rect) in enumerate(zip(values, rects)):
        text_width = label.fontMetrics().horizontalAdvance(label.text())
        assert text_width <= rect.width(), label.text()
        for other, neighbour in zip(values[index + 1:], rects[index + 1:]):
            # Values on one line need a readable gutter, not 2 px ("42 / 4215 +2").
            assert not rect.adjusted(-4, 0, 4, 0).intersects(neighbour), (label.text(), other.text())
    close(app, window)


@pytest.mark.parametrize("theme", ["high_fantasy", "modern_proof"])
def test_journal_entries_start_at_the_top_and_quest_counts_sit_beside_the_bar(
    tmp_path: Path, theme: str
) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.theme_requested.emit(theme)
    window.resize(1600, 900)
    window.show()
    window.controller.navigate("journal")
    for _ in range(3):
        app.processEvents()
    journal = window.navigation_pages["journal"]
    for panel, name in ((journal.event_log, "eventLogEntry"), (journal.recent_events, "recentEventEntry")):
        viewport = panel.scroll_area.viewport()
        entries = [w for w in panel.findChildren(QLabel, name) if w.isVisible()]
        assert entries, name
        tops = sorted(w.mapTo(viewport, QPoint(0, 0)).y() for w in entries)
        assert tops[-1] + entries[0].height() <= viewport.height()  # short list: no scrolling
        assert tops[0] < 30, (name, tops[0], viewport.height())  # not bottom-anchored
    cards = [c for c in journal.quest_list.findChildren(QuestListItem) if not c.completed]
    assert cards
    for card in cards:
        bar = card.findChild(QWidget, "questProgress")
        label = card.progress_label
        quest = card.quest
        assert not bar.isTextVisible()
        assert label.isVisible() and label.text().endswith(f"{quest.progress_current} / {quest.progress_maximum}")
        assert label.fontMetrics().horizontalAdvance(label.text()) <= label.contentsRect().width()
        assert not label.geometry().intersects(bar.geometry()), label.text()
    close(app, window)


def test_equipping_keeps_the_paperdoll_widget_and_size(tmp_path: Path) -> None:
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.resize(1600, 900)
    window.show()
    app.processEvents()
    window.codex_column.fit()
    panel, size = window.paperdoll_panel, window.paperdoll_panel.size()
    service = window.game_state_service
    service.execute_item_command(ItemCommand(ItemAction.UNEQUIP, 0))
    bag = service.load_active_dashboard().inventory_preview
    window._refresh_item_views(service.load_active_dashboard())
    source = next(i for i, item in enumerate(bag) if item.name and item.compatible_slots)
    window._equip_inventory_to_equipment(source, 0)
    app.processEvents()
    assert window.paperdoll_panel is panel and panel.size() == size
    assert window.updatesEnabled()
    window.close()
    window.deleteLater()
    app.processEvents()


def test_reloads_open_no_stray_windows_and_combat_turns_echo_without_greying(tmp_path: Path) -> None:
    from PySide6.QtCore import QEvent, QObject

    from dd_simulator.state import CombatAction, CombatCommand

    app, window, _manager = build_application([], config_dir=tmp_path)
    window.resize(1600, 900)
    window.show()
    app.processEvents()
    shown: list[str] = []

    class Spy(QObject):
        def eventFilter(self, obj, event):  # type: ignore[no-untyped-def]
            if event.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow() and obj is not window:
                shown.append(obj.objectName() or type(obj).__name__)
            return False

    spy = Spy()
    app.installEventFilter(spy)
    try:
        service = window.game_state_service
        window._reload_dashboard(service.load_active_dashboard())
        assert shown == []  # quest progress labels used to flash up as tiny windows
        service.start_combat()
        window._reload_dashboard(service.load_active_dashboard())
        enemy = next(c for c in window.dashboard.combat.combatants if c.side == "enemy")
        from dd_simulator.ui import main_window as mw

        before = [button.isEnabled() for button in window.scene_view.choice_grid.choice_buttons]
        started: list[object] = []
        original = mw.QThreadPool.globalInstance
        mw.QThreadPool.globalInstance = lambda: type("P", (), {"start": lambda self, task: started.append(task)})()
        try:
            window._resolve_combat_action(CombatCommand(CombatAction.ATTACK, target_id=enemy.id))
        finally:
            mw.QThreadPool.globalInstance = original
        assert started and window.powers_card.isEnabled()
        assert [b.isEnabled() for b in window.scene_view.choice_grid.choice_buttons] == before
        pending = window.conversation_view.pending_row
        assert pending is not None and pending.text_label.text().startswith("Attack ")
    finally:
        app.removeEventFilter(spy)
        window._combat_task = None
        window.close()
        window.deleteLater()
        app.processEvents()


def test_turn_refresh_updates_in_place_and_rebuilds_hidden_pages_on_open(tmp_path: Path) -> None:
    import time

    from dd_simulator.state import CombatAction, CombatCommand

    app, window, _manager = build_application([], config_dir=tmp_path)
    window.resize(1600, 900)
    window.show()
    window._show_navigation("dashboard")
    app.processEvents()
    service = window.game_state_service
    service.start_combat()
    window._refresh_turn_views(service.load_active_dashboard())
    stack, splitter, scene = window.content_stack, window.concept_splitter, window.scene_view
    journal = window.navigation_pages["journal"]
    service.execute_combat_command(CombatCommand(CombatAction.PREPARE, preparation="scout"))
    started = time.perf_counter()
    window._refresh_turn_views(service.load_active_dashboard())
    elapsed = time.perf_counter() - started
    assert window.content_stack is stack and window.concept_splitter is splitter and window.scene_view is scene
    assert window.conversation_view.messages[-1].turn_number == window.dashboard.narrative.messages[-1].turn_number
    assert "journal" in window._stale_pages and window.navigation_pages["journal"] is journal
    window._show_navigation("journal")
    assert window.navigation_pages["journal"] is not journal and "journal" not in window._stale_pages
    assert window.content_stack.currentWidget() is window.navigation_pages["journal"]
    assert elapsed < 0.5, elapsed  # a full reload took ~1 s
    window.close()
    window.deleteLater()
    app.processEvents()
