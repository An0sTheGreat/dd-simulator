from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QApplication

from dd_simulator.lm_studio import LMStudioClient, LMStudioModelInfo
from dd_simulator.lm_studio.evaluation import ModelEvaluationService
from dd_simulator.ui.models.presentation import EquipmentSlotView, InventorySlotView
from dd_simulator.ui.panels.settings_panel import SettingsPanel
from dd_simulator.ui.services.ui_preferences import UiPreferencesStore
from dd_simulator.ui.themes.theme_manager import ThemeManager
from dd_simulator.ui.widgets.inventory_grid import EquipmentSlotWidget, InventorySlotWidget


THEMES_ROOT = Path(__file__).parents[1] / "src" / "dd_simulator" / "ui" / "themes"


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_model_discovery_lists_loaded_and_installed_metadata(monkeypatch) -> None:
    client = LMStudioClient()
    monkeypatch.setattr(
        client,
        "_json_request_url",
        lambda _url: {
            "models": [
                {"key": "installed-model", "display_name": "Installed", "loaded_instances": []},
                {
                    "key": "gemma-model",
                    "display_name": "Gemma 4 E4B",
                    "architecture": "gemma",
                    "quantization": "Q4_K_M",
                    "size_bytes": 4_000_000_000,
                    "loaded_instances": [
                        {
                            "id": "gemma-loaded",
                            "context_length": 62_000,
                            "estimated_vram_bytes": 6_000_000_000,
                        }
                    ],
                },
            ]
        },
    )

    models = client.discover_model_details()

    assert [model.loaded for model in models] == [False, True]
    assert models[1].instance_id == "gemma-loaded"
    assert models[1].context_length == 62_000
    assert models[1].memory_bytes == 6_000_000_000


def test_settings_model_picker_selects_loaded_model_by_default() -> None:
    _app()
    manager = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=Path("unused-preferences.json"),
        default_theme_id="high_fantasy",
    )
    panel = SettingsPanel(manager.available_themes())
    panel.set_models(
        (
            LMStudioModelInfo("unloaded", "Unloaded", False),
            LMStudioModelInfo("loaded", "Loaded", True, instance_id="loaded-instance"),
        ),
        "unloaded",
    )

    assert panel.model_selector.currentData() == "loaded-instance"
    assert panel.model_evaluate_button.isEnabled()
    panel.set_models((LMStudioModelInfo("only-unloaded", "Only Unloaded", False),), None)
    panel.set_model_busy(False, "Connected")
    assert not panel.model_evaluate_button.isEnabled()
    assert panel.model_load_button.isEnabled()


def test_selected_model_preference_survives_ui_reset(tmp_path: Path) -> None:
    store = UiPreferencesStore(tmp_path / "preferences.json")
    store.save_lm_studio({"model_id": "gemma-loaded"})
    store.save_ui({"font_size": "large"})
    store.reset_ui()

    assert store.load_ui() == {}
    assert store.load_lm_studio() == {"model_id": "gemma-loaded"}


def test_model_evaluation_isolated_metrics_and_report(monkeypatch, tmp_path: Path) -> None:
    client = LMStudioClient()
    monkeypatch.setattr(
        client,
        "discover_model_details",
        lambda: (
            LMStudioModelInfo(
                "gemma-model",
                "Gemma Test",
                True,
                instance_id="gemma-loaded",
                context_length=62_000,
                memory_bytes=6_000_000_000,
            ),
        ),
    )
    payloads: list[dict[str, object]] = []

    def completion(_path: str, *, method: str, payload: dict[str, object]):
        assert method == "POST"
        payloads.append(payload)
        user = json.loads(payload["messages"][1]["content"])  # type: ignore[index]
        section = user.get("requested_section")
        if section == "body_description":
            content = (
                "1. Height: 6 feet; Build: lean and athletic\n"
                "2. Height: 5 feet 8 inches; Build: broad and sturdy\n"
                "3. Height: 5 feet 4 inches; Build: compact and agile"
            )
        elif section == "campaign_name":
            content = "1. Crown of Embers\n2. The Silent Frontier\n3. Ashes at Dawn"
        else:
            content = (
                "CAMPAIGN NAME: Crown of Embers\n"
                "CAMPAIGN PREMISE: Rival heirs hunt an ember crown on the frontier."
            )
        return {
            "choices": [
                {
                    "message": {"content": content}
                }
            ],
            "usage": {"prompt_tokens": 60, "completion_tokens": 40},
        }

    monkeypatch.setattr(client, "_json_request", completion)
    service = ModelEvaluationService(client, tmp_path / "reports")

    result = service.evaluate("gemma-loaded", samples=3)

    assert result.valid_responses == result.strict_first_passes == 3
    assert result.prompt_tokens == 180
    assert result.completion_tokens == 120
    assert result.quality_score >= 90
    assert all("response_format" not in payload for payload in payloads)
    assert (tmp_path / "reports" / "latest-model-evaluation.json").is_file()
    assert (tmp_path / "reports" / "latest-model-evaluation.md").is_file()


def test_rarity_follows_item_between_inventory_and_equipment() -> None:
    _app()
    rare_dagger = InventorySlotView(
        "Star-Iron Dagger",
        quantity=1,
        rarity="rare",
        item_type="equipment",
        equip_slot="Main Hand",
    )
    inventory = InventorySlotWidget(rare_dagger, 0)
    equipment = EquipmentSlotWidget(
        EquipmentSlotView("Main Hand", "Star-Iron Dagger", item=rare_dagger),
        0,
    )

    assert inventory.property("rarity") == "rare"
    assert equipment.property("rarity") == "rare"
    inventory.enterEvent(QEnterEvent(QPointF(), QPointF(), QPointF()))
    assert inventory.hover_card is not None
    assert inventory.hover_card.property("rarity") == "rare"


def test_both_themes_compile_all_rarity_tiers(tmp_path: Path) -> None:
    manager = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "preferences.json",
        default_theme_id="high_fantasy",
    )
    for loaded in manager.discover().values():
        for rarity in ("common", "uncommon", "rare", "epic", "legendary"):
            assert f'QFrame#equipmentSlot[rarity="{rarity}"]' in loaded.stylesheet
