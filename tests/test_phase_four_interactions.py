from __future__ import annotations

import json
from dataclasses import replace
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from dd_simulator.ui.controllers.ui_controller import UiController
from dd_simulator.ui.main_window import MainWindow
from dd_simulator.ui.models.presentation import (
    NarrativeMessageView,
    NarrativeSegmentView,
    NarrativeView,
)
from dd_simulator.ui.panels.narrative_panels import NarrativePanel, ResponseOptionButton
from dd_simulator.ui.services.mock_data import build_phase_three_dashboard
from dd_simulator.ui.services.ui_preferences import UiPreferencesStore
from dd_simulator.ui.themes.theme_manager import ThemeManager


THEMES_ROOT = Path(__file__).parents[1] / "src" / "dd_simulator" / "ui" / "themes"


def build_window(
    tmp_path: Path, dashboard=None
) -> tuple[QApplication, MainWindow, Path]:
    app = QApplication.instance() or QApplication([])
    preferences_path = tmp_path / "preferences.json"
    manager = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=preferences_path,
        default_theme_id="high_fantasy",
    )
    window = MainWindow(
        manager.available_themes(),
        dashboard or build_phase_three_dashboard(),
        preferences_store=UiPreferencesStore(preferences_path),
    )
    return app, window, preferences_path


def close_window(app: QApplication, window: MainWindow) -> None:
    window.close()
    window.deleteLater()
    app.processEvents()


def test_controller_validates_and_normalizes_player_actions() -> None:
    controller = UiController()
    accepted = QSignalSpy(controller.action_submitted)
    rejected = QSignalSpy(controller.validation_failed)

    controller.submit_player_action("   search   the   altar ")
    controller.submit_player_action("   ")
    controller.submit_player_action("x" * 2001)

    assert accepted.count() == 1
    assert accepted.at(0)[0] == "search the altar"
    assert rejected.count() == 2


def test_narrative_panel_displays_player_and_typed_response_with_six_choices() -> None:
    app = QApplication.instance() or QApplication([])
    panel = NarrativePanel(
        NarrativeView(
            title="Crossroads",
            paragraphs=(),
            dialogue="",
            prompt="What next?",
            suggested_actions=tuple(f"Choice {index}" for index in range(1, 7)),
            player_action="I greet the traveler",
            response_segments=(
                NarrativeSegmentView("narrative", "Rain falls across the road."),
                NarrativeSegmentView("monologue", "Something feels wrong."),
                NarrativeSegmentView("spoken", "Welcome, traveler."),
            ),
        )
    )

    assert panel.findChild(object, "playerActionHistory").text() == (
        "You: I greet the traveler"
    )
    assert panel.findChild(object, "narrativeMessage0").property("textRole") == "narrative"
    assert panel.findChild(object, "monologueMessage1").property("textRole") == "monologue"
    assert panel.findChild(object, "spokenMessage2").property("textRole") == "spoken"
    choices = panel.findChildren(object, "suggestedActionButton")
    assert len(choices) == 6
    assert all(choice.minimumHeight() == 28 for choice in choices)
    choices[3].click()
    assert panel.action_input.text() == "Choice 4"

    panel.deleteLater()
    app.processEvents()


def test_clipped_response_option_shows_complete_persistent_hover_card() -> None:
    app = QApplication.instance() or QApplication([])
    long_response = (
        "Study the merchant's unusual dagger closely for hidden markings, "
        "craftsmanship details, and any magical flaws."
    )
    panel = NarrativePanel(
        NarrativeView(
            title="Crossroads",
            paragraphs=("A merchant waits beside the road.",),
            dialogue="",
            prompt="What next?",
            suggested_actions=(long_response, "Wait", "Leave"),
        )
    )
    panel.resize(480, 300)
    panel.show()
    app.processEvents()
    long_button, short_button = panel.suggestion_buttons[:2]
    long_button.setFixedWidth(220)
    short_button.setFixedWidth(220)

    assert isinstance(long_button, ResponseOptionButton)
    assert long_button.is_text_clipped()
    assert not short_button.is_text_clipped()
    enter = QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
    long_button.enterEvent(enter)
    app.processEvents()
    assert long_button.hover_card.isVisible()
    assert long_button.hover_card.message_label.text() == long_response
    assert 0 < long_button.hover_card.width() <= 640
    screen = QApplication.primaryScreen()
    assert screen is not None
    assert screen.availableGeometry().contains(long_button.hover_card.geometry())

    long_button.click()
    app.processEvents()
    assert long_button.hover_card is None
    short_button.enterEvent(enter)
    app.processEvents()
    assert short_button.hover_card is None

    panel.close()
    panel.deleteLater()
    app.processEvents()


