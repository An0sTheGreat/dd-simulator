from __future__ import annotations

import json

import pytest

from dd_simulator.state import (
    CombatAction,
    CombatCommand,
    CombatError,
    EnemySpec,
    GameStateDatabase,
    GameStateService,
)
from dd_simulator.state.combat import (
    CombatNarrationOutcome,
    CombatService,
)
from dd_simulator.state.abilities import CATALOG, class_catalog
from dd_simulator.state.character_creation import CLASSES
from dd_simulator.state.turns import NarrativeSegment


class SequenceRoller:
    def __init__(self, *values: int) -> None:
        self.values = iter(values)

    def __call__(self, _minimum: int, _maximum: int) -> int:
        return next(self.values)


def test_every_selectable_class_has_valid_combat_actions() -> None:
    for character_class in CLASSES:
        definitions = class_catalog(character_class)
        assert len(definitions) >= 4
        assert len({definition.key for definition in definitions}) == len(definitions)
        assert all(definition.key in CATALOG for definition in definitions)
        assert all(definition.kind in {"ability", "spell"} for definition in definitions)


def test_ranged_class_actions_explain_equipment_requirement() -> None:
    database, service = combat_service(20, 1)
    service.start_combat(enemies=(training_enemy(),))
    options = service.load_active_dashboard().combat.action_options  # type: ignore[union-attr]
    quick_shot = next(option for option in options if option.key == "quick_shot")
    assert not quick_shot.available
    assert quick_shot.unavailable_reason == "Requires an equipped ranged weapon"
    database.close()


def combat_service(*rolls: int) -> tuple[GameStateDatabase, GameStateService]:
    database = GameStateDatabase.in_memory()
    service = GameStateService(database)
    service.initialize()
    service.ensure_demo_campaign()
    service.combat = CombatService(database, roll=SequenceRoller(*rolls))
    return database, service


def training_enemy(**overrides: object) -> EnemySpec:
    values: dict[str, object] = {
        "name": "Training Goblin",
        "maximum_health": 6,
        "armor_class": 10,
        "attack_bonus": 2,
        "damage_die_size": 4,
        "distance_feet": 5,
        "morale": 80,
    }
    values.update(overrides)
    return EnemySpec(**values)  # type: ignore[arg-type]


def test_combat_victory_is_persistent_and_awards_progression() -> None:
    database, service = combat_service(20, 1, 20, 4, 4)
    start = service.start_combat(enemies=(training_enemy(),))
    initial = service.load_active_dashboard()
    assert start.status == "active"
    assert initial.combat is not None
    enemy = next(row for row in initial.combat.combatants if row.side == "enemy")

    result = service.execute_combat_command(
        CombatCommand(CombatAction.ATTACK, target_id=enemy.id)
    )
    dashboard = service.load_active_dashboard()

    assert result.status == "victory"
    assert dashboard.combat is not None and dashboard.combat.status == "victory"
    defeated = next(row for row in dashboard.combat.combatants if row.side == "enemy")
    assert defeated.status == "defeated"
    assert dashboard.player.experience.current == 2500
    assert next(skill for skill in dashboard.skills if skill.name == "Attack").current_xp == 405
    assert dashboard.equipment[0].item is not None
    assert dashboard.equipment[0].item.durability == 81
    assert dashboard.narrative.messages[-3].kind == "player"
    assert dashboard.narrative.messages[-2].kind == "combat"
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM combat_turns").fetchone()[0] == 1
    database.close()


class FixedNarrator:
    def resolve_combat_turn(self, **kwargs):  # type: ignore[no-untyped-def]
        allowed = kwargs["allowed_intents"]
        return CombatNarrationOutcome(
            (NarrativeSegment("narrative", "Steel flashes beside the damaged cart."),),
            {combatant_id: "attack" for combatant_id in allowed},
        )


def test_defend_enemy_turn_and_lm_narration_commit_together() -> None:
    database, service = combat_service(20, 1, 15, 3)
    service.start_combat(enemies=(training_enemy(maximum_health=20),))

    result = service.execute_combat_command(
        CombatCommand(CombatAction.DEFEND), narrator=FixedNarrator()
    )
    dashboard = service.load_active_dashboard()

    assert result.status == "active"
    assert dashboard.combat is not None and dashboard.combat.round_number == 2
    player = next(row for row in dashboard.combat.combatants if row.side == "player")
    assert player.current_health == 39
    assert player.active_turn
    assert any(
        message.text == "Steel flashes beside the damaged cart."
        for message in dashboard.narrative.messages
    )
    database.close()


