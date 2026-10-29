from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from dd_simulator.state import CombatAction
from dd_simulator.state.abilities import CATALOG
from dd_simulator.state.projection import _ability_stats
from dd_simulator.ui.main_window import MainWindow
from dd_simulator.ui.models.presentation import CombatActionOptionView
from dd_simulator.ui.services.mock_data import build_phase_three_dashboard
from dd_simulator.ui.services.ui_preferences import UiPreferencesStore
from dd_simulator.ui.themes.theme_manager import ThemeManager
from dd_simulator.ui.widgets.codex_cards import PowersCard
from dd_simulator.ui.widgets.hotbar import (
    ATTACK_KEY,
    HOTBAR_KEYS,
    Hotbar,
    default_slots,
    hotbar_actions,
)

THEMES_ROOT = Path(__file__).resolve().parents[1] / "src" / "dd_simulator" / "ui" / "themes"


def _power(key: str, level: str) -> CombatActionOptionView:
    return CombatActionOptionView(
        key=key, name=key.title(), kind="ability", description="", resource_label="3 stamina",
        available=True, stats=(("Level", level),),
    )


def test_self_targeted_powers_show_no_range_and_levels_show_plainly() -> None:
    row = {"current_uses": 2, "maximum_uses": 2, "cooldown_remaining": 0}
    self_stats = dict(_ability_stats(CATALOG["field_dressing"], row))
    assert self_stats["Target"] == "Self" and "Range" not in self_stats
    assert self_stats["Level"] == "2"  # was "Unlock 2"
    ranged = dict(_ability_stats(CATALOG["quick_shot"], row))
    assert ranged["Range"].endswith("ft")


def test_powers_columns_filter_by_level() -> None:
    QApplication.instance() or QApplication([])
    card = PowersCard((_power("a", "1"), _power("b", "2"), _power("c", "2")), (_power("d", "Cantrip"),))
    card.show()
    column = card.ability_column
    assert list(column.level_buttons) == ["All", "1", "2"]
    column.level_buttons["2"].click()
    assert [entry.isVisible() for entry in column.entries] == [False, True, True]
    assert column.level_buttons["2"].isChecked() and not column.level_buttons["All"].isChecked()
    column.level_buttons["All"].click()
    assert all(entry.isVisible() for entry in column.entries)
    assert card.spell_column.level_buttons == {}  # one level: nothing to pick
    card.deleteLater()


def test_hotbar_assigns_moves_clears_and_uses_slots() -> None:
    QApplication.instance() or QApplication([])
    choices = hotbar_actions((_power("quick_shot", "1"),), (_power("hex", "1"),))
    assert [c.key for c in choices] == [ATTACK_KEY, "quick_shot", "hex"]
    bar = Hotbar()
    keys = default_slots(choices)
    assert keys[:3] == [ATTACK_KEY, "quick_shot", "hex"] and len(keys) == 10
    bar.set_actions(choices, keys)
    used: list[str] = []
    saved: list[list] = []
    bar.slot_used.connect(used.append)
    bar.slots_changed.connect(saved.append)

    assert HOTBAR_KEYS == ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0")
    QTest.mouseClick(bar.slots[1], Qt.MouseButton.LeftButton)
    assert bar.use_key("1") and not bar.use_key("x")
    assert used == ["quick_shot", ATTACK_KEY]
    bar.assign(9, "hex")  # one slot per action: it moves to 0
    assert saved[-1][2] is None and saved[-1][9] == "hex"
    assert bar.slots[9].action.key == "hex" and bar.slots[2].action is None
    bar.assign(9, None)
    assert bar.slots[9].action is None
    menu = bar.slots[0].build_menu()
    assert "Clear slot" in [a.text() for a in menu.actions()]
    bar.deleteLater()


def test_hotbar_slots_persist_and_number_keys_use_them(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "preferences.json"
    manager = ThemeManager(themes_root=THEMES_ROOT, preferences_path=path, default_theme_id="high_fantasy")

    def window() -> MainWindow:
        result = MainWindow(
            manager.available_themes(), build_phase_three_dashboard(),
            preferences_store=UiPreferencesStore(path), config_dir=tmp_path,
        )
        result.resize(1600, 900)
        result.show()
        app.processEvents()
        return result

    first = window()
    assert first.hotbar.slots[0].action.key == ATTACK_KEY  # first-run defaults
    first.hotbar.assign(4, ATTACK_KEY)
    first.close()
    first.deleteLater()
    app.processEvents()

    second = window()
    assert second.hotbar.slots[4].action.key == ATTACK_KEY
    assert second.hotbar.slots[0].action is None
    QTest.keyClick(second, Qt.Key.Key_5)  # outside combat 1-6 still pick story choices
    assert "submitted" in second.statusBar().currentMessage()
    commands = []
    second._resolve_combat_action = commands.append
    second.dashboard = replace(second.dashboard, combat=_active_combat())
    QTest.keyClick(second, Qt.Key.Key_5)  # in combat the hotbar owns them
    assert [command.action for command in commands] == [CombatAction.ATTACK]
    second.close()
    second.deleteLater()
    app.processEvents()


def _active_combat():  # type: ignore[no-untyped-def]
    from dd_simulator.ui.models.presentation import CombatEncounterView

    return CombatEncounterView(
        id="encounter", status="active", round_number=1, environment="road", hazard="",
        starting_distance=30, end_reason="", combatants=(), recent_turns=(),
    )
