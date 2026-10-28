"""Render deterministic Phase 11 encounter, reward, and consolidated-UI previews."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from dd_simulator.state import (
    ActionOutcome,
    CombatAction,
    CombatCommand,
    GameStateDatabase,
    GameStateService,
    NarrativeSegment,
    EnemySpec,
)
from dd_simulator.state.combat import CombatService
from dd_simulator.ui.fonts import register_application_fonts
from dd_simulator.ui.main_window import MainWindow
from dd_simulator.ui.themes.theme_manager import ThemeManager
from dd_simulator.ui.widgets.combat_rewards_dialog import CombatRewardsDialog


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    output_override = os.environ.get("DDSIM_PREVIEW_DIR")
    output_dir = (
        Path(output_override).expanduser().resolve()
        if output_override
        else project_root / "artifacts" / "previews"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    application = QApplication.instance() or QApplication([])
    register_application_fonts()
    manager = ThemeManager(
        themes_root=project_root / "src" / "dd_simulator" / "ui" / "themes",
        preferences_path=output_dir / "preview-preferences.json",
        default_theme_id="high_fantasy",
    )
    database = GameStateDatabase.in_memory()
    service = GameStateService(database)
    service.initialize()
    service.load_active_dashboard()

    class PreviewProvider:
        def resolve_action(self, **_kwargs):  # type: ignore[no-untyped-def]
            return ActionOutcome(
                narration=(
                    "The merchant glances toward the damaged wheel. "
                    "Perhaps this traveler can help. I would welcome a careful eye."
                ),
                state_changes=(),
                quest_notes=(),
                suggested_actions=(
                    "Inspect the wheel",
                    "Ask what happened",
                    "Offer repair tools",
                    "Examine the cargo",
                    "Check the road",
                    "Continue to the keep",
                ),
                narrative_segments=(
                    NarrativeSegment(
                        "narrative",
                        "The merchant glances toward the cart's damaged wheel.",
                    ),
                    NarrativeSegment(
                        "monologue",
                        "Perhaps this traveler can help.",
                    ),
                    NarrativeSegment(
                        "spoken",
                        "I would welcome a careful eye.",
                    ),
                ),
            )

    service.resolve_player_action(
        "I ask the merchant whether assistance is needed",
        PreviewProvider(),
    )
    window = MainWindow(
        manager.available_themes(),
        service.load_active_dashboard(),
        game_state_service=service,
    )
    window.resize(1600, 900)
    window.show()

    for theme_id in ("high_fantasy", "modern_proof"):
        window.resize(1600, 900)
        loaded = manager.load_theme(theme_id)
        manager.apply_loaded_theme(application, loaded, persist=False)
        window.select_theme(theme_id)
        for page, label, creation_tab, utility_tab, action_state in (
            ("campaigns", "campaigns", None, None, None),
            ("character_creation", "character-identity", 0, None, None),
            ("character_creation", "character-appearance", 1, None, None),
            ("character_creation", "character-equipment", 3, None, None),
            ("character_creation", "character-story", 4, None, None),
            ("character_creation", "character-world", 5, None, None),
            ("skills", "skills-compact", None, None, None),
            ("quests", "quests-compact", None, None, None),
            ("dashboard", "dashboard-action-ready", None, 1, "ready"),
            ("dashboard", "dashboard-action-pending", None, 1, "pending"),
            ("dashboard", "dashboard-action-error", None, 1, "error"),
            ("dashboard", "dashboard-inventory", None, 2, "ready"),
        ):
            window.controller.navigate(page)
            if creation_tab is not None:
                window.character_creation_panel.tabs.setCurrentIndex(creation_tab)
            if utility_tab is not None:
                window.utility_panel.set_current_tab(utility_tab)
            if action_state == "ready":
                window.narrative_panel.reset_resolution_controls()
            elif action_state == "pending":
                window.narrative_panel.show_resolution_pending(
                    "Inspect the damaged cart for useful clues"
                )
            elif action_state == "error":
                window.narrative_panel.show_resolution_error(
                    "LM Studio returned an invalid turn. Your action was preserved."
                )
            application.processEvents()
            destination = output_dir / f"ui-phase11-{label}-{theme_id}.png"
            temporary = destination.with_suffix(".tmp.png")
            if not window.grab().save(str(temporary), "PNG"):
                raise RuntimeError(f"Could not save preview: {temporary}")
            temporary.replace(destination)
            print(destination)

        window.resize(1600, 900)
        window.controller.navigate("dashboard")
        window.dashboard_rows_splitter.setSizes([650, 120])
        application.processEvents()
        destination = output_dir / f"ui-phase11-dashboard-events-compressed-{theme_id}.png"
        temporary = destination.with_suffix(".tmp.png")
        if not window.grab().save(str(temporary), "PNG"):
            raise RuntimeError(f"Could not save preview: {temporary}")
        temporary.replace(destination)
        print(destination)
        window.dashboard_rows_splitter.setSizes([500, 300])

        for page, label, utility_tab in (
            ("dashboard", "dashboard-minimum", 1),
            ("skills", "skills-compact-minimum", None),
        ):
            window.resize(1280, 720)
            window.controller.navigate(page)
            if utility_tab is not None:
                window.utility_panel.set_current_tab(utility_tab)
            application.processEvents()
            destination = output_dir / f"ui-phase11-{label}-{theme_id}.png"
            temporary = destination.with_suffix(".tmp.png")
            if not window.grab().save(str(temporary), "PNG"):
                raise RuntimeError(f"Could not save preview: {temporary}")
            temporary.replace(destination)
            print(destination)

    window.close()
    database.close()

    combat_database = GameStateDatabase.in_memory()
    combat_service = GameStateService(combat_database)
    combat_service.initialize()
    combat_service.load_active_dashboard()
    with combat_database.transaction() as connection:
        connection.execute(
            "UPDATE characters SET character_class = 'Custom hybrid class' "
            "WHERE is_player = 1"
        )
    combat_rolls = iter((20, 1, 2))
    combat_service.combat = CombatService(
        combat_database,
        roll=lambda _minimum, _maximum: next(combat_rolls),
    )
    combat_service.start_combat(
        enemies=(
            EnemySpec(
                "Goblin Skirmisher", 16, 12, 3, 6,
                damage_bonus=1, initiative_modifier=2,
                distance_feet=25, morale=38,
                weapon_name="Rusty Scimitar",
            ),
            EnemySpec(
                "Goblin Archer", 12, 11, 3, 6,
                initiative_modifier=3, distance_feet=25,
                attack_range_feet=60, morale=32,
                weapon_name="Shortbow",
            ),
        )
    )
    combat_window = MainWindow(
        manager.available_themes(),
        combat_service.load_active_dashboard(),
        game_state_service=combat_service,
    )
    combat_window.show()
    combat_window.utility_panel.set_current_tab(0)
    for theme_id in ("high_fantasy", "modern_proof"):
        loaded = manager.load_theme(theme_id)
        manager.apply_loaded_theme(application, loaded, persist=False)
        combat_window.select_theme(theme_id)
        for width, height, suffix in (
            (1600, 900, ""),
            (1280, 720, "-minimum"),
        ):
            combat_window.resize(width, height)
            application.processEvents()
            destination = output_dir / f"ui-phase11-dashboard-combat{suffix}-{theme_id}.png"
            temporary = destination.with_suffix(".tmp.png")
            if not combat_window.grab().save(str(temporary), "PNG"):
                raise RuntimeError(f"Could not save preview: {temporary}")
            temporary.replace(destination)
            print(destination)
            scrollbar = combat_window.utility_panel.combat_page.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            application.processEvents()
            action_destination = output_dir / (
                f"ui-phase11-dashboard-combat-actions{suffix}-{theme_id}.png"
            )
            action_temporary = action_destination.with_suffix(".tmp.png")
            if not combat_window.grab().save(str(action_temporary), "PNG"):
                raise RuntimeError(f"Could not save preview: {action_temporary}")
            action_temporary.replace(action_destination)
            print(action_destination)
            scrollbar.setValue(0)
    combat_window.close()
    combat_database.close()

    generated_database = GameStateDatabase.in_memory()
    generated_service = GameStateService(generated_database)
    generated_service.initialize()
    generated_service.load_active_dashboard()
    generated_service.combat = CombatService(
        generated_database,
        roll=lambda minimum, maximum: (minimum + maximum) // 2,
    )
    generated_service.start_combat()
    generated_window = MainWindow(
        manager.available_themes(),
        generated_service.load_active_dashboard(),
        game_state_service=generated_service,
    )
    generated_window.resize(1600, 900)
    generated_window.show()
    generated_window.utility_panel.set_current_tab(0)
    for theme_id in ("high_fantasy", "modern_proof"):
        loaded = manager.load_theme(theme_id)
        manager.apply_loaded_theme(application, loaded, persist=False)
        generated_window.select_theme(theme_id)
        application.processEvents()
        destination = output_dir / f"ui-phase11-encounter-introduction-{theme_id}.png"
        temporary = destination.with_suffix(".tmp.png")
        if not generated_window.grab().save(str(temporary), "PNG"):
            raise RuntimeError(f"Could not save preview: {temporary}")
        temporary.replace(destination)
        print(destination)
    generated_window.close()
    generated_database.close()

    reward_database = GameStateDatabase.in_memory()
    reward_service = GameStateService(reward_database)
    reward_service.initialize()
    reward_service.load_active_dashboard()
    reward_rolls = iter((20, 1, 20, 4, 4))
    reward_service.combat = CombatService(
        reward_database,
        roll=lambda _minimum, _maximum: next(reward_rolls),
    )
    reward_service.start_combat(
        enemies=(
            EnemySpec(
                "Goblin Skirmisher", 6, 10, 2, 4, distance_feet=5,
                archetype_key="goblin_skirmisher",
            ),
        )
    )
    reward_dashboard = reward_service.load_active_dashboard()
    reward_enemy = next(
        combatant for combatant in reward_dashboard.combat.combatants
        if combatant.side == "enemy"
    )
    reward_service.execute_combat_command(
        CombatCommand(CombatAction.ATTACK, target_id=reward_enemy.id)
    )
    reward_dashboard = reward_service.load_active_dashboard()
    for theme_id in ("high_fantasy", "modern_proof"):
        loaded = manager.load_theme(theme_id)
        manager.apply_loaded_theme(application, loaded, persist=False)
        dialog = CombatRewardsDialog(
            reward_dashboard.combat, reward_dashboard.player
        )
        dialog.show()
        application.processEvents()
        destination = output_dir / f"ui-phase11-combat-rewards-{theme_id}.png"
        temporary = destination.with_suffix(".tmp.png")
        if not dialog.grab().save(str(temporary), "PNG"):
            raise RuntimeError(f"Could not save preview: {temporary}")
        temporary.replace(destination)
        print(destination)
        dialog.close()
    reward_database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