def test_narrative_panel_scrolls_latest_twenty_messages_to_bottom() -> None:
    app = QApplication.instance() or QApplication([])
    messages = tuple(
        NarrativeMessageView(
            "player" if index % 2 == 0 else "narrative",
            f"Message {index}",
        )
        for index in range(20)
    )
    panel = NarrativePanel(
        NarrativeView(
            title="History",
            paragraphs=(),
            dialogue="",
            prompt="What next?",
            suggested_actions=tuple(f"Choice {index}" for index in range(6)),
            messages=messages,
        )
    )
    panel.resize(500, 260)
    panel.show()
    app.processEvents()
    QTest.qWait(1)
    app.processEvents()

    bar = panel.history_scroll.verticalScrollBar()
    assert bar.maximum() > 0
    assert bar.value() == bar.maximum()
    rendered = panel.findChildren(object, "playerActionHistory")
    assert rendered[-1].text() == "You: Message 18"
    assert panel.findChild(object, "narrativeMessage19").text() == "Message 19"

    panel.close()
    panel.deleteLater()
    app.processEvents()


def test_navigation_and_tabs_switch_real_content(tmp_path: Path) -> None:
    app, window, _ = build_window(tmp_path)

    # The bottom navigation bar (and its placeholders) is gone; the scene tabs navigate.
    assert not hasattr(window, "navigation_buttons")
    assert window.findChildren(object, "navigationPlaceholderButton") == []
    assert not {"profile", "inventory", "skills", "quests"} & set(
        window.page_indices
    )
    assert {"map", "people", "character_sheet", "settings", "crafting"} <= set(
        window.page_indices
    )
    window.resize(1600, 900)
    window.show()
    tabs = window.scene_view.tabs.buttons

    tabs["map"].click()
    app.processEvents()
    assert window.current_page == "map"
    assert window.content_stack.currentIndex() == window.page_indices["map"]

    window.controller.navigate("people")
    app.processEvents()
    assert window.current_page == "people"
    assert window.content_stack.currentIndex() == window.page_indices["people"]

    # The retired utility tabs, quest panel and event panel are gone from the window.
    for retired in ("utility_panel", "quest_panel", "event_panel", "narrative_panel"):
        assert not hasattr(window, retired), retired

    close_window(app, window)


def test_header_theme_selection_synchronizes_settings(tmp_path: Path) -> None:
    app, window, _ = build_window(tmp_path)

    modern_index = window.theme_selector.findData("modern_proof")
    window.theme_selector.setCurrentIndex(modern_index)
    window.select_theme("modern_proof")

    assert window.settings_panel.theme_selector.currentData() == "modern_proof"
    close_window(app, window)


def test_inventory_selection_keyboard_and_context_actions(tmp_path: Path) -> None:
    # InventoryCard slot indices are real bag positions, so give the bag occupied positions.
    mock = build_phase_three_dashboard()
    occupied = tuple(item for item in mock.inventory_preview if not item.is_empty)
    app, window, _ = build_window(tmp_path, replace(mock, inventory=occupied))
    card = window.inventory_card
    grid = card.grid
    selected = QSignalSpy(card.selection_changed)
    requested = QSignalSpy(card.context_action_requested)

    grid.select_index(1)
    assert selected.count() == 1
    assert bool(grid.slots[1].property("selected"))

    window.show()
    grid.slots[1].setFocus()
    QTest.keyClick(grid.slots[1], Qt.Key.Key_Right)
    app.processEvents()
    assert grid.slots[2].hasFocus()

    menu = grid.slots[1].build_context_menu()
    assert [action.text() for action in menu.actions()] == [
        "Inspect", "Use", "Equip", "Drop"
    ]
    menu.actions()[0].trigger()
    assert requested.count() == 1
    assert requested.at(0) == [1, "inspect"]

    close_window(app, window)


