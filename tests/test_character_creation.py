from __future__ import annotations

import os
from pathlib import Path
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPlainTextEdit

from dd_simulator.app import build_application
from dd_simulator.lm_studio import CharacterRandomizationService, LMStudioModelInfo
from dd_simulator.state import GameStateDatabase, GameStateError, GameStateService
from dd_simulator.state.character_creation import (
    CLASSES,
    DEFAULT_CONTENT_PREFERENCES,
    CharacterCreationDraft,
    CharacterCreationValidator,
    level_one_hit_points,
    point_buy_spent,
)
from dd_simulator.state.migrations import LATEST_SCHEMA_VERSION, MIGRATIONS
from dd_simulator.state.presets import LAST_ORRERY_OF_SOL, load_preset
from dd_simulator.state.quests import complete_objective, progress_quests
from dd_simulator.ui.main_window import MainWindow
from dd_simulator.ui.panels.campaign_panels import CampaignBrowserPanel, CharacterCreationPanel
from dd_simulator.ui.panels.utility_panels import MinimapPanel
from dd_simulator.ui.services.mock_data import build_phase_three_dashboard
from dd_simulator.ui.services.ui_preferences import UiPreferencesStore
from dd_simulator.ui.themes.theme_manager import ThemeManager
from dd_simulator.ui.widgets.full_click_combo import FullClickComboBox


THEMES_ROOT = Path(__file__).parents[1] / "src" / "dd_simulator" / "ui" / "themes"
VALID_ABILITY_SCORES = (
    ("Strength", 10), ("Dexterity", 15), ("Constitution", 13),
    ("Intelligence", 8), ("Wisdom", 15), ("Charisma", 10),
)


def unlock_panel(panel: CharacterCreationPanel) -> None:
    panel.set_models(
        (LMStudioModelInfo("local", "Local Model", True, "local-instance"),),
        "local-instance",
    )


def allocate_abilities(panel: CharacterCreationPanel) -> None:
    panel.ability_scores.update(dict(VALID_ABILITY_SCORES))
    panel._update_ability_controls()


def valid_draft(**changes: object) -> CharacterCreationDraft:
    values: dict[str, object] = {
        "campaign_name": "Northern Lights",
        "campaign_description": "A vanished border patrol draws the hero into an ancient forest conspiracy.",
        "name": "Aria Vale",
        "ancestry": "Human",
        "age": 22,
        "gender_identity": "Woman",
        "pronouns": "she/her",
        "body_description": "Tall, athletic, and quietly confident.",
        "face_description": "Green eyes, black hair, and a small cheek scar.",
        "clothing_style": "Practical layered traveling clothes.",
        "background": "Former soldier",
        "character_class": "Ranger",
        "primary_weapon": "Longsword",
        "secondary_weapon": "Dagger",
        "ranged_weapon": "Longbow",
        "armor": "Leather armor",
        "shield": "",
        "important_tool": "Compass",
        "keepsake": "Silver locket",
        "personalities": ("Brave", "Curious"),
        "primary_strength": "Courage",
        "meaningful_flaw": "Pride",
        "motivation": "Adventure",
        "biography": "A wandering ranger.",
        "backstory": "Raised near an old forest after the border wars.",
        "skills": ("Attack", "Ranged", "Survival"),
        "world_type": "Classic high fantasy",
        "tone": "Heroic",
        "starting_region": "Forest village",
        "starting_location": "Tavern",
        "difficulty": "Adventurer",
        "content_preferences": "Include mystery; exclude graphic injury.",
        "visual_style": "Classic fantasy illustration",
        "camera_style": "Cinematic wide-angle",
        "ability_scores": VALID_ABILITY_SCORES,
    }
    values.update(changes)
    return CharacterCreationDraft(**values)  # type: ignore[arg-type]


def test_character_creation_validator_enforces_required_adult_and_skill_rules() -> None:
    assert CharacterCreationValidator.validate(valid_draft()) == {}
    errors = CharacterCreationValidator.validate(
        valid_draft(name=" ", age=12, skills=("Attack", "Attack"), personalities=())
    )
    assert "name" in errors
    assert "age" in errors
    assert "skills" in errors
    assert "personalities" in errors

    elf_errors = CharacterCreationValidator.validate(valid_draft(ancestry="Elf", age=99))
    assert "at least 100" in elf_errors["age"]


