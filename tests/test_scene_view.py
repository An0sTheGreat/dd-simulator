from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtGui import Qt as GuiQt, QTextDocument
from PySide6.QtWidgets import QApplication, QLabel

from dd_simulator.state import CombatAction, CombatCommand, GameStateDatabase, GameStateService
from dd_simulator.ui.location_images import LOCATION_ART_ROOT
from dd_simulator.ui.models.presentation import (
    CombatantView,
    CombatEncounterView,
    LocationSummaryView,
    ObjectiveView,
    QuestListItemView,
    QuestView,
)
from dd_simulator.ui.themes.theme_manager import ThemeManager
from dd_simulator.ui.widgets.quest_list import QuestListItem
from dd_simulator.ui.widgets.scene_view import (
    COMBAT_ACTIONS,
    NAV_TABS,
    ChoiceGrid,
    QuestProgressCard,
    SceneView,
    reward_chips,
)


THEMES_ROOT = Path(__file__).resolve().parents[1] / "src" / "dd_simulator" / "ui" / "themes"
SUGGESTIONS = (
    "Speak with the merchant",
    "Inspect the damaged cart",
    "Continue toward the Keep",
    "Examine the weathered signpost",
    "Ask about the Whispering Woods and the bandits who were seen near the old mill last night",
    "Search the road for tracks",
)
QUEST = QuestView(
    title="The Lost Heirloom",
    status="active",
    summary="Recover Lord Aric's heirloom.",
    objectives=(
        ObjectiveView("Travel to the bandit camp"),
        ObjectiveView("Recover the heirloom"),
        ObjectiveView("Return to Lord Aric"),
        ObjectiveView("Help the roadside merchant", completed=True, optional=True),
    ),
)
QUEST_LIST = (
    QuestListItemView("The Lost Heirloom", "active", 1, 4, selected=True, reward_summary="400 XP, 120 gold"),
)


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def location(**changes: str) -> LocationSummaryView:
    values = dict(
        name="Greystone Road", region="Silvermarch", time_label="Morning, Day 17",
        weather="Clear, 68F", danger="Low", route_status="Road open toward Greystone Keep", biome="road",
    )
    values.update(changes)
    return LocationSummaryView(**values)  # type: ignore[arg-type]


def encounter(player_turn: bool = True, wolf: str | None = None) -> CombatEncounterView:
    def combatant(id_: str, name: str, side: str, initiative: int, **extra) -> CombatantView:  # type: ignore[no-untyped-def]
        return CombatantView(
            id=id_, name=name, side=side, status="active", current_health=8, maximum_health=12,
            armor_class=13, initiative=initiative, distance_feet=10, weapon_name="", morale=10, **extra,
        )

    return CombatEncounterView(
        id="enc", status="active", round_number=2, environment="Road", hazard="", starting_distance=30,
        end_reason="", recent_turns=(),
        combatants=(
            combatant("hero", "Kaelen", "player", 15, active_turn=player_turn),
            combatant("bandit", "Bandit", "enemy", 18, declared_intent="Flank and strike"),
            *((replace(combatant("wolf", "Wolf", "enemy", 12), status=wolf),) if wolf else ()),
        ),
    )


def scene(**kwargs) -> SceneView:  # type: ignore[no-untyped-def]
    app()
    view = SceneView(location(), QUEST, SUGGESTIONS, quest_list=QUEST_LIST, **kwargs)
    view.resize(832, 876)
    view.show()
    QApplication.processEvents()
    return view


def test_scene_picks_location_art_for_biome_and_weather() -> None:
    view = scene()
    assert view.image_path == LOCATION_ART_ROOT / "road" / "road_daylight.png"
    assert view._art is not None
    view.set_location(location(weather="Heavy rain"))
    assert view.image_path == LOCATION_ART_ROOT / "road" / "road_rain.png"
    view.set_location(location(biome="forest", time_label="Night, Day 18"))
    assert view.image_path == LOCATION_ART_ROOT / "forest" / "forest_night.png"
    assert view.time_chip.text() == "DAY 18 · NIGHT"


def test_low_danger_chip_is_marked_low() -> None:
    view = scene()
    assert view.danger_chip.text() == "LOW DANGER"
    assert view.danger_chip.property("dangerLevel") == "low"
    view.set_location(location(danger="High"))
    assert view.danger_chip.property("dangerLevel") == "elevated"


def test_each_tab_emits_its_target() -> None:
    view = scene()
    spy = QSignalSpy(view.navigation_requested)
    for _title, target in NAV_TABS:
        view.tabs.buttons[target].click()
    assert [spy.at(index)[0] for index in range(spy.count())] == [t for _title, t in NAV_TABS]
    assert {"dashboard", "map", "people", "character_sheet", "settings", "journal"} == set(view.tabs.buttons)


