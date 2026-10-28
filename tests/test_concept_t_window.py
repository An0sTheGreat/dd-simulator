from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from dd_simulator.ui.main_window import MainWindow
from dd_simulator.ui.services.mock_data import build_phase_three_dashboard
from dd_simulator.ui.themes.theme_manager import ThemeManager


THEMES_ROOT = Path(__file__).parents[1] / "src" / "dd_simulator" / "ui" / "themes"


def build_window(tmp_path: Path) -> tuple[QApplication, MainWindow]:
    app = QApplication.instance() or QApplication([])
    theme_manager = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "preferences.json",
        default_theme_id="high_fantasy",
    )
    window = MainWindow(theme_manager.available_themes(), build_phase_three_dashboard())
    return app, window


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