def test_point_buy_and_class_hit_points_follow_5e_rules() -> None:
    assert point_buy_spent(VALID_ABILITY_SCORES) == 27
    assert level_one_hit_points("Barbarian", 14) == 14
    assert level_one_hit_points("Fighter", 14) == 12
    assert level_one_hit_points("Wizard", 14) == 8
    assert all(level_one_hit_points(name, 10) > 0 for name in CLASSES)

    app = QApplication.instance() or QApplication([])
    panel = CharacterCreationPanel()
    allocate_abilities(panel)
    assert panel.points_left_label.text() == "POINTS LEFT: 0"
    assert all(not button.isEnabled() for button in panel.ability_plus_buttons.values())
    panel.character_class.setCurrentText("Ranger")
    assert "Hit die: d10" in panel.character_class.toolTip()
    assert "Level 1 HP with Constitution 13: 11" in panel.character_class.toolTip()
    panel.deleteLater()
    app.processEvents()


def test_creation_controls_are_fixed_choice_and_personality_is_limited() -> None:
    app = QApplication.instance() or QApplication([])
    panel = CharacterCreationPanel()
    unlock_panel(panel)

    combos = panel.findChildren(FullClickComboBox)
    assert len(combos) >= 17
    assert all(not combo.isEditable() for combo in combos)
    assert set(panel.equipment_fields) == {
        "primary_weapon", "secondary_weapon", "ranged_weapon", "armor",
        "shield", "important_tool", "keepsake",
    }
    assert all(field.count() > 0 for field in panel.equipment_fields.values())

    panel.personality_buttons["Brave"].click()
    panel.personality_buttons["Curious"].click()
    assert panel.personality_buttons["Brave"].text().startswith("✓")
    assert not panel.personality_buttons["Ruthless"].isEnabled()
    assert panel.draft().personalities == ("Brave", "Curious")
    assert panel.personality_counter.text() == "2 / 2 selected"
    for combo in (panel.primary_strength, panel.flaw, panel.motivation):
        assert combo.toolTip()
        assert combo.itemData(0, Qt.ItemDataRole.ToolTipRole)

    panel.deleteLater()
    app.processEvents()


def test_blank_content_preferences_use_concise_default() -> None:
    app = QApplication.instance() or QApplication([])
    panel = CharacterCreationPanel()
    panel.content_preferences.clear()
    assert panel.draft().content_preferences == DEFAULT_CONTENT_PREFERENCES
    panel.deleteLater()
    app.processEvents()