def test_player_action_requires_configured_ai_and_preserves_input(tmp_path: Path) -> None:
    app, window, _ = build_window(tmp_path)
    panel = window.scene_view.choice_grid

    panel.action_input.setText("  Look   beneath the bridge ")
    QTest.keyClick(panel.action_input, Qt.Key.Key_Return)
    assert panel.action_input.text() == "  Look   beneath the bridge "
    assert panel.feedback.text() == "Action resolution is unavailable."
    assert panel.feedback.property("feedbackState") == "error"

    close_window(app, window)


def test_action_resolution_feedback_preserves_input_for_retry(tmp_path: Path) -> None:
    app, window, _ = build_window(tmp_path)
    panel = window.scene_view.choice_grid
    retried = QSignalSpy(panel.retry_requested)

    panel.show_resolution_pending("inspect the sealed door")
    assert panel.action_input.text() == "inspect the sealed door"
    assert not panel.action_input.isEnabled()
    assert panel.cancel_button.isVisibleTo(panel)

    panel.show_resolution_error("The local model returned an invalid turn.")
    assert panel.action_input.text() == "inspect the sealed door"
    assert panel.action_input.isEnabled()
    assert panel.retry_button.isVisibleTo(panel)
    panel.retry_button.click()
    assert retried.at(0) == ["inspect the sealed door"]

    panel.show_resolution_pending("inspect the sealed door")
    panel.show_resolution_cancelled()
    assert panel.action_input.text() == "inspect the sealed door"
    assert "no state was changed" in panel.feedback.text()
    close_window(app, window)


def test_ui_preferences_round_trip_and_reset(tmp_path: Path) -> None:
    app, window, preferences_path = build_window(tmp_path)
    window.resize(1600, 900)
    window.show()
    current = window.concept_splitter.sizes()
    window.concept_splitter.setSizes([current[0] + 60, current[1] - 60])
    expected_split = window.concept_splitter.sizes()
    window.controller.navigate("map")
    window.settings_panel.select_font_size(125)
    window.settings_panel.font_size_requested.emit(125)
    window.save_ui_preferences()

    saved = json.loads(preferences_path.read_text(encoding="utf-8"))
    assert saved["ui"]["page"] == "map"
    assert saved["ui"]["font_size"] == 125
    assert saved["ui"]["splitters"]["concept_t"] == expected_split
    # The retired tab/filter and splitter keys are no longer written.
    assert not {"utility_tab", "quest_tab"} & set(saved["ui"])
    assert set(saved["ui"]["splitters"]) == {"concept_t", "people"}
    close_window(app, window)

    # Old keys left in an existing preferences file are ignored on load.
    saved["ui"].update({"utility_tab": 2, "quest_tab": 1})
    saved["ui"]["splitters"].update(
        {"rows": [610, 190], "summary": [300, 500], "narrative": [400, 400]}
    )
    preferences_path.write_text(json.dumps(saved), encoding="utf-8")

    app, restored, _ = build_window(tmp_path)
    restored.resize(1600, 900)
    restored.show()
    assert restored.current_page == "map"
    assert restored.font_size_preference == 125
    assert restored.settings_panel.font_size_value.text() == "125%"
    restored_split = restored.concept_splitter.sizes()
    assert abs(restored_split[0] / sum(restored_split) - expected_split[0] / sum(expected_split)) < 0.02

    restored._reset_ui_preferences()
    assert restored.current_page == "dashboard"
    assert restored.font_size_preference == 100
    assert "ui" not in json.loads(preferences_path.read_text(encoding="utf-8"))
    close_window(app, restored)


def test_legacy_removed_navigation_preference_returns_to_dashboard(tmp_path: Path) -> None:
    app, window, preferences_path = build_window(tmp_path)
    close_window(app, window)
    preferences_path.write_text(
        json.dumps({"ui": {"page": "inventory"}}),
        encoding="utf-8",
    )

    app, restored, _ = build_window(tmp_path)
    assert restored.current_page == "dashboard"
    assert restored.content_stack.currentIndex() == restored.page_indices["dashboard"]
    close_window(app, restored)
