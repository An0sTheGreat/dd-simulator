from __future__ import annotations

import pytest

from dd_simulator.state import GameStateDatabase, GameStateService
from dd_simulator.state.abilities import (
    CATALOG,
    scaled_definition,
    spell_slot_maximum,
    sync_character_combat_catalog,
)
from dd_simulator.state.progression import (
    allocate_ability_points,
    award_character_experience,
    proficiency_bonus,
    xp_to_next,
)
from dd_simulator.state.quests import complete_objective
from dd_simulator.state.errors import GameStateError


def initialized_demo() -> tuple[GameStateDatabase, GameStateService, str]:
    database = GameStateDatabase.in_memory()
    service = GameStateService(database)
    assert service.initialize() == 23
    campaign_id = service.ensure_demo_campaign()
    return database, service, campaign_id


def test_fixed_level_table_proficiency_and_cantrip_scaling() -> None:
    assert xp_to_next(1) == 300
    assert xp_to_next(4) == 3_800
    assert proficiency_bonus(1) == 2
    assert proficiency_bonus(5) == 3
    assert proficiency_bonus(17) == 6
    fire_bolt = CATALOG["fire_bolt"]
    assert fire_bolt.is_cantrip
    assert fire_bolt.resource_cost == fire_bolt.spell_slot_cost == 0
    assert [scaled_definition(fire_bolt, level).dice_count for level in (1, 5, 11, 17)] == [1, 2, 3, 4]


def test_level_four_awards_hp_asi_slots_and_unlocks() -> None:
    database, _service, _campaign_id = initialized_demo()
    with database.transaction() as connection:
        character = connection.execute(
            "SELECT id FROM characters WHERE is_player = 1"
        ).fetchone()
        character_id = str(character["id"])
        connection.execute(
            "UPDATE characters SET level = 3, character_class = 'Wizard', "
            "pending_ability_points = 0 WHERE id = ?",
            (character_id,),
        )
        connection.execute(
            "UPDATE character_resources SET current_value = 1790, maximum_value = 1800 "
            "WHERE character_id = ? AND resource_type = 'experience'",
            (character_id,),
        )
        health_before = connection.execute(
            "SELECT maximum_value FROM character_resources WHERE character_id = ? "
            "AND resource_type = 'health'",
            (character_id,),
        ).fetchone()[0]
        result = award_character_experience(connection, character_id, 10)
        assert result.level == 4
        assert result.pending_ability_points == 2
        health_after = connection.execute(
            "SELECT maximum_value FROM character_resources WHERE character_id = ? "
            "AND resource_type = 'health'",
            (character_id,),
        ).fetchone()[0]
        assert health_after == health_before + 6
        slots = connection.execute(
            "SELECT maximum_value FROM character_resources WHERE character_id = ? "
            "AND resource_type = 'spell_slots'",
            (character_id,),
        ).fetchone()[0]
        assert slots == spell_slot_maximum("Wizard", 4) == 7
        unlocks = {
            row["action_key"]: bool(row["unlocked"])
            for row in connection.execute(
                "SELECT action_key, unlocked FROM abilities WHERE character_id = ? "
                "AND action_key IN ('fire_bolt', 'magic_missile', 'ice_bind', 'arcane_ward')",
                (character_id,),
            )
        }
        assert unlocks == {
            "fire_bolt": True,
            "magic_missile": True,
            "ice_bind": True,
            "arcane_ward": False,
        }
        allocate_ability_points(connection, character_id, {"Strength": 2})
        strength = connection.execute(
            "SELECT value FROM character_attributes WHERE character_id = ? "
            "AND name = 'Strength'",
            (character_id,),
        ).fetchone()[0]
        assert strength == 18
        assert connection.execute(
            "SELECT pending_ability_points FROM characters WHERE id = ?",
            (character_id,),
        ).fetchone()[0] == 0
    database.close()


def test_level_one_catalog_keeps_later_features_locked() -> None:
    database, _service, _campaign_id = initialized_demo()
    with database.transaction() as connection:
        character = connection.execute(
            "SELECT id FROM characters WHERE is_player = 1"
        ).fetchone()
        sync_character_combat_catalog(
            connection,
            str(character["id"]),
            character_class="Mage",
            level=1,
        )
        unlocks = {
            row["action_key"]: bool(row["unlocked"])
            for row in connection.execute(
                "SELECT action_key, unlocked FROM abilities WHERE character_id = ? "
                "AND action_key IN ('fire_bolt', 'magic_missile', 'ice_bind', 'arcane_ward')",
                (character["id"],),
            )
        }
    assert unlocks == {
        "fire_bolt": True,
        "magic_missile": True,
        "ice_bind": False,
        "arcane_ward": False,
    }
    database.close()


def test_final_quest_gate_rejects_investigation_until_outcome_is_resolved() -> None:
    database, _service, campaign_id = initialized_demo()
    with database.transaction() as connection:
        objective = connection.execute(
            "SELECT id, trigger_target FROM quest_objectives WHERE quest_id = "
            "(SELECT id FROM quests WHERE campaign_id = ? AND status = 'active' LIMIT 1) "
            "ORDER BY display_order DESC LIMIT 1",
            (campaign_id,),
        ).fetchone()
        connection.execute(
            "UPDATE quest_objectives SET completion_gate = 1, completed = 0, "
            "current_count = 0 WHERE id = ?",
            (objective["id"],),
        )
        connection.execute(
            "UPDATE quest_objectives SET completed = 1 WHERE optional = 0 AND id <> ? "
            "AND quest_id = (SELECT quest_id FROM quest_objectives WHERE id = ?)",
            (objective["id"], objective["id"]),
        )
        with pytest.raises(GameStateError, match="clearly resolved outcome"):
            complete_objective(
                connection,
                campaign_id,
                str(objective["id"]),
                evidence=f"I inspect {objective['trigger_target']} and consider whether I should destroy it.",
            )
        summary = complete_objective(
            connection,
            campaign_id,
            str(objective["id"]),
            evidence=f"I destroy {objective['trigger_target']} and resolve the danger.",
        )
        assert "Completed objective" in summary
    database.close()