def test_blank_content_preferences_are_persisted_as_default(tmp_path: Path) -> None:
    database = GameStateDatabase(tmp_path / "state.db")
    service = GameStateService(database)
    service.initialize()
    campaign_id = service.complete_character_creation(
        valid_draft(content_preferences="")
    )
    with database.connect() as connection:
        stored = connection.execute(
            "SELECT content_preferences FROM campaign_preferences WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()[0]
    assert stored == DEFAULT_CONTENT_PREFERENCES


def test_last_orrery_preset_seeds_authored_world_and_chained_milestones(tmp_path: Path) -> None:
    database = GameStateDatabase(tmp_path / "preset.db")
    service = GameStateService(database)
    service.initialize()
    campaign_id = service.complete_character_creation(
        valid_draft(
            preset_id=LAST_ORRERY_OF_SOL,
            campaign_name="The Last Orrery of Sol",
        ),
        opening_text="Generating your campaign... please wait!",
    )
    dashboard = service.load_campaign(campaign_id)
    assert dashboard.is_preset_campaign
    assert dashboard.campaign_name == "The Last Orrery of Sol"
    assert dashboard.location.name == "Meridian Museum"
    assert [quest.title for quest in dashboard.quest_list] == [
        "The Day the Moon Moved",
        "The Choir Beneath Tycho",
        "Red Maze, Black Sun",
        "The Ocean That Looked Back",
        "The Last Orrery",
    ]
    assert dashboard.quest_list[0].status == "active"
    assert all(quest.status == "rumored" for quest in dashboard.quest_list[1:])
    context = service.build_action_context()
    assert context["preset_campaign"]["active_quest"]["title"] == "The Day the Moon Moved"
    assert "Selene Freeport" not in context["preset_campaign"]["active_quest"]["known_locations"]

    with database.transaction() as connection:
        objectives = [
            row
            for row in connection.execute(
                "SELECT trigger_type, trigger_target, required_count "
                "FROM quest_objectives WHERE quest_id = ? AND optional = 0 "
                "ORDER BY display_order",
                (dashboard.quest_list[0].id,),
            ).fetchall()
        ]
        for objective in objectives:
            target = str(objective["trigger_target"])
            for _ in range(int(objective["required_count"])):
                progress_quests(
                    connection, campaign_id, str(objective["trigger_type"]), target,
                    detail=f"Resolve {target} completely.",
                )
    advanced = service.load_campaign(campaign_id)
    assert advanced.player.level == 2
    assert advanced.player.experience.current == 0
    assert advanced.player.experience.maximum == 600
    assert advanced.player.currency == 175
    assert advanced.quest_list[1].status == "active"
    with database.connect() as connection:
        selene = connection.execute(
            "SELECT discovered FROM locations WHERE campaign_id = ? AND name = 'Selene Freeport'",
            (campaign_id,),
        ).fetchone()
    assert selene is not None and bool(selene["discovered"])
    database.close()


def test_last_orrery_preset_is_selectable_and_supplies_opening_fallback() -> None:
    app = QApplication.instance() or QApplication([])
    panel = CharacterCreationPanel()
    assert panel.preset_selector.count() == 2
    panel.preset_selector.setCurrentIndex(1)
    draft = panel.draft()
    preset = load_preset(LAST_ORRERY_OF_SOL)
    assert draft.preset_id == LAST_ORRERY_OF_SOL
    assert draft.campaign_name == preset["name"]
    assert panel.campaign_name.isReadOnly()
    fallback = CharacterRandomizationService.fallback_intro(
        valid_draft(preset_id=LAST_ORRERY_OF_SOL)
    )
    assert "moon" in fallback.casefold()
    assert len(fallback.split()) <= 220
    panel.deleteLater()
    app.processEvents()


def test_last_orrery_five_quest_playthrough_reaches_level_five(tmp_path: Path) -> None:
    database = GameStateDatabase(tmp_path / "orrery-playthrough.db")
    service = GameStateService(database)
    service.initialize()
    campaign_id = service.complete_character_creation(
        valid_draft(
            preset_id=LAST_ORRERY_OF_SOL,
            campaign_name="The Last Orrery of Sol",
        )
    )

    expected = (
        ("The Day the Moon Moved", 2),
        ("The Choir Beneath Tycho", 3),
        ("Red Maze, Black Sun", 4),
        ("The Ocean That Looked Back", 5),
        ("The Last Orrery", 5),
    )
    for title, expected_level in expected:
        dashboard = service.load_campaign(campaign_id)
        active = next(quest for quest in dashboard.quest_list if quest.status == "active")
        assert active.title == title
        with database.transaction() as connection:
            objectives = connection.execute(
                "SELECT trigger_type, trigger_target, required_count "
                "FROM quest_objectives WHERE quest_id = ? AND optional = 0 "
                "ORDER BY display_order",
                (active.id,),
            ).fetchall()
            for objective in objectives:
                target = str(objective["trigger_target"])
                for _ in range(int(objective["required_count"])):
                    progress_quests(
                        connection, campaign_id, str(objective["trigger_type"]), target,
                        detail=f"Resolve {target} completely.",
                    )
        resolved = service.load_campaign(campaign_id)
        assert resolved.player.level == expected_level
        reward = resolved.pending_quest_reward
        assert reward is not None
        for item in reward.items:
            service.claim_quest_reward_item(item.id)
        service.acknowledge_quest_reward(reward.id)

    completed = service.load_campaign(campaign_id)
    assert all(quest.status == "completed" for quest in completed.quest_list)
    assert completed.player.currency == 625
    with database.connect() as connection:
        reward_names = {
            str(row[0]) for row in connection.execute(
                "SELECT name FROM inventory_items WHERE character_id = "
                "(SELECT id FROM characters WHERE campaign_id = ?)",
                (campaign_id,),
            ).fetchall()
        }
    assert {"Orrery Key", "Jovian Aegis", "Martian Vector", "Lunar Lens"} <= reward_names
    database.close()


def test_last_orrery_encounter_gate_rejects_skips_and_unresolved_prose(
    tmp_path: Path,
) -> None:
    database = GameStateDatabase(tmp_path / "orrery-gates.db")
    service = GameStateService(database)
    service.initialize()
    campaign_id = service.complete_character_creation(
        valid_draft(preset_id=LAST_ORRERY_OF_SOL)
    )
    with database.transaction() as connection:
        rows = connection.execute(
            "SELECT id, trigger_type, trigger_target FROM quest_objectives "
            "WHERE quest_id LIKE '%-preset-quest-day-moon-moved' AND optional = 0 "
            "ORDER BY display_order"
        ).fetchall()
        sentinel = rows[2]
        with pytest.raises(GameStateError, match="earlier required objectives"):
            complete_objective(
                connection, campaign_id, str(sentinel["id"]),
                evidence="I destroy the falling sentinel.",
            )
        for row in rows[:2]:
            target = str(row["trigger_target"])
            progress_quests(
                connection, campaign_id, str(row["trigger_type"]), target,
                detail=f"Resolve {target} completely.",
            )
        with pytest.raises(GameStateError, match="named target"):
            complete_objective(
                connection, campaign_id, str(sentinel["id"]),
                evidence="I consider my options.",
            )
        assert "Completed objective" in complete_objective(
            connection, campaign_id, str(sentinel["id"]),
            evidence="I destroy the falling sentinel and secure the chamber.",
        )


def test_last_orrery_preset_references_are_closed_and_unique() -> None:
    preset = load_preset(LAST_ORRERY_OF_SOL)
    location_ids = [entry["id"] for entry in preset["locations"]]
    npc_ids = [entry["id"] for entry in preset["npcs"]]
    quest_ids = [entry["id"] for entry in preset["quests"]]
    assert len(location_ids) == len(set(location_ids))
    assert len(npc_ids) == len(set(npc_ids))
    assert len(quest_ids) == len(set(quest_ids)) == 5
    locations = set(location_ids)
    assert all(route["origin"] in locations and route["destination"] in locations
               for route in preset["routes"])
    assert all(npc["location"] in locations for npc in preset["npcs"])
    assert all(set(quest["locations"]) <= locations for quest in preset["quests"])
    assert all(set(quest["unlock_locations"]) <= locations for quest in preset["quests"])
    assert len(preset["opening"]["suggested_actions"]) == 6


def test_caster_creation_atomically_adds_spell_resources_and_catalog(tmp_path: Path) -> None:
    database = GameStateDatabase(tmp_path / "caster.db")
    service = GameStateService(database)
    service.initialize()
    campaign_id = service.complete_character_creation(
        valid_draft(character_class="Mage")
    )
    dashboard = service.load_campaign(campaign_id)
    resource_types = {resource.resource_type for resource in dashboard.player.resources}
    assert {"mana", "spell_slots"} <= resource_types
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT action_kind, action_key FROM abilities "
            "WHERE character_id = (SELECT id FROM characters WHERE campaign_id = ?) "
            "ORDER BY display_order",
            (campaign_id,),
        ).fetchall()
    assert len(rows) == 4
    assert all(row["action_kind"] == "spell" for row in rows)
    database.close()


