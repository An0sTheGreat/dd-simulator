from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from dd_simulator.state import CombatAction, CombatCommand, SkillCheckResult
from dd_simulator.ui.main_window import MainWindow
from dd_simulator.ui.services.mock_data import build_phase_three_dashboard
from dd_simulator.ui.services.ui_preferences import UiPreferencesStore
from dd_simulator.ui.themes.theme_manager import ThemeManager
from dd_simulator.ui.widgets.conversation_view import ConversationView
from dd_simulator.ui.widgets.dice_roll import FADE_MS, DiceRollBanner
from test_combat import combat_service, training_enemy

THEMES_ROOT = Path(__file__).resolve().parents[1] / "src" / "dd_simulator" / "ui" / "themes"
CHECK = SkillCheckResult("Persuasion", 14, 3, 17, 15, True)


def test_attack_and_spell_rolls_reach_the_player_as_checks() -> None:
    database, service = combat_service(20, 1, 20, 4, 4)
    service.start_combat(enemies=(training_enemy(),))
    enemy = next(r for r in service.load_active_dashboard().combat.combatants if r.side == "enemy")  # type: ignore[union-attr]
    check = service.execute_combat_command(CombatCommand(CombatAction.ATTACK, target_id=enemy.id)).skill_check
    assert check is not None and check.target_label == "AC" and check.target == 10
    assert check.roll == 20 and check.success
    database.close()

    # sacred flame: the d20 is the enemy's save, so a saved roll is the player's failure
    database, service = combat_service(20, 1, 6, 6, 20, 1)
    with database.transaction() as connection:
        connection.execute("UPDATE characters SET character_class = 'Cleric' WHERE is_player = 1")
    service.start_combat(enemies=(training_enemy(maximum_health=30, armor_class=18),))
    enemy = next(r for r in service.load_active_dashboard().combat.combatants if r.side == "enemy")  # type: ignore[union-attr]
    check = service.execute_combat_command(
        CombatCommand(CombatAction.SPELL, target_id=enemy.id, ability_key="sacred_flame")
    ).skill_check
    assert check is not None and "Dexterity save" in check.name
    assert check.roll == 20 and check.success is False
    database.close()


def test_banner_rolls_lands_coloured_holds_then_fades() -> None:
    app = QApplication.instance() or QApplication([])
    banner = DiceRollBanner(CHECK, hold_ms=3000)
    assert banner.state == "rolling" and banner.outcome.text() == "ROLLING…"
    banner.start()
    banner.roll_animation.setCurrentTime(banner.roll_animation.duration())
    app.processEvents()
    assert banner.state == "success" and banner.outcome.text() == "SUCCESS"
    assert banner.outcome.property("checkState") == "success"
    assert "17" in banner.detail.text() and "DC 15" in banner.detail.text()
    assert banner.hold_timer.isActive() and banner.hold_timer.interval() == 3000
    assert banner.fade_animation.duration() == FADE_MS == 1000

    failed = DiceRollBanner(SkillCheckResult("Attack", 3, 2, 5, 12, False, "AC"), reduced_motion=True)
    failed.start()
    assert failed.outcome.text() == "FAILED" and failed.outcome.property("checkState") == "failure"
    assert "AC 12" in failed.detail.text()
    banner.deleteLater()
    failed.deleteLater()


def test_roll_sits_below_the_newest_message_and_removes_itself() -> None:
    app = QApplication.instance() or QApplication([])
    view = ConversationView(reduced_motion=True)
    view.resize(500, 400)
    view.set_messages(build_phase_three_dashboard().narrative.messages, False)
    view.show()
    banner = view.show_roll(CHECK, 50)
    layout = view.widget().layout()
    assert layout.indexOf(banner) == layout.count() - 1  # after the last message row
    assert layout.indexOf(view.rows[-1]) < layout.indexOf(banner)
    banner.hold_timer.timeout.emit()
    banner.fade_animation.setCurrentTime(FADE_MS)
    app.processEvents()
    assert view.roll_banner is None
    view.deleteLater()


def test_display_time_is_a_saved_setting(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "preferences.json"
    manager = ThemeManager(themes_root=THEMES_ROOT, preferences_path=path, default_theme_id="high_fantasy")

    def window() -> MainWindow:
        return MainWindow(
            manager.available_themes(), build_phase_three_dashboard(),
            preferences_store=UiPreferencesStore(path), config_dir=tmp_path,
        )

    first = window()
    first.settings_panel.dice_roll_slider.setValue(6)
    assert first.dice_roll_seconds_preference == 6.0
    first._flush_ui_preferences()
    first._show_skill_check(CHECK)
    assert first.conversation_view.roll_banner is not None
    assert first.conversation_view.roll_banner.hold_ms == 6000
    first.close()
    first.deleteLater()
    app.processEvents()

    second = window()
    assert second.dice_roll_seconds_preference == 6.0
    assert second.settings_panel.dice_roll_slider.value() == 6
    second.close()
    second.deleteLater()
    app.processEvents()