def test_quest_ring_fraction_and_completed_styling() -> None:
    view = scene()
    card = view.quest_card
    assert (card.ring.completed, card.ring.total) == (1, 4)
    assert card.ring.fraction == 0.25
    states = [row.property("completed") for row in card.objective_rows]
    assert states == [False, False, False, True]
    assert card.objective_rows[3].text() == "Optional · Help the roadside merchant"
    assert [chip.text() for chip in card.reward_labels] == ["400 XP", "120 GOLD"]


def test_completed_objective_uses_success_colour_in_both_themes(tmp_path: Path) -> None:
    application = app()
    manager = ThemeManager(
        themes_root=THEMES_ROOT, preferences_path=tmp_path / "prefs.json",
        default_theme_id="high_fantasy",
    )
    try:
        for theme in ("high_fantasy", "modern_proof"):
            loaded = manager.load_theme(theme)
            manager.apply_loaded_theme(application, loaded, persist=False)
            view = scene()
            done, open_ = view.quest_card.objective_rows[3], view.quest_card.objective_rows[0]
            success = loaded.definition.tokens["codex"]["success"]
            assert done.palette().color(done.foregroundRole()).name() == success
            assert open_.palette().color(open_.foregroundRole()).name() != success
    finally:
        application.setStyleSheet("")


def test_set_combat_swaps_cards_both_ways() -> None:
    view = scene()
    assert view.quest_card.isVisible() and view.encounter_card is None
    view.set_combat(encounter())
    assert view.encounter_card is not None and view.encounter_card.isVisible()
    assert not view.quest_card.isVisible()
    assert set(view.encounter_card.health_bars) == {"bandit", "hero"}
    view.set_combat(None)
    assert view.quest_card.isVisible() and not view.encounter_card.isVisible()
    assert view.choice_grid.choice_buttons[0].text_label.full_text == SUGGESTIONS[0]


def test_number_keys_activate_choices_only_when_input_unfocused() -> None:
    view = scene()
    grid = view.choice_grid
    view.activateWindow()
    spy = QSignalSpy(grid.submission_requested)
    grid.choice_buttons[0].setFocus()
    QTest.keyClick(grid.choice_buttons[0], Qt.Key.Key_4)
    assert spy.count() == 1 and spy.at(0)[0] == SUGGESTIONS[3]

    grid.action_input.clear()
    grid.action_input.setFocus()
    assert QApplication.focusWidget() is grid.action_input
    QTest.keyClick(grid.action_input, Qt.Key.Key_2)
    assert spy.count() == 1
    assert grid.action_input.text() == "2"

    QTest.keyClick(grid.action_input, Qt.Key.Key_Return)
    assert spy.count() == 2 and spy.at(1)[0] == "2"


def test_combat_mode_replaces_choices_and_locks_input() -> None:
    view = scene(combat=encounter())
    grid = view.choice_grid
    assert [b.text_label.full_text for b in grid.choice_buttons] == [label for label, _a in COMBAT_ACTIONS]
    assert [label for label, _a in COMBAT_ACTIONS] == [
        "Attack", "Advance", "Defend", "Use Potion", "Negotiate", "Flee",
    ]
    assert not grid.action_input.isEnabled() and not grid.submit_button.isEnabled()
    spy = QSignalSpy(grid.combat_action_requested)
    submissions = QSignalSpy(grid.submission_requested)
    grid.choice_buttons[0].setFocus()
    QTest.keyClick(grid.choice_buttons[0], Qt.Key.Key_1)
    assert spy.count() == 1 and submissions.count() == 0
    assert spy.at(0)[0] == CombatCommand(CombatAction.ATTACK, target_id="bandit")
    view.set_combat(encounter(player_turn=False))
    assert not any(button.isEnabled() for button in grid.choice_buttons)
    view.set_combat(None)
    assert grid.action_input.isEnabled() and grid.submit_button.isEnabled()


def test_action_placeholder_names_the_actor_or_falls_back() -> None:
    assert scene(actor="Kaelen").choice_grid.action_input.placeholderText() == "Or write what Kaelen does…"
    assert scene().choice_grid.action_input.placeholderText() == "Or describe your action…"


def test_long_choice_text_is_never_silently_truncated() -> None:
    view = scene()
    view.resize(560, 876)
    QApplication.processEvents()
    button = view.choice_grid.choice_buttons[4]
    assert button.text_label.text() != SUGGESTIONS[4]
    assert tooltip_text(button) == SUGGESTIONS[4]
    assert SUGGESTIONS[4] in button.accessibleName()
    short = view.choice_grid.choice_buttons[0]
    assert short.text_label.text() == SUGGESTIONS[0] and short.toolTip() == ""


def tooltip_text(widget) -> str:  # type: ignore[no-untyped-def]
    """What a viewer reads: rich tooltips render as HTML, plain ones as-is."""
    tip = widget.toolTip()
    if not GuiQt.mightBeRichText(tip):
        return tip
    document = QTextDocument()
    document.setHtml(tip)
    return document.toPlainText()