def test_full_click_combo_opens_from_its_main_surface() -> None:
    class PopupSpyCombo(FullClickComboBox):
        def __init__(self) -> None:
            super().__init__()
            self.popup_count = 0

        def showPopup(self) -> None:
            self.popup_count += 1

    app = QApplication.instance() or QApplication([])
    combo = PopupSpyCombo()
    combo.addItems(("One", "Two"))
    combo.resize(180, 34)
    combo.show()
    QTest.mouseClick(combo, Qt.MouseButton.LeftButton)
    assert combo.popup_count == 1
    combo.deleteLater()
    app.processEvents()


def test_failed_randomization_reenables_button_and_preserves_text() -> None:
    class OfflineRandomizer:
        def generate_options(self, _section, _draft):  # type: ignore[no-untyped-def]
            from dd_simulator.lm_studio import LMStudioConnectionError

            raise LMStudioConnectionError("LM Studio is offline")

    class ImmediatePool:
        def start(self, task):  # type: ignore[no-untyped-def]
            task.run()

    app = QApplication.instance() or QApplication([])
    panel = CharacterCreationPanel(
        OfflineRandomizer(), thread_pool=ImmediatePool()  # type: ignore[arg-type]
    )
    unlock_panel(panel)
    panel.body.setPlainText("Keep this body description")
    panel._request_randomization("body_description")

    assert panel.body.toPlainText() == "Keep this body description"
    assert panel.randomize_buttons["body_description"].isEnabled()
    assert panel.randomize_buttons["body_description"].text() == "Randomize"
    assert panel.error_label.text() == "LM Studio is offline"
    panel.deleteLater()
    app.processEvents()


