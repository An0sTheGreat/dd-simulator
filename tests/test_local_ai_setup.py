from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dd_simulator.app import build_application
from dd_simulator.local_ai import LOCAL_MODEL_ALIAS, LocalAiConfiguration
from dd_simulator.local_ai import (
    GEMMA_4_E4B_DISPLAY_NAME,
    QWEN3_4B,
    RECOMMENDED_MODEL_NAME,
)
from dd_simulator.ui.services.ui_preferences import UiPreferencesStore


def test_local_ai_configuration_round_trips_through_preferences(tmp_path: Path) -> None:
    store = UiPreferencesStore(tmp_path / "preferences.json")
    configuration = LocalAiConfiguration(
        mode="llama_cpp",
        setup_complete=True,
        model_directory=str(tmp_path / "models"),
        model_path=str(tmp_path / "models" / "story.gguf"),
        model_id=LOCAL_MODEL_ALIAS,
    )

    store.save_local_ai(configuration.to_mapping())

    restored = LocalAiConfiguration.from_mapping(store.load_local_ai())
    assert restored == configuration


def test_first_run_requires_ai_setup_and_retired_modes_are_rejected(tmp_path: Path) -> None:
    UiPreferencesStore(tmp_path / "preferences.json").save_local_ai({
        "mode": "retired_mode", "setup_complete": True,
        "model_directory": str(tmp_path / "models"), "model_path": "",
    })
    app, window, _themes = build_application([], config_dir=tmp_path)
    assert window.current_page == "local_ai_setup"
    assert window.bottom_navigation.isHidden()
    assert window.local_ai_setup_panel.findChild(object, "selectNoAiButton") is None
    saved = LocalAiConfiguration.from_mapping(
        UiPreferencesStore(tmp_path / "preferences.json").load_local_ai()
    )
    assert saved.mode == ""
    assert not saved.setup_complete

    window.close()
    window.deleteLater()
    app.processEvents()


def test_setup_recommends_qwen_and_suggests_gemma(tmp_path: Path) -> None:
    app, window, _themes = build_application([], config_dir=tmp_path)
    panel = window.local_ai_setup_panel

    assert RECOMMENDED_MODEL_NAME == "Qwen3-4B-Q4_K_M.gguf"
    assert QWEN3_4B.size == 2_497_280_256
    assert "Recommended" in panel.recommended_button.text()
    assert GEMMA_4_E4B_DISPLAY_NAME in panel.large_model_button.text()
    assert panel.choice_buttons.index(panel.recommended_button) < panel.choice_buttons.index(
        panel.large_model_button
    )

    window.close()
    window.deleteLater()
    app.processEvents()