def test_out_of_range_attack_rolls_back_then_advance_closes_distance() -> None:
    database, service = combat_service(20, 1)
    service.start_combat(
        enemies=(training_enemy(maximum_health=20, distance_feet=25),)
    )
    dashboard = service.load_active_dashboard()
    assert dashboard.combat is not None
    enemy = next(row for row in dashboard.combat.combatants if row.side == "enemy")

    with pytest.raises(CombatError, match="25 feet away"):
        service.execute_combat_command(
            CombatCommand(CombatAction.ATTACK, target_id=enemy.id)
        )
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM combat_turns").fetchone()[0] == 0

    service.execute_combat_command(CombatCommand(CombatAction.ADVANCE))
    dashboard = service.load_active_dashboard()
    assert dashboard.combat is not None
    enemy = next(row for row in dashboard.combat.combatants if row.side == "enemy")
    assert enemy.distance_feet == 0
    database.close()


def test_combat_potion_is_consumed_and_health_is_synchronized() -> None:
    database, service = combat_service(20, 1, 1)
    service.start_combat(enemies=(training_enemy(maximum_health=20),))
    with database.transaction() as connection:
        connection.execute(
            "UPDATE combatants SET current_health = 20 "
            "WHERE encounter_id IN (SELECT id FROM combat_encounters WHERE status = 'active') "
            "AND side = 'player'"
        )
        connection.execute(
            "UPDATE character_resources SET current_value = 20 "
            "WHERE resource_type = 'health'"
        )

    service.execute_combat_command(CombatCommand(CombatAction.USE_ITEM))
    dashboard = service.load_active_dashboard()
    player = next(row for row in dashboard.combat.combatants if row.side == "player")  # type: ignore[union-attr]

    assert player.current_health == 35
    assert next(r for r in dashboard.player.resources if r.resource_type == "health").current == 35
    assert next(item for item in dashboard.inventory_preview if item.name == "Health Potion").quantity == 2
    database.close()


def test_noncombat_turn_is_rejected_while_encounter_is_active() -> None:
    database, service = combat_service(20, 1)
    service.start_combat(enemies=(training_enemy(maximum_health=20),))

    class Provider:
        def resolve_action(self, **_kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("LM Studio must not be called during active combat")

    with pytest.raises(Exception, match="Combat is active"):
        service.resolve_player_action("Look around", Provider())
    database.close()


def test_ranged_attack_consumes_ammunition_and_rejects_empty_quiver() -> None:
    database, service = combat_service(20, 1, 15, 4)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE inventory_items SET name = 'Shortbow', equip_slot = 'Main Hand' "
            "WHERE id = 'item-0'"
        )
        connection.execute(
            "UPDATE equipment_slots SET item_name = 'Shortbow' "
            "WHERE id = 'equipment-0'"
        )
        connection.execute(
            "UPDATE inventory_items SET quantity = 1 WHERE name = 'Arrows'"
        )
    service.start_combat(
        enemies=(training_enemy(maximum_health=20, distance_feet=25),)
    )
    enemy = next(
        row
        for row in service.load_active_dashboard().combat.combatants  # type: ignore[union-attr]
        if row.side == "enemy"
    )

    service.execute_combat_command(
        CombatCommand(CombatAction.ATTACK, target_id=enemy.id)
    )
    with database.connect() as connection:
        assert connection.execute(
            "SELECT 1 FROM inventory_items WHERE name = 'Arrows'"
        ).fetchone() is None
        assert connection.execute(
            "SELECT item_name FROM equipment_slots WHERE slot_name = 'Ammunition'"
        ).fetchone()[0] is None
    with pytest.raises(CombatError, match="requires equipped Arrows"):
        service.execute_combat_command(
            CombatCommand(CombatAction.ATTACK, target_id=enemy.id)
        )
    database.close()


def test_low_morale_enemy_can_retreat_without_forced_death() -> None:
    database, service = combat_service(20, 1)
    service.start_combat(
        enemies=(training_enemy(maximum_health=20, morale=20),)
    )

    result = service.execute_combat_command(CombatCommand(CombatAction.DEFEND))
    dashboard = service.load_active_dashboard()
    enemy = next(row for row in dashboard.combat.combatants if row.side == "enemy")  # type: ignore[union-attr]

    assert result.status == "victory"
    assert enemy.status == "retreated"
    assert any("retreats from the fight" in summary for summary in result.summaries)
    database.close()


def test_power_strike_spends_stamina_and_uses_deterministic_damage() -> None:
    database, service = combat_service(20, 1, 20, 4, 4)
    service.start_combat(enemies=(training_enemy(),))
    enemy = next(
        row
        for row in service.load_active_dashboard().combat.combatants  # type: ignore[union-attr]
        if row.side == "enemy"
    )

    result = service.execute_combat_command(
        CombatCommand(CombatAction.ABILITY, target_id=enemy.id)
    )
    dashboard = service.load_active_dashboard()

    assert result.status == "victory"
    stamina = next(
        resource
        for resource in dashboard.player.resources
        if resource.resource_type == "stamina"
    )
    assert stamina.current == 23
    assert "Power Strike" in result.summaries[0]
    database.close()