def test_cancelled_option_dialog_can_be_randomized_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RepeatRandomizer:
        calls = 0

        def generate_options(self, _section, _draft):  # type: ignore[no-untyped-def]
            self.calls += 1
            return (f"first {self.calls}", f"second {self.calls}", f"third {self.calls}")

    class ImmediatePool:
        def start(self, task):  # type: ignore[no-untyped-def]
            task.run()

    class FakeDialog:
        DialogCode = QDialog.DialogCode
        calls = 0

        def __init__(self, _label, options, _parent):  # type: ignore[no-untyped-def]
            self.options = options

        def exec(self):  # type: ignore[no-untyped-def]
            type(self).calls += 1
            return (
                self.DialogCode.Rejected
                if self.calls == 1
                else self.DialogCode.Accepted
            )

        def selected_option(self):  # type: ignore[no-untyped-def]
            return self.options[1]

    monkeypatch.setattr(
        "dd_simulator.ui.panels.campaign_panels.OptionSelectionDialog", FakeDialog
    )
    app = QApplication.instance() or QApplication([])
    randomizer = RepeatRandomizer()
    panel = CharacterCreationPanel(
        randomizer, thread_pool=ImmediatePool()  # type: ignore[arg-type]
    )
    unlock_panel(panel)
    panel.body.setPlainText("Keep this until selected")

    panel._request_randomization("body_description")
    assert panel.body.toPlainText() == "Keep this until selected"
    assert panel.randomize_buttons["body_description"].isEnabled()

    panel._request_randomization("body_description")
    assert panel.body.toPlainText() == "second 2"
    assert panel.randomize_buttons["body_description"].isEnabled()
    assert randomizer.calls == 2
    panel.deleteLater()
    app.processEvents()


def test_try_again_regenerates_before_applying_an_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RepeatRandomizer:
        calls = 0

        def generate_options(self, _section, _draft):  # type: ignore[no-untyped-def]
            self.calls += 1
            return tuple(f"choice {self.calls}-{index}" for index in range(3))

    class ImmediatePool:
        def start(self, task):  # type: ignore[no-untyped-def]
            task.run()

    class FakeDialog:
        DialogCode = QDialog.DialogCode
        RETRY_RESULT = 2
        calls = 0

        def __init__(self, _label, options, _parent):  # type: ignore[no-untyped-def]
            self.options = options

        def exec(self):  # type: ignore[no-untyped-def]
            type(self).calls += 1
            return self.RETRY_RESULT if self.calls == 1 else self.DialogCode.Accepted

        def selected_option(self):  # type: ignore[no-untyped-def]
            return self.options[0]

    monkeypatch.setattr(
        "dd_simulator.ui.panels.campaign_panels.OptionSelectionDialog", FakeDialog
    )
    app = QApplication.instance() or QApplication([])
    randomizer = RepeatRandomizer()
    panel = CharacterCreationPanel(
        randomizer, thread_pool=ImmediatePool()  # type: ignore[arg-type]
    )
    unlock_panel(panel)

    panel._request_randomization("body_description")
    app.processEvents()

    assert randomizer.calls == 2
    assert panel.body.toPlainText() == "choice 2-0"
    panel.deleteLater()
    app.processEvents()


def test_randomization_targets_only_the_selected_text_section() -> None:
    app = QApplication.instance() or QApplication([])
    panel = CharacterCreationPanel()
    panel.body.setPlainText("Existing body")
    panel.face.setPlainText("Existing face")

    panel.apply_generated_option("body_description", "Generated body")

    assert panel.body.toPlainText() == "Generated body"
    assert panel.face.toPlainText() == "Existing face"
    assert set(panel.randomize_buttons) == {
        "campaign_name", "character_name",
        "body_description", "face_description", "clothing_style",
        "biography",
    }
    assert panel.backstory is panel.biography
    assert panel.draft().backstory == ""
    panel.deleteLater()
    app.processEvents()


