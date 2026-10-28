from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QLineEdit

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


def test_saved_lm_studio_config_still_builds_an_lm_studio_client(tmp_path: Path) -> None:
    store = UiPreferencesStore(tmp_path / "preferences.json")
    store.save_local_ai({
        "mode": "lm_studio", "setup_complete": True,
        "model_directory": str(tmp_path / "models"), "model_path": "",
    })
    store.save_lm_studio({"model_id": "gemma-lm-studio"})

    loaded = LocalAiConfiguration.from_mapping(store.load_local_ai())
    assert loaded.mode == "lm_studio"
    assert loaded.usable()

    app, window, _themes = build_application([], config_dir=tmp_path)
    assert window.current_page == "settings"
    assert window.lm_client is not None
    assert window.lm_client.provider == "lm_studio"
    assert window.lm_client.base_url == "http://localhost:1234/v1"
    assert window.lm_client.model_id == "gemma-lm-studio"
    window.close()
    window.deleteLater()
    app.processEvents()


def test_unsloth_config_requires_key_and_hides_it(tmp_path: Path) -> None:
    keyless = LocalAiConfiguration.from_mapping({"mode": "unsloth", "setup_complete": True})
    assert keyless.unsloth_port == 8888
    assert not keyless.usable()
    keyed = replace(keyless, api_key="sk-unsloth-repr-marker")
    assert keyed.usable()
    assert "sk-unsloth-repr-marker" not in repr(keyed)

    app, window, _themes = build_application([], config_dir=tmp_path)
    panel = window.local_ai_setup_panel
    order = [button.objectName() for button in panel.choice_buttons]
    assert order.index("connectUnslothButton") < order.index("connectLmStudioButton")
    assert "Unsloth Studio" in panel.large_model_button.text()
    assert panel.unsloth_port.value() == 8888
    assert panel.api_key.echoMode() == QLineEdit.EchoMode.Password
    window.close()
    window.deleteLater()
    app.processEvents()


def test_first_run_requires_ai_setup_and_retired_modes_are_rejected(tmp_path: Path) -> None:
    UiPreferencesStore(tmp_path / "preferences.json").save_local_ai({
        "mode": "retired_mode", "setup_complete": True,
        "model_directory": str(tmp_path / "models"), "model_path": "",
    })
    app, window, _themes = build_application([], config_dir=tmp_path)
    assert window.current_page == "local_ai_setup"
    # No navigation is reachable until setup completes: the scene and its tabs are not shown.
    assert window.content_stack.currentWidget() is not window.concept_splitter
    assert not window.scene_view.tabs.isVisibleTo(window)
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


def test_unsloth_setup_completes_before_any_model_is_loaded(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import json

    from dd_simulator.ui.services.local_ai_worker import LocalAiActivationTask

    class Response:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"data": [{"id": "gemma", "loaded": False}]}).encode("utf-8")

    monkeypatch.setattr("dd_simulator.local_model.client.urlopen", lambda *_a, **_k: Response())
    configuration = LocalAiConfiguration(mode="unsloth", setup_complete=True, api_key="sk-unsloth-x")
    task = LocalAiActivationTask(configuration, runtime=None)  # type: ignore[arg-type]
    succeeded: list[str] = []
    failed: list[str] = []
    task.signals.succeeded.connect(lambda _config, _endpoint, model: succeeded.append(model))
    task.signals.failed.connect(failed.append)
    task.run()
    assert failed == []
    assert succeeded == ["gemma"]