def test_combat_schema_enforces_single_active_encounter() -> None:
    database, service = combat_service(20, 1)
    service.start_combat(enemies=(training_enemy(maximum_health=20),))
    with pytest.raises(CombatError, match="already active"):
        service.start_combat(enemies=(training_enemy(maximum_health=20),))
    with database.connect() as connection:
        kinds = json.loads(
            json.dumps(
                [row[0] for row in connection.execute("SELECT kind FROM narrative_messages")]
            )
        )
    assert "combat" in kinds
    database.close()


def test_warlock_spell_spends_resources_and_ticks_persistent_condition() -> None:
    database, service = combat_service(20, 1, 4, 1, 1)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE characters SET character_class = 'Warlock' WHERE is_player = 1"
        )
    service.start_combat(
        enemies=(training_enemy(maximum_health=30, armor_class=10),)
    )
    dashboard = service.load_active_dashboard()
    assert dashboard.combat is not None
    enemy = next(row for row in dashboard.combat.combatants if row.side == "enemy")
    spell_names = {
        option.name for option in dashboard.combat.action_options
        if option.kind == "spell"
    }
    assert spell_names == {"Eldritch Bolt", "Hex", "Dark Bargain", "Shadow Veil"}

    result = service.execute_combat_command(
        CombatCommand(CombatAction.SPELL, target_id=enemy.id, ability_key="hex")
    )
    dashboard = service.load_active_dashboard()
    assert result.status == "active"
    assert any("suffers 2 damage from Hex" in summary for summary in result.summaries)
    assert next(resource for resource in dashboard.player.resources if resource.resource_type == "mana").current == 38
    assert next(resource for resource in dashboard.player.resources if resource.resource_type == "spell_slots").current == 1
    enemy = next(row for row in dashboard.combat.combatants if row.side == "enemy")  # type: ignore[union-attr]
    assert enemy.current_health == 24
    assert "Hexed" in enemy.conditions
    database.close()


def test_spell_saving_throw_is_deterministic_and_audited() -> None:
    database, service = combat_service(20, 1, 6, 6, 20, 1)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE characters SET character_class = 'Cleric' WHERE is_player = 1"
        )
    service.start_combat(
        enemies=(training_enemy(maximum_health=30, armor_class=18),)
    )
    dashboard = service.load_active_dashboard()
    enemy = next(row for row in dashboard.combat.combatants if row.side == "enemy")  # type: ignore[union-attr]
    result = service.execute_combat_command(
        CombatCommand(
            CombatAction.SPELL, target_id=enemy.id, ability_key="sacred_flame"
        )
    )
    assert "Dexterity save 20" in result.summaries[0]
    assert "success" in result.summaries[0]
    enemy = next(
        row for row in service.load_active_dashboard().combat.combatants  # type: ignore[union-attr]
        if row.side == "enemy"
    )
    assert enemy.current_health == 30
    with database.connect() as connection:
        turn = connection.execute(
            "SELECT d20_roll, target_number, damage FROM combat_turns "
            "WHERE action_key = 'sacred_flame'"
        ).fetchone()
    assert tuple(turn) == (20, 12, 0)
    database.close()


def test_mage_direct_damage_spell_and_resource_availability_explanations() -> None:
    database, service = combat_service(20, 1, 3, 4, 1)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE characters SET character_class = 'Mage' WHERE is_player = 1"
        )
    service.start_combat(
        enemies=(training_enemy(maximum_health=30, armor_class=18),)
    )
    dashboard = service.load_active_dashboard()
    assert dashboard.combat is not None
    enemy = next(row for row in dashboard.combat.combatants if row.side == "enemy")
    result = service.execute_combat_command(
        CombatCommand(
            CombatAction.SPELL, target_id=enemy.id, ability_key="magic_missile"
        )
    )
    assert result.summaries[0].endswith("9 damage; 21/30 HP remains.")
    with database.transaction() as connection:
        connection.execute(
            "UPDATE character_resources SET current_value = 0 "
            "WHERE resource_type IN ('mana', 'spell_slots')"
        )
    options = service.load_active_dashboard().combat.action_options  # type: ignore[union-attr]
    assert all(
        not option.available for option in options
        if option.kind == "spell" and "Cantrip" not in option.resource_label
    )
    assert any(
        option.available for option in options
        if option.kind == "spell" and "Cantrip" in option.resource_label
    )
    assert any("Requires 2 mana" in option.unavailable_reason for option in options)
    database.close()