def test_creation_requires_a_loaded_local_model_and_confirmation() -> None:
    app = QApplication.instance() or QApplication([])
    panel = CharacterCreationPanel()

    assert panel.tabs.tabText(0) == "1. Local AI Model Selection"
    assert panel.tabs.count() == 4
    assert all(not panel.tabs.isTabEnabled(index) for index in range(1, panel.tabs.count()))
    assert not panel.complete_button.isEnabled()

    unlock_panel(panel)
    assert all(panel.tabs.isTabEnabled(index) for index in range(1, panel.tabs.count()))
    panel.review_confirmed.setChecked(True)
    assert panel.complete_button.isEnabled()
    panel.review_confirmed.setChecked(False)
    assert not panel.complete_button.isEnabled()
    panel.deleteLater()
    app.processEvents()


def test_long_written_creation_fields_are_limited_to_4000_characters() -> None:
    app = QApplication.instance() or QApplication([])
    panel = CharacterCreationPanel()
    panel.body.setPlainText("x" * 4100)
    panel.biography.setPlainText("y" * 4100)

    assert len(panel.body.toPlainText()) == 4000
    assert len(panel.biography.toPlainText()) == 4000
    counters = panel.findChildren(QLabel, "creationCharacterCounter")
    assert any(counter.text() == "4000 / 4000" for counter in counters)
    panel.deleteLater()
    app.processEvents()


def test_personality_and_equipment_options_expose_explanatory_tooltips() -> None:
    app = QApplication.instance() or QApplication([])
    panel = CharacterCreationPanel()
    assert "danger" in panel.personality_buttons["Brave"].toolTip().casefold()
    weapon = panel.equipment_fields["primary_weapon"]
    dagger_index = weapon.findText("Dagger")
    tooltip = str(weapon.itemData(dagger_index, Qt.ItemDataRole.ToolTipRole))
    assert "Damage: 1d4 piercing" in tooltip
    assert "Compatible slot" in tooltip
    panel.deleteLater()
    app.processEvents()


def test_phase_five_database_migrates_to_character_creation_schema(tmp_path: Path) -> None:
    path = tmp_path / "phase-five.db"
    connection = sqlite3.connect(path)
    connection.executescript(MIGRATIONS[0][1])
    connection.execute(
        "CREATE TABLE schema_migrations ("
        "version INTEGER PRIMARY KEY, "
        "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    connection.execute(
        "INSERT INTO schema_migrations(version, applied_at) VALUES (1, CURRENT_TIMESTAMP)"
    )
    connection.execute(
        "INSERT INTO campaigns(id, name) VALUES ('existing', 'Existing Campaign')"
    )
    connection.commit()
    connection.close()

    database = GameStateDatabase(path)
    assert database.initialize() == LATEST_SCHEMA_VERSION == 21
    with database.connect() as migrated:
        campaign = migrated.execute(
            "SELECT creation_complete FROM campaigns WHERE id = 'existing'"
        ).fetchone()
        character_columns = {
            str(row[1]) for row in migrated.execute("PRAGMA table_info(characters)")
        }
    assert campaign[0] == 1
    assert {"species", "background", "biography", "backstory"} <= character_columns


