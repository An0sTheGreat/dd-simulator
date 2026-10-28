from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from dd_simulator.lm_studio import LMStudioClient, LMStudioModelInfo
from dd_simulator.ui.main_window import MainWindow
from dd_simulator.ui.panels.settings_panel import SettingsPanel
from dd_simulator.ui.services.mock_data import build_phase_three_dashboard
from dd_simulator.ui.themes.theme_manager import ThemeManager


THEMES_ROOT = Path(__file__).parents[1] / "src" / "dd_simulator" / "ui" / "themes"


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _themes(tmp_path: Path):  # type: ignore[no-untyped-def]
    return ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "preferences.json",
        default_theme_id="high_fantasy",
    ).available_themes()


def test_client_loads_installed_model_through_native_api(monkeypatch) -> None:
    client = LMStudioClient()
    calls: list[tuple[str, str, dict[str, object] | None, float | None]] = []

    def request(  # type: ignore[no-untyped-def]
        url: str, *, method: str = "GET", payload=None, timeout_seconds=None
    ):
        calls.append((url, method, payload, timeout_seconds))
        return {"status": "loaded", "instance_id": "gemma-loaded"}

    monkeypatch.setattr(client, "_json_request_url", request)

    assert client.load_model("gemma-model") == "gemma-loaded"
    assert calls == [
        (
            "http://localhost:1234/api/v1/models/load",
            "POST",
            {"model": "gemma-model"},
            300.0,
        )
    ]


def test_unloaded_model_is_selectable_and_emits_explicit_load(tmp_path: Path) -> None:
    _app()
    panel = SettingsPanel(_themes(tmp_path))
    panel.set_models((LMStudioModelInfo("gemma-model", "Gemma", False),), None)
    load_spy = QSignalSpy(panel.model_load_requested)

    panel.model_load_button.click()

    assert panel.model_selector.currentData() == "gemma-model"
    assert panel.model_load_button.isEnabled()
    assert load_spy.count() == 1
    assert load_spy.at(0) == ["gemma-model"]


def test_settings_page_uses_left_half_and_scrolls(tmp_path: Path) -> None:
    app = _app()
    window = MainWindow(_themes(tmp_path), build_phase_three_dashboard())
    window.resize(1600, 900)
    window.controller.navigate("settings")
    window.show()
    app.processEvents()

    assert window.settings_scroll.widget() is window.settings_page
    assert abs(window.settings_panel.width() * 2 - window.settings_page.width()) < 30
    assert window.settings_scroll.verticalScrollBarPolicy().name == "ScrollBarAsNeeded"

    window.show_startup_status("Packaged distribution. Storage ready.")
    window._reload_dashboard(window.dashboard, target_page="settings")  # noqa: SLF001
    assert window.settings_panel.startup_status.text() == (
        "Packaged distribution. Storage ready."
    )
    assert not window._models_scanned  # noqa: SLF001

    window.close()