def test_class_ability_cooldown_limited_uses_and_short_rest_recovery() -> None:
    database, service = combat_service(20, 1, 2, 1)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE characters SET character_class = 'Warrior' WHERE is_player = 1"
        )
        connection.execute(
            "UPDATE character_resources SET current_value = 20 "
            "WHERE resource_type = 'health'"
        )
    service.start_combat(
        enemies=(training_enemy(maximum_health=30, armor_class=18),)
    )
    dashboard = service.load_active_dashboard()
    assert dashboard.combat is not None
    second_wind = next(
        option for option in dashboard.combat.action_options if option.key == "second_wind"
    )
    assert second_wind.available
    service.execute_combat_command(
        CombatCommand(CombatAction.ABILITY, ability_key="second_wind")
    )
    with database.connect() as connection:
        row = connection.execute(
            "SELECT current_uses, cooldown_remaining FROM abilities "
            "WHERE action_key = 'second_wind'"
        ).fetchone()
        assert tuple(row) == (1, 2)
        encounter_id = connection.execute(
            "SELECT id FROM combat_encounters WHERE status = 'active'"
        ).fetchone()[0]
    with database.transaction() as connection:
        connection.execute(
            "UPDATE combat_encounters SET status = 'resolved', "
            "end_reason = 'Training ended.' WHERE id = ?",
            (encounter_id,),
        )
        connection.execute(
            "UPDATE character_resources SET current_value = 1 "
            "WHERE resource_type = 'stamina'"
        )
    result = service.execute_combat_command(CombatCommand(CombatAction.RECOVER))
    assert "short rest" in result.summaries[0]
    with database.connect() as connection:
        ability = connection.execute(
            "SELECT current_uses, cooldown_remaining FROM abilities "
            "WHERE action_key = 'second_wind'"
        ).fetchone()
        stamina = connection.execute(
            "SELECT current_value FROM character_resources "
            "WHERE resource_type = 'stamina'"
        ).fetchone()[0]
    assert tuple(ability) == (2, 0)
    assert stamina > 1
    database.close()


def test_phase_ten_schema_records_ability_and_effect_fields() -> None:
    database, service = combat_service(20, 1)
    assert database.schema_version() == 23
    service.start_combat(enemies=(training_enemy(),))
    with database.connect() as connection:
        ability_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(abilities)")
        }
        condition_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(combat_conditions)")
        }
        turn_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(combat_turns)")
        }
    assert {"action_key", "action_kind", "cooldown_remaining", "current_uses"} <= ability_columns
    assert {"damage_per_round", "healing_per_round"} <= condition_columns
    assert {"action_key", "healing"} <= turn_columns
    database.close()


def test_successful_flee_resolves_and_persists_encounter() -> None:
    database, service = combat_service(20, 1, 20)
    service.start_combat(enemies=(training_enemy(maximum_health=20),))

    result = service.execute_combat_command(CombatCommand(CombatAction.FLEE))
    reloaded = GameStateService(database).load_active_dashboard()

    assert result.status == "escaped"
    assert result.skill_check is not None
    assert result.skill_check.name == "Survival"
    assert result.skill_check.total == result.skill_check.roll + result.skill_check.modifier
    assert result.skill_check.success is True
    assert reloaded.combat is not None and reloaded.combat.status == "escaped"
    assert "escaped" in reloaded.combat.end_reason.lower()
    database.close()


def test_enemy_can_defeat_player_and_persist_unconscious_condition() -> None:
    database, service = combat_service(1, 20, 20, 50, 50)
    result = service.start_combat(
        enemies=(
            training_enemy(
                maximum_health=20,
                attack_bonus=20,
                damage_die_size=100,
                damage_bonus=0,
            ),
        )
    )
    dashboard = service.load_active_dashboard()

    assert result.status == "defeat"
    assert dashboard.combat is not None and dashboard.combat.status == "defeat"
    health = next(
        resource for resource in dashboard.player.resources
        if resource.resource_type == "health"
    )
    assert health.current == 0
    with database.connect() as connection:
        assert connection.execute(
            "SELECT name FROM status_effects WHERE name = 'Unconscious'"
        ).fetchone()[0] == "Unconscious"
    database.close()


def test_projected_attack_bonus_matches_combat_player_attack_bonus() -> None:
    database, service = combat_service(20, 1)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE characters SET equipment_attack_bonus = 2 WHERE is_player = 1"
        )
    projected = service.load_active_dashboard().player.attack_bonus
    service.start_combat(enemies=(training_enemy(),))
    with database.connect() as connection:
        combat_value = connection.execute(
            "SELECT attack_bonus FROM combatants WHERE side = 'player'"
        ).fetchone()[0]
    assert projected is not None and projected == combat_value
    database.close()
