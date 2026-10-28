from __future__ import annotations

import os
from pathlib import Path
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from dd_simulator.app import build_application
from dd_simulator.lm_studio import LMStudioModelInfo
from dd_simulator.state import GameStateDatabase, GameStateService
from dd_simulator.state.commerce import merchant_price
from dd_simulator.state.seed import DEMO_CAMPAIGN_ID, seed_demo_campaign
from dd_simulator.ui import main_window as main_window_module


def test_first_run_explains_setup_and_key_controls_are_accessible(tmp_path: Path) -> None:
    app, window, _themes = build_application([], config_dir=tmp_path)
    setup = window.local_ai_setup_panel
    settings = window.settings_panel

    setup_text = "\n".join(label.text() for label in setup.findChildren(QLabel))
    assert "BEFORE YOU START" in setup_text
    assert "3-sample evaluation" in setup_text
    assert setup.progress.accessibleName() == "Local AI setup progress"
    assert setup.status.accessibleName() == "Local AI setup status"
    assert setup.model_directory.focusPolicy() != Qt.FocusPolicy.NoFocus
    assert settings.startup_status.accessibleName() == "Application startup readiness"
    assert settings.model_status.accessibleName() == "Local AI model status"
    assert settings.reliability_status.accessibleName() == "Campaign reliability status"
    assert settings.reduced_motion_checkbox.accessibleName() == "Reduce interface motion"
    assert settings.export_logs_button.accessibleName() == "Export diagnostic logs"
    assert settings.export_logs_button.focusPolicy() != Qt.FocusPolicy.NoFocus

    settings.set_models(
        (
            LMStudioModelInfo(
                "story-model",
                "Story Model",
                True,
                architecture="gemma3",
                quantization="Q8_K",
                context_length=62_000,
                memory_bytes=9 * 1_073_741_824,
            ),
        ),
        "story-model",
    )
    tooltip = str(settings.model_selector.itemData(0, Qt.ItemDataRole.ToolTipRole))
    assert "Architecture: gemma3" in tooltip
    assert "Quantization: Q8_K" in tooltip
    assert "Context: 62,000 tokens" in tooltip
    assert "Loaded memory: 9.0 GB" in tooltip

    window.close()
    window.deleteLater()
    app.processEvents()
    if window.game_state_service is not None:
        window.game_state_service.database.close()


def test_diagnostic_export_contains_logs_but_not_campaign_data(
    tmp_path: Path, monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    log_dir = tmp_path / "logs"
    evaluation_dir = tmp_path / "model-evaluations"
    log_dir.mkdir()
    evaluation_dir.mkdir()
    (log_dir / "application.log").write_text("startup ok", encoding="utf-8")
    (evaluation_dir / "model.json").write_text('{"valid": true}', encoding="utf-8")
    destination = tmp_path / "diagnostics.zip"

    app, window, _themes = build_application([], config_dir=tmp_path)
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "ZIP archives (*.zip)"),
    )
    window._export_diagnostic_logs()

    with zipfile.ZipFile(destination) as archive:
        names = set(archive.namelist())
    assert names == {"logs/application.log", "model-evaluations/model.json"}
    assert "game_state.db" not in names
    assert "preferences.json" not in names

    window.close()
    window.deleteLater()
    app.processEvents()
    if window.game_state_service is not None:
        window.game_state_service.database.close()


def test_deadly_difficulty_affects_trade_prices_and_dialogue_checks() -> None:
    assert merchant_price(
        20, "common", None, None, "deadly", 0, action="buy"
    ) > merchant_price(
        20, "common", None, None, "adventurer", 0, action="buy"
    )

    database = GameStateDatabase.in_memory()
    database.initialize()
    seed_demo_campaign(database)
    service = GameStateService(database)
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO campaign_preferences(campaign_id, world_type, tone, difficulty, "
            "content_preferences, visual_style, camera_style) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (DEMO_CAMPAIGN_ID, "Fantasy", "Heroic", "Story", "", "Illustrated", "Wide"),
        )
        story = service.dialogue._build_context(
            connection, DEMO_CAMPAIGN_ID, "npc-roadside-merchant",
            "I persuade the merchant to help.",
        )
        connection.execute(
            "UPDATE campaign_preferences SET difficulty = 'Deadly' WHERE campaign_id = ?",
            (DEMO_CAMPAIGN_ID,),
        )
        deadly = service.dialogue._build_context(
            connection, DEMO_CAMPAIGN_ID, "npc-roadside-merchant",
            "I persuade the merchant to help.",
        )

    assert story["difficulty"] == 10
    assert deadly["difficulty"] == 16
    database.close()
