from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from dd_simulator.state import (
    CombatAction,
    CombatCommand,
    EnemySpec,
    GameStateDatabase,
    GameStateService,
)
from dd_simulator.state.combat import CombatService
from dd_simulator.state.encounters import generate_encounter
from dd_simulator.ui.widgets.combat_rewards_dialog import CombatRewardsDialog


THEMES_ROOT = (
    Path(__file__).parents[1] / "src" / "dd_simulator" / "ui" / "themes"
)


class SequenceRoller:
    def __init__(self, *values: int) -> None:
        self.values = iter(values)

    def __call__(self, _minimum: int, _maximum: int) -> int:
        return next(self.values)


def service_with_demo(*rolls: int) -> tuple[GameStateDatabase, GameStateService]:
    database = GameStateDatabase.in_memory()
    service = GameStateService(database)
    service.initialize()
    service.ensure_demo_campaign()
    if rolls:
        service.combat = CombatService(database, roll=SequenceRoller(*rolls))
    else:
        service.combat = CombatService(database, roll=lambda low, high: (low + high) // 2)
    return database, service


def finish_training_encounter() -> tuple[GameStateDatabase, GameStateService]:
    database, service = service_with_demo(20, 1, 20, 4, 4)
    service.start_combat(
        enemies=(
            EnemySpec(
                "Training Goblin", 6, 10, 2, 4, distance_feet=5,
                archetype_key="goblin_skirmisher",
            ),
        )
    )
    combat = service.load_active_dashboard().combat
    assert combat is not None
    enemy = next(row for row in combat.combatants if row.side == "enemy")
    result = service.execute_combat_command(
        CombatCommand(CombatAction.ATTACK, target_id=enemy.id)
    )
    assert result.status == "victory"
    return database, service


def test_generated_encounter_is_deterministic_and_uses_persistent_catalog() -> None:
    database, service = service_with_demo()
    campaign_id = service.campaigns.active_campaign_id()
    assert campaign_id is not None
    with database.connect() as connection:
        first = generate_encounter(connection, campaign_id)
        second = generate_encounter(connection, campaign_id)
        catalog_count = connection.execute(
            "SELECT COUNT(*) FROM enemy_archetypes"
        ).fetchone()[0]

    assert first == second
    assert first.enemies
    assert first.introduction
    assert first.terrain
    assert catalog_count >= 8
    database.close()


def test_generated_encounter_requires_and_persists_preparation() -> None:
    database, service = service_with_demo()
    result = service.start_combat()
    dashboard = service.load_active_dashboard()

    assert result.status == "active"
    assert dashboard.combat is not None
    assert dashboard.combat.generated
    assert not dashboard.combat.intro_complete
    assert dashboard.combat.introduction
    assert all(enemy.archetype_key for enemy in dashboard.combat.combatants if enemy.side == "enemy")

    prepared = service.execute_combat_command(
        CombatCommand(CombatAction.PREPARE, preparation="scout")
    )
    dashboard = service.load_active_dashboard()
    assert prepared.status in {"active", "defeat"}
    assert dashboard.combat is not None and dashboard.combat.intro_complete
    assert dashboard.combat.preparation_choice == "scout"
    assert any("scouts the opposition" in summary for summary in prepared.summaries)
    database.close()


def test_victory_reward_is_persisted_claimable_and_acknowledgeable() -> None:
    database, service = finish_training_encounter()
    dashboard = service.load_active_dashboard()
    assert dashboard.combat is not None and dashboard.combat.reward is not None
    reward = dashboard.combat.reward

    assert reward.outcome == "victory"
    assert reward.experience > 0
    assert reward.currency > 0
    assert reward.items and not reward.acknowledged
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM combat_rewards").fetchone()[0] == 1
        assert connection.execute(
            "SELECT progression_applied FROM combat_rewards"
        ).fetchone()[0] == 1

    claimed_id = reward.items[0].id
    message = service.claim_combat_reward_item(claimed_id)
    assert message.startswith("Claimed")
    claimed = service.load_active_dashboard().combat
    assert claimed is not None and claimed.reward is not None
    assert next(item for item in claimed.reward.items if item.id == claimed_id).claimed

    service.acknowledge_combat_reward(reward.id)
    acknowledged = service.load_active_dashboard().combat
    assert acknowledged is not None and acknowledged.reward is not None
    assert acknowledged.reward.acknowledged
    database.close()


def test_reward_dialog_exposes_themed_totals_claims_and_continue() -> None:
    app = QApplication.instance() or QApplication([])
    database, service = finish_training_encounter()
    dashboard = service.load_active_dashboard()
    assert dashboard.combat is not None and dashboard.combat.reward is not None

    dialog = CombatRewardsDialog(dashboard.combat, dashboard.player)
    assert dialog.objectName() == "combatRewardsDialog"
    assert dialog.findChild(QLabel, "combatRewardsTitle").text() == "VICTORY REWARDS"
    assert dialog.findChild(object, "claimAllRewardsButton") is not None
    assert dialog.findChild(object, "continueAfterCombatButton") is not None
    assert len(dialog.item_buttons) == len(dashboard.combat.reward.items)
    dialog.close()
    dialog.deleteLater()
    app.processEvents()
    database.close()


def _relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    lighter, darker = sorted((_relative_luminance(first), _relative_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_modern_theme_is_dark_and_core_text_meets_contrast_target() -> None:
    manifest = json.loads(
        (THEMES_ROOT / "modern_proof" / "theme.json").read_text(encoding="utf-8")
    )
    colors = manifest["tokens"]["colors"]

    assert manifest["name"] == "Modern Dark Simple"
    assert _relative_luminance(colors["background_primary"]) < 0.02
    for surface in ("background_primary", "background_secondary", "panel_surface", "panel_surface_alt"):
        channels = tuple(int(colors[surface][index:index + 2], 16) for index in (1, 3, 5))
        assert max(channels) - min(channels) <= 4
        assert _contrast(colors["text_primary"], colors[surface]) >= 7
        assert _contrast(colors["text_secondary"], colors[surface]) >= 4.5