def test_model_text_with_markup_renders_literally() -> None:
    hostile = "<img src='x'>Look at the very long and winding road toward the distant keep"
    grid = ChoiceGrid((hostile, "Wait"))
    grid.resize(260, 200)
    grid.show()
    QApplication.processEvents()
    button = grid.choice_buttons[0]
    assert button.text_label.textFormat() == Qt.TextFormat.PlainText
    assert button.text_label.text() != hostile  # elided, so a tooltip is offered
    assert tooltip_text(button) == hostile

    title = "<b>Bold</b>"
    card = QuestProgressCard(replace(QUEST, title=title), ())
    assert card.title.text() == title
    assert card.title.textFormat() == Qt.TextFormat.PlainText
    item = QuestListItem(QuestListItemView(title, "active", 0, 1))
    item_label = item.findChild(QLabel, "questListTitle")
    assert item_label.text() == title
    assert item_label.textFormat() == Qt.TextFormat.PlainText


def test_pending_cancel_and_retry_match_narrative_panel() -> None:
    view = scene()
    grid = view.choice_grid
    grid.show_resolution_pending("Search the road")
    assert not grid.action_input.isEnabled() and grid.cancel_button.isVisible()
    cancels = QSignalSpy(grid.cancellation_requested)
    grid.cancel_button.click()
    assert cancels.count() == 1 and not grid.cancel_button.isEnabled()
    grid.show_resolution_cancelled()
    assert grid.action_input.isEnabled() and grid.retry_button.isVisible()
    retries = QSignalSpy(grid.retry_requested)
    grid.retry_button.click()
    assert retries.at(0)[0] == "Search the road"
    grid.reset_resolution_controls()
    assert not grid.retry_button.isVisible() and grid.action_input.text() == ""


def test_controls_have_accessible_names() -> None:
    view = scene(combat=encounter())
    view.set_combat(None)
    named = [
        *view.tabs.buttons.values(), *view.choice_grid.choice_buttons, view.choice_grid.action_input,
        view.choice_grid.submit_button, view.quest_card, view.quest_card.ring, view.title,
        view.tabs.clock_label, *view.quest_card.objective_rows, view.encounter_card,
    ]
    assert all(widget.accessibleName() for widget in named)
    assert view.choice_grid.choice_buttons[2].accessibleName() == f"Choice 3: {SUGGESTIONS[2]}"


def test_enemy_row_click_picks_the_target_and_keeps_it_across_rebuilds() -> None:
    view = scene(combat=encounter(wolf="active"))
    grid = view.choice_grid
    card = view.encounter_card
    assert card is not None
    assert grid.target_id == "bandit"  # highest initiative is the automatic target
    assert card.rows["bandit"].property("targetSelected") is True
    assert not card.rows["hero"].property("targetable")

    QTest.mouseClick(card.rows["wolf"], Qt.MouseButton.LeftButton)
    assert grid.target_id == "wolf"
    assert card.rows["wolf"].property("targetSelected") is True
    assert card.rows["bandit"].property("targetSelected") is False
    spy = QSignalSpy(grid.combat_action_requested)
    grid.activate_choice(1)
    assert spy.at(0)[0] == CombatCommand(CombatAction.ATTACK, target_id="wolf")

    card.rows["bandit"].setFocus()
    QTest.keyClick(card.rows["bandit"], Qt.Key.Key_Space)
    assert grid.target_id == "bandit"
    QTest.mouseClick(card.rows["wolf"], Qt.MouseButton.LeftButton)

    view.set_combat(encounter(wolf="active"))
    assert grid.target_id == "wolf"
    assert view.encounter_card.rows["wolf"].property("targetSelected") is True
    view.set_combat(encounter(wolf="defeated"))
    assert grid.target_id == "bandit"
    assert not view.encounter_card.rows["bandit"].property("targetable")
    QTest.mouseClick(view.encounter_card.rows["wolf"], Qt.MouseButton.LeftButton)
    assert grid.target_id == "bandit"


def test_selected_target_has_a_style_in_both_themes(tmp_path: Path) -> None:
    manager = ThemeManager(
        themes_root=THEMES_ROOT, preferences_path=tmp_path / "prefs.json",
        default_theme_id="high_fantasy",
    )
    for theme_id in ("high_fantasy", "modern_proof"):
        stylesheet = manager.load_theme(theme_id).stylesheet
        assert 'QFrame#encounterCombatant[targetSelected="true"]' in stylesheet


def test_quest_reward_chips_include_faction_reputation() -> None:
    database = GameStateDatabase.in_memory()
    service = GameStateService(database)
    service.initialize()
    service.ensure_demo_campaign()
    with database.transaction() as connection:
        connection.execute(
            "UPDATE quests SET reward_faction = 'Lord Aric', reward_reputation = 1 WHERE selected = 1"
        )
    chips = reward_chips(service.load_active_dashboard().quest_list)
    assert "LORD ARIC +1" in chips
    database.close()
