from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QProgressBar, QPushButton

from dd_simulator.state import GameStateDatabase, GameStateService
from dd_simulator.ui.main_window import MainWindow
from dd_simulator.ui.themes.theme_manager import ThemeManager


THEMES_ROOT = Path(__file__).parents[1] / "src" / "dd_simulator" / "ui" / "themes"


def _window(tmp_path: Path) -> tuple[QApplication, MainWindow, ThemeManager]:
    app = QApplication.instance() or QApplication([])
    service = GameStateService(GameStateDatabase.in_memory())
    service.initialize()
    service.ensure_demo_campaign()
    themes = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "theme.json",
        default_theme_id="high_fantasy",
    )
    window = MainWindow(
        themes.available_themes(), service.load_active_dashboard(),
        game_state_service=service, start_on_campaigns=True,
    )
    window.resize(1600, 900)
    window.show()
    app.processEvents()
    return app, window, themes


def test_skill_xp_bars_use_authoritative_progress_and_theme_accent(tmp_path: Path) -> None:
    app, window, themes = _window(tmp_path)

    bars = window.skill_detail_list.findChildren(QProgressBar, "skillDetailXpBar")
    assert len(bars) == 8
    survival = next(
        bar for bar in bars if bar.accessibleName().startswith("Survival experience")
    )
    assert (survival.value(), survival.maximum(), survival.height()) == (410, 460, 3)

    # Concept T: a gold gradient in High Fantasy, the experience token in Modern Proof.
    for theme_id, fill in (
        ("high_fantasy", "stop:0 #9a7436, stop:1 #e2bd6c"),
        ("modern_proof", "background: #8ab8ff"),
    ):
        stylesheet = themes.load_theme(theme_id).stylesheet
        start = stylesheet.index("QProgressBar#skillDetailXpBar::chunk")
        assert fill in stylesheet[start:start + 180]

    window.close()
    app.processEvents()


def test_redundant_navigation_is_blank_and_campaigns_live_in_settings(tmp_path: Path) -> None:
    app, window, _themes = _window(tmp_path)

    assert window.current_page == "settings"
    tabs = window.scene_view.tabs.buttons
    assert list(tabs) == [
        "dashboard", "map", "people", "character_sheet", "settings", "journal"
    ]
    assert not {"skills", "quests", "campaigns"} & set(window.page_indices)
    # Every tab opens a page; blank placeholder buttons are gone.
    assert set(tabs) <= set(window.page_indices)
    assert not window.findChildren(QPushButton, "navigationPlaceholderButton")
    assert window.settings_page.isAncestorOf(window.campaign_browser)
    assert abs(window.settings_panel.width() - window.campaign_browser.width()) < 40

    window.campaign_browser.new_requested.emit()
    assert window.current_page == "character_creation"
    panel = window.character_creation_panel
    assert panel.preset_selector.count() == 2
    assert not panel.world_type.isHidden()
    assert not panel.campaign_description.isReadOnly()
    window.character_creation_panel.cancelled.emit()
    assert window.current_page == "settings"

    preset_item = window.campaign_browser.preset_list.item(0)
    window.campaign_browser.preset_list.itemClicked.emit(preset_item)
    assert window.current_page == "character_creation"
    assert panel.preset_selector.count() == 1
    assert panel.preset_selector.currentData() == "last_orrery_of_sol"
    assert panel.world_type.isHidden()
    assert panel.tone.isHidden()
    assert panel.region.isHidden()
    assert panel.location.isHidden()
    assert panel.content_preferences.isHidden()
    assert panel._campaign_name_row.isHidden()
    assert panel.campaign_description.isReadOnly()

    panel.cancelled.emit()
    window.campaign_browser.new_requested.emit()
    assert panel.preset_selector.count() == 2
    assert panel.preset_selector.itemData(0) == ""
    assert not panel.world_type.isHidden()
    assert not panel.campaign_description.isReadOnly()

    window.close()
    app.processEvents()