def test_character_creation_commits_complete_campaign_atomically(tmp_path: Path) -> None:
    database = GameStateDatabase(tmp_path / "state.db")
    service = GameStateService(database)
    service.initialize()

    campaign_id = service.complete_character_creation(valid_draft())
    dashboard = service.load_campaign(campaign_id)

    assert dashboard.player.name == "Aria Vale"
    assert dashboard.player.level == 1
    assert dashboard.player.character_class == "Ranger"
    assert dashboard.player.currency == 100
    assert dict((value.name, value.value) for value in dashboard.player.attributes) == dict(
        VALID_ABILITY_SCORES
    )
    health = next(
        value for value in dashboard.player.resources if value.resource_type == "health"
    )
    assert (health.current, health.maximum) == (11, 11)
    assert dashboard.location.name == "Tavern"
    assert dashboard.location.region == "Forest village"
    assert len(dashboard.inventory_preview) == 36
    assert dashboard.equipment[0].item_name == "Longsword"
    assert all(item.name != "Longsword" for item in dashboard.inventory_preview)
    assert [skill.name for skill in dashboard.skills if skill.level == 10] == [
        "Attack", "Ranged", "Survival"
    ]
    assert service.campaigns.active_campaign_id() == campaign_id

    with database.connect() as connection:
        character = connection.execute(
            "SELECT species, age, biography, backstory FROM characters "
            "WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        preferences = connection.execute(
            "SELECT world_type, tone, difficulty, visual_style, camera_style "
            "FROM campaign_preferences WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        campaign = connection.execute(
            "SELECT premise FROM campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
        opening = connection.execute(
            "SELECT text FROM narrative_messages WHERE campaign_id = ? ORDER BY sequence",
            (campaign_id,),
        ).fetchall()
    assert tuple(character) == (
        "Human", 22, "A wandering ranger.",
        "Raised near an old forest after the border wars.",
    )
    assert tuple(preferences) == (
        "Classic high fantasy", "Heroic", "Adventurer",
        "Classic fantasy illustration", "Cinematic wide-angle",
    )
    assert campaign[0] == valid_draft().campaign_description
    assert [row[0] for row in opening] == [valid_draft().campaign_description]


def test_character_creation_removes_model_markdown_from_names(tmp_path: Path) -> None:
    database = GameStateDatabase(tmp_path / "state.db")
    service = GameStateService(database)
    service.initialize()

    campaign_id = service.complete_character_creation(
        valid_draft(campaign_name="**Northern Lights**", name="*Aria Vale**"),
        opening_text="*Aria Vale** arrives beneath the northern lights.",
    )

    campaign = service.campaigns.get(campaign_id)
    assert campaign is not None and campaign.name == "Northern Lights"
    dashboard = service.load_campaign(campaign_id)
    assert (dashboard.player.name, dashboard.player.portrait_initials) == ("Aria Vale", "AV")
    assert dashboard.narrative.messages[0].text == "Aria Vale arrives beneath the northern lights."
    database.close()


def test_campaign_delete_cascades_and_selects_remaining_campaign(tmp_path: Path) -> None:
    database = GameStateDatabase(tmp_path / "state.db")
    service = GameStateService(database)
    service.initialize()
    demo_id = service.ensure_demo_campaign()
    campaign_id = service.complete_character_creation(valid_draft())

    assert service.delete_campaign(campaign_id) == demo_id
    assert service.campaigns.get(campaign_id) is None
    with database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM characters WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()[0] == 0
    database.close()


def test_campaign_browser_delete_and_location_visual_panel() -> None:
    app = QApplication.instance() or QApplication([])
    campaign = type("Campaign", (), {
        "campaign_id": "campaign-1", "name": "One", "status": "active",
        "creation_complete": True,
    })()
    browser = CampaignBrowserPanel((campaign,))  # type: ignore[arg-type]
    browser.resize(700, 600)
    browser.show()
    app.processEvents()
    assert browser.preset_list.y() < browser.campaign_list.y()
    assert abs(browser.preset_list.height() - browser.campaign_list.height()) <= 1
    delete_spy = QSignalSpy(browser.delete_requested)
    browser.delete_button.click()
    assert delete_spy.count() == 1
    assert delete_spy.at(0) == ["campaign-1"]
    preset_spy = QSignalSpy(browser.preset_requested)
    preset_item = browser.preset_list.item(0)
    browser.preset_list.itemClicked.emit(preset_item)
    assert preset_spy.count() == 1
    assert preset_spy.at(0) == [LAST_ORRERY_OF_SOL]

    minimap = MinimapPanel(build_phase_three_dashboard().location)
    assert minimap.findChild(QLabel, "locationVisualPlaceholder") is not None
    assert minimap.findChild(QLabel, "panelTitle") is None
    browser.deleteLater()
    minimap.deleteLater()
    app.processEvents()


def test_campaign_opening_placeholder_is_replaced_and_autosaved(tmp_path: Path) -> None:
    database = GameStateDatabase(tmp_path / "state.db")
    service = GameStateService(database)
    service.initialize()
    campaign_id = service.complete_character_creation(
        valid_draft(),
        opening_text="Generating your campaign... please wait!",
    )
    assert service.load_campaign(campaign_id).narrative.messages[0].text == (
        "Generating your campaign... please wait!"
    )

    introduction = (
        "Morning gathers over the forest village as Aria Vale reaches the old road. "
        "A broken warning bell sounds beyond the trees, demanding an immediate choice."
    )
    service.replace_campaign_introduction(campaign_id, introduction)
    reloaded = service.load_campaign(campaign_id)
    assert [message.text for message in reloaded.narrative.messages] == [introduction]
    with database.connect() as connection:
        stored = connection.execute(
            "SELECT text FROM narrative_messages WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchall()
    assert [row[0] for row in stored] == [introduction]


def test_creation_failure_rolls_back_campaign_and_character(tmp_path: Path) -> None:
    database = GameStateDatabase(tmp_path / "state.db")
    service = GameStateService(database)
    service.initialize()
    with database.connect() as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_new_narrative
            BEFORE INSERT ON narratives
            BEGIN SELECT RAISE(ABORT, 'forced creation failure'); END
            """
        )

    with pytest.raises(GameStateError, match="forced creation failure"):
        service.complete_character_creation(valid_draft())

    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM characters").fetchone()[0] == 0


def test_application_starts_on_local_ai_setup_then_campaign_browser(tmp_path: Path) -> None:
    UiPreferencesStore(tmp_path / "preferences.json").save_local_ai({
        "mode": "lm_studio", "setup_complete": True,
        "model_directory": str(tmp_path / "models"), "model_path": "",
    })
    app, window, manager = build_application([], config_dir=tmp_path)

    assert window.current_page == "settings"
    assert not window.bottom_navigation.isHidden()
    assert window.settings_page.isAncestorOf(window.campaign_browser)
    assert window.campaign_browser.campaign_list.count() == 1
    assert window.findChild(object, "newCampaignButton") is not None

    loaded = manager.apply_theme(app, "modern_proof")
    window.select_theme(loaded.definition.theme_id)
    window.controller.navigate("character_creation")
    app.processEvents()
    assert window.theme_selector.currentData() == "modern_proof"
    assert window.settings_panel.theme_selector.currentData() == "modern_proof"
    assert window.content_stack.currentWidget() is window.character_creation_panel
    assert len(window.character_creation_panel.findChildren(QPlainTextEdit)) >= 6
    assert window.character_creation_panel.skill_box.accessibleName()

    window.close()
    window.deleteLater()
    app.processEvents()


def test_ui_creation_saves_then_refreshes_dashboard_and_campaign_list(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    manager = ThemeManager(
        themes_root=THEMES_ROOT,
        preferences_path=tmp_path / "preferences.json",
        default_theme_id="high_fantasy",
    )
    database = GameStateDatabase(tmp_path / "state.db")
    service = GameStateService(database)
    service.initialize()
    service.ensure_demo_campaign()
    window = MainWindow(
        manager.available_themes(),
        build_phase_three_dashboard(),
        game_state_service=service,
        start_on_campaigns=True,
    )
    panel = window.character_creation_panel
    window.controller.navigate("character_creation")
    unlock_panel(panel)
    panel.campaign_name.setText("Northern Lights")
    panel.campaign_description.setPlainText(
        "An edited premise that must become the campaign's opening narrative."
    )
    panel.character_name.setText("Aria Vale")
    panel.age.setValue(22)
    panel.body.setPlainText("Tall and athletic")
    panel.face.setPlainText("Green eyes and black hair")
    panel.clothing.setPlainText("Practical traveling clothes")
    panel.equipment_fields["primary_weapon"].setCurrentText("Longsword")
    panel.content_preferences.setPlainText("No graphic injury")
    for skill in ("Attack", "Ranged", "Survival"):
        panel.skill_buttons[skill].click()
    panel.personality_buttons["Brave"].click()
    panel.review_confirmed.setChecked(True)
    assert panel.complete_button.isEnabled()

    panel._complete()
    assert panel.tabs.currentIndex() == 1
    assert panel.error_label.text() == "Ability Scores: Spend all 27 ability points."

    allocate_abilities(panel)

    panel._complete()
    app.processEvents()

    assert window.current_page == "dashboard"
    assert window.dashboard.player.name == "Aria Vale"
    assert len(service.list_campaigns()) == 2
    with database.connect() as connection:
        saved_premise = connection.execute(
            "SELECT premise FROM campaigns WHERE id = ?",
            (service.campaigns.active_campaign_id(),),
        ).fetchone()[0]
    assert saved_premise == (
        "An edited premise that must become the campaign's opening narrative."
    )
    window.controller.navigate("settings")
    assert window.campaign_browser.campaign_list.count() == 2

    demo_row = next(
        row
        for row in range(window.campaign_browser.campaign_list.count())
        if window.campaign_browser.campaign_list.item(row).data(Qt.ItemDataRole.UserRole)
        == "demo-greystone"
    )
    window.campaign_browser.campaign_list.setCurrentRow(demo_row)
    window.campaign_browser._load()
    app.processEvents()
    assert window.dashboard.player.name == "Kaelen Stormborne"
    assert service.campaigns.active_campaign_id() == "demo-greystone"

    window.close()
    window.deleteLater()
    app.processEvents()
