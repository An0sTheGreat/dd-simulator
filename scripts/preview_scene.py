"""Render the Concept T right column (SceneView) in both themes, plus one combat state.

Writes artifacts/previews/scene-<theme>.png and scene-combat.png (832x876) from the demo
campaign, with a placeholder where Phase 6 puts the conversation.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dd_simulator.app import build_application
from dd_simulator.ui.models.presentation import CombatEncounterView, CombatantView
from dd_simulator.ui.widgets.scene_view import SceneView


def demo_encounter() -> CombatEncounterView:
    def fighter(id_: str, name: str, side: str, hp: int, top: int, ac: int, init: int, ft: int, **extra):  # type: ignore[no-untyped-def]
        return CombatantView(
            id=id_, name=name, side=side, status="active", current_health=hp, maximum_health=top,
            armor_class=ac, initiative=init, distance_feet=ft, weapon_name="", morale=10, **extra,
        )

    return CombatEncounterView(
        id="preview", status="active", round_number=2, environment="Greystone Road", hazard="",
        starting_distance=30, end_reason="", recent_turns=(),
        combatants=(
            fighter("p", "Kaelen Stormborne", "player", 31, 42, 15, 17, 0, active_turn=True),
            fighter("e1", "Bandit Cutthroat", "enemy", 9, 16, 13, 14, 10, declared_intent="Flank and strike"),
            fighter("e2", "Bandit Archer", "enemy", 11, 11, 12, 9, 40, declared_intent="Loose arrows from cover",
                    conditions=("Hidden",)),
        ),
    )


def main() -> int:
    output_dir = Path(__file__).resolve().parents[1] / "artifacts" / "previews"
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as config_dir:
        app, window, manager = build_application([], config_dir=Path(config_dir))
        dashboard = window.dashboard
        actor = dashboard.player.name.split()[0]
        shots = (("high_fantasy", None, "scene-high_fantasy"), ("modern_proof", None, "scene-modern_proof"),
                 ("high_fantasy", demo_encounter(), "scene-combat"))
        for theme, combat, name in shots:
            manager.apply_loaded_theme(app, manager.load_theme(theme), persist=False)
            scene = SceneView(
                dashboard.location, dashboard.quest, dashboard.narrative.suggested_actions,
                quest_list=dashboard.quest_list, combat=combat, actor=actor,
            )
            scene.set_clock(17, 46)
            scene.setFixedSize(832, 876)
            scene.show()
            app.processEvents()
            path = output_dir / f"{name}.png"
            scene.grab().save(str(path))
            print(path)
            scene.close()
            scene.deleteLater()
        window.close()
        window.deleteLater()
        app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
