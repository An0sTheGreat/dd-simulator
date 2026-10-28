"""Deterministic, database-backed combat rules and turn orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import json
import random
import re
import sqlite3
from typing import Any, Protocol
from uuid import uuid4

from dd_simulator.state.abilities import (
    CATALOG,
    CombatAbilityDefinition,
    scaled_definition,
    sync_character_combat_catalog,
)
from dd_simulator.state.database import GameStateDatabase
from dd_simulator.state.encounters import (
    ENEMY_ABILITIES,
    GeneratedEncounter,
    archetype_by_key,
    generate_encounter,
    sync_enemy_archetypes,
)
from dd_simulator.state.errors import CombatError
from dd_simulator.state.item_actions import (
    item_definition,
    materialize_item_metadata,
    recalculate_character_item_totals,
)
from dd_simulator.state.item_catalog import select_loot
from dd_simulator.state.quests import progress_quests
from dd_simulator.state.progression import (
    award_character_experience,
    proficiency_bonus,
)
from dd_simulator.state.turns import NarrativeSegment, SkillCheckResult


class CombatAction(str, Enum):
    ATTACK = "attack"
    ABILITY = "ability"
    SPELL = "spell"
    ADVANCE = "advance"
    DEFEND = "defend"
    USE_ITEM = "use_item"
    FLEE = "flee"
    NEGOTIATE = "negotiate"
    PREPARE = "prepare"
    RECOVER = "recover"


@dataclass(frozen=True, slots=True)
class CombatCommand:
    action: CombatAction
    target_id: str | None = None
    item_id: str | None = None
    ability_key: str | None = None
    preparation: str | None = None


@dataclass(frozen=True, slots=True)
class EnemySpec:
    name: str
    maximum_health: int
    armor_class: int
    attack_bonus: int
    damage_die_size: int
    damage_bonus: int = 0
    initiative_modifier: int = 0
    distance_feet: int = 25
    movement_feet: int = 15
    attack_range_feet: int = 5
    morale: int = 50
    intelligence: str = "average"
    weapon_name: str = "Weapon"
    archetype_key: str = ""
    abilities: tuple[str, ...] = ()
    resistances: tuple[str, ...] = ()
    vulnerabilities: tuple[str, ...] = ()
    behavior_profile: str = ""


@dataclass(frozen=True, slots=True)
class CombatNarrationOutcome:
    narrative_segments: tuple[NarrativeSegment, ...]
    enemy_intents: dict[str, str]


class CombatNarrationProvider(Protocol):
    def resolve_combat_turn(
        self,
        *,
        context: dict[str, Any],
        allowed_intents: dict[str, tuple[str, ...]],
    ) -> CombatNarrationOutcome: ...


@dataclass(frozen=True, slots=True)
class CombatActionResult:
    encounter_id: str
    status: str
    summaries: tuple[str, ...]
    skill_check: SkillCheckResult | None = None


DEFAULT_ENEMIES = (
    EnemySpec(
        "Goblin Skirmisher",
        maximum_health=16,
        armor_class=12,
        attack_bonus=3,
        damage_die_size=6,
        damage_bonus=1,
        initiative_modifier=2,
        morale=38,
        intelligence="cunning",
        weapon_name="Rusty Scimitar",
    ),
    EnemySpec(
        "Goblin Archer",
        maximum_health=12,
        armor_class=11,
        attack_bonus=3,
        damage_die_size=6,
        initiative_modifier=3,
        attack_range_feet=60,
        morale=32,
        intelligence="cautious",
        weapon_name="Shortbow",
    ),
)


WEAPON_PROFILES: dict[str, tuple[int, int, int]] = {
    "iron dagger": (1, 4, 5),
    "dagger": (1, 4, 5),
    "shortsword": (1, 6, 5),
    "longsword": (1, 8, 5),
    "battleaxe": (1, 8, 5),
    "warhammer": (1, 8, 5),
    "spear": (1, 6, 10),
    "shortbow": (1, 6, 60),
    "longbow": (1, 8, 120),
    "light crossbow": (1, 8, 80),
    "heavy crossbow": (1, 10, 100),
}


class CombatService:
    """Own combat mechanics; the LLM may phrase results but never calculate them."""

    def __init__(
        self,
        database: GameStateDatabase,
        *,
        roll: Callable[[int, int], int] | None = None,
    ) -> None:
        self.database = database
        self.roll = roll or random.SystemRandom().randint

    def sync_character_catalogs(self) -> None:
        """Backfill Phase 10 resources/actions for existing player characters."""

        with self.database.transaction() as connection:
            sync_enemy_archetypes(connection)
            campaign_ids = tuple(
                str(row["campaign_id"])
                for row in connection.execute(
                    "SELECT campaign_id FROM characters WHERE is_player = 1"
                )
            )
            for campaign_id in campaign_ids:
                self.ensure_character_combat_catalog(connection, campaign_id)

    def start_generated_encounter(
        self,
        campaign_id: str,
        *,
        narrator: CombatNarrationProvider | None = None,
    ) -> CombatActionResult:
        with self.database.connect() as connection:
            generated = generate_encounter(connection, campaign_id)
        enemies = tuple(
            EnemySpec(
                enemy.name, enemy.maximum_health, enemy.armor_class,
                enemy.attack_bonus, enemy.damage_die_size, enemy.damage_bonus,
                enemy.initiative_modifier, enemy.distance_feet,
                enemy.movement_feet, enemy.attack_range_feet, enemy.morale,
                enemy.intelligence, enemy.weapon_name, enemy.key,
                enemy.abilities, enemy.resistances, enemy.vulnerabilities,
                enemy.behavior_profile,
            )
            for enemy in generated.enemies
        )
        return self.start_encounter(
            campaign_id,
            enemies=enemies,
            environment=generated.environment,
            hazard=generated.hazard,
            generated=generated,
            narrator=narrator,
        )

    def start_encounter(
        self,
        campaign_id: str,
        *,
        enemies: tuple[EnemySpec, ...] = DEFAULT_ENEMIES,
        environment: str = "Greystone Road",
        hazard: str = "A damaged cart narrows the road and provides partial cover.",
        generated: GeneratedEncounter | None = None,
        narrator: CombatNarrationProvider | None = None,
    ) -> CombatActionResult:
        if not enemies:
            raise CombatError("A combat encounter requires at least one enemy.")
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT id FROM combat_encounters WHERE campaign_id = ? AND status = 'active'",
                (campaign_id,),
            ).fetchone()
            if existing is not None:
                raise CombatError("A combat encounter is already active.")
            self.ensure_character_combat_catalog(connection, campaign_id)
            player = self._player_snapshot(connection, campaign_id)
            location = connection.execute(
                "SELECT id, name FROM locations WHERE campaign_id = ? AND is_current = 1",
                (campaign_id,),
            ).fetchone()
            if location is None:
                raise CombatError("Combat requires a current location.")
            encounter_id = f"combat-{uuid4().hex}"
            starting_distance = max(enemy.distance_feet for enemy in enemies)
            intro_complete = 0 if generated is not None else 1
            awareness = "aware" if generated is None else generated.awareness_state
            connection.execute(
                """
                INSERT INTO combat_encounters(
                    id, campaign_id, location_id, starting_distance, environment,
                    hazard, generated, intro_complete, introduction, terrain,
                    awareness_state, difficulty_rating,
                    reinforcement_archetype_key, reinforcement_round
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    encounter_id,
                    campaign_id,
                    str(location["id"]),
                    starting_distance,
                    environment or str(location["name"]),
                    hazard,
                    int(generated is not None), intro_complete,
                    "" if generated is None else generated.introduction,
                    "" if generated is None else generated.terrain,
                    awareness,
                    1 if generated is None else generated.difficulty_rating,
                    "" if generated is None else generated.reinforcement_key,
                    None if generated is None else generated.reinforcement_round,
                ),
            )
            combatants: list[dict[str, Any]] = [
                {
                    **player,
                    "id": f"combatant-{uuid4().hex}",
                    "initiative": self.roll(1, 20) + int(player["initiative_modifier"])
                    + (-5 if awareness == "player_surprised" else 5 if awareness == "enemies_surprised" else 0),
                    "archetype_key": "",
                    "abilities_json": "[]",
                    "resistances_json": "[]",
                    "vulnerabilities_json": "[]",
                    "behavior_profile": "Player controlled.",
                }
            ]
            for enemy in enemies:
                combatants.append(
                    {
                        "id": f"combatant-{uuid4().hex}",
                        "character_id": None,
                        "name": enemy.name,
                        "side": "enemy",
                        "current_health": enemy.maximum_health,
                        "maximum_health": enemy.maximum_health,
                        "armor_class": enemy.armor_class,
                        "attack_bonus": enemy.attack_bonus,
                        "damage_dice_count": 1,
                        "damage_die_size": enemy.damage_die_size,
                        "damage_bonus": enemy.damage_bonus,
                        "initiative_modifier": enemy.initiative_modifier,
                        "initiative": self.roll(1, 20) + enemy.initiative_modifier,
                        "distance_feet": enemy.distance_feet,
                        "movement_feet": enemy.movement_feet,
                        "attack_range_feet": enemy.attack_range_feet,
                        "cover_bonus": 0,
                        "morale": enemy.morale,
                        "intelligence": enemy.intelligence,
                        "weapon_name": enemy.weapon_name,
                        "weapon_item_id": None,
                        "archetype_key": enemy.archetype_key,
                        "abilities_json": json.dumps(enemy.abilities),
                        "resistances_json": json.dumps(enemy.resistances),
                        "vulnerabilities_json": json.dumps(enemy.vulnerabilities),
                        "behavior_profile": enemy.behavior_profile,
                    }
                )
            combatants.sort(
                key=lambda entry: (
                    -int(entry["initiative"]),
                    0 if entry["side"] == "player" else 1,
                    str(entry["name"]),
                )
            )
            for order, combatant in enumerate(combatants):
                connection.execute(
                    """
                    INSERT INTO combatants(
                        id, encounter_id, character_id, name, side,
                        current_health, maximum_health, armor_class, attack_bonus,
                        damage_dice_count, damage_die_size, damage_bonus, initiative,
                        initiative_modifier, distance_feet, movement_feet,
                        attack_range_feet, cover_bonus, morale, intelligence,
                        weapon_name, weapon_item_id, display_order, archetype_key,
                        abilities_json, resistances_json, vulnerabilities_json,
                        behavior_profile
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        combatant["id"], encounter_id, combatant["character_id"],
                        combatant["name"], combatant["side"], combatant["current_health"],
                        combatant["maximum_health"], combatant["armor_class"],
                        combatant["attack_bonus"], combatant["damage_dice_count"],
                        combatant["damage_die_size"], combatant["damage_bonus"],
                        combatant["initiative"], combatant["initiative_modifier"],
                        combatant["distance_feet"], combatant["movement_feet"],
                        combatant["attack_range_feet"], combatant["cover_bonus"],
                        combatant["morale"], combatant["intelligence"],
                        combatant["weapon_name"], combatant["weapon_item_id"], order,
                        combatant["archetype_key"], combatant["abilities_json"],
                        combatant["resistances_json"], combatant["vulnerabilities_json"],
                        combatant["behavior_profile"],
                    ),
                )
            opening = (
                generated.introduction if generated is not None
                else f"Combat begins at {environment or location['name']} from {starting_distance} feet."
            )
            summaries = [opening]
            narration_segments: tuple[NarrativeSegment, ...] = ()
            if narrator is not None:
                try:
                    narration = narrator.resolve_combat_turn(
                        context=self._narration_context(connection, encounter_id, opening),
                        allowed_intents={},
                    )
                    narration_segments = narration.narrative_segments
                except Exception:
                    narration_segments = ()
            if intro_complete:
                summaries.extend(self._run_until_player(connection, encounter_id, {}))
            turn_number = self._next_campaign_turn(connection, campaign_id)
            self._append_messages(
                connection,
                campaign_id,
                turn_number,
                (
                    ("combat", summaries[0]),
                    *((segment.kind, segment.text) for segment in narration_segments),
                    *(("combat", summary) for summary in summaries[1:]),
                ),
            )
            self._append_event(connection, campaign_id, summaries[0])
            status = self._encounter_status(connection, encounter_id)
            if status != "active":
                summaries.extend(self._finalize_encounter(connection, encounter_id))
            self._refresh_narrative_prompt(
                connection, campaign_id, active=status == "active"
            )
        return CombatActionResult(encounter_id, status, tuple(summaries))

    def perform_action(
        self,
        campaign_id: str,
        command: CombatCommand,
        *,
        narrator: CombatNarrationProvider | None = None,
    ) -> CombatActionResult:
        with self.database.transaction() as connection:
            if command.action is CombatAction.RECOVER:
                return self._recover_after_combat(connection, campaign_id)
            encounter = connection.execute(
                "SELECT * FROM combat_encounters WHERE campaign_id = ? AND status = 'active'",
                (campaign_id,),
            ).fetchone()
            if encounter is None:
                raise CombatError("There is no active combat encounter.")
            encounter_id = str(encounter["id"])
            if not bool(encounter["intro_complete"]):
                if command.action is not CombatAction.PREPARE:
                    raise CombatError("Choose an encounter preparation before acting.")
                player_summary = self._apply_preparation(
                    connection, encounter, command.preparation
                )
                summaries = [player_summary]
                connection.execute(
                    "UPDATE combat_encounters SET intro_complete = 1, "
                    "preparation_choice = ? WHERE id = ?",
                    (command.preparation or "observe", encounter_id),
                )
                summaries.extend(self._run_until_player(connection, encounter_id, {}))
                status = self._encounter_status(connection, encounter_id)
                if status != "active":
                    summaries.extend(self._finalize_encounter(connection, encounter_id))
                turn_number = self._next_campaign_turn(connection, campaign_id)
                self._append_messages(
                    connection, campaign_id, turn_number,
                    (("player", self._command_text(command, connection, encounter_id)),
                     *(("combat", summary) for summary in summaries)),
                )
                for summary in summaries:
                    self._append_event(connection, campaign_id, summary)
                self._refresh_narrative_prompt(
                    connection, campaign_id, active=status == "active"
                )
                return CombatActionResult(encounter_id, status, tuple(summaries))
            actor = self._current_actor(connection, encounter_id)
            if str(actor["side"]) != "player":
                raise CombatError("The player cannot act during an enemy turn.")
            connection.execute(
                "DELETE FROM combat_conditions WHERE combatant_id = ? AND name = 'Guarded'",
                (actor["id"],),
            )
            player_summary = self._apply_player_action(
                connection, encounter, actor, command
            )
            skill_check = self._player_skill_check(
                connection, encounter_id, str(actor["id"]), command
            )
            summaries = [player_summary]
            narration_segments: tuple[NarrativeSegment, ...] = ()
            if self._encounter_status(connection, encounter_id) == "active":
                summaries.extend(self._advance_pointer(connection, encounter_id))
                allowed = self._allowed_enemy_intents(connection, encounter_id)
                intents: dict[str, str] = {}
                if narrator is not None and allowed:
                    try:
                        narration = narrator.resolve_combat_turn(
                            context=self._narration_context(
                                connection, encounter_id, player_summary
                            ),
                            allowed_intents=allowed,
                        )
                        narration_segments = narration.narrative_segments
                        intents = {
                            combatant_id: intent
                            for combatant_id, intent in narration.enemy_intents.items()
                            if intent in allowed.get(combatant_id, ())
                        }
                    except Exception:
                        narration_segments = ()
                        intents = {}
                summaries.extend(
                    self._run_until_player(connection, encounter_id, intents)
                )
            status = self._encounter_status(connection, encounter_id)
            if status != "active":
                summaries.extend(self._finalize_encounter(connection, encounter_id))
            action_text = self._command_text(command, connection, encounter_id)
            turn_number = self._next_campaign_turn(connection, campaign_id)
            messages: list[tuple[str, str]] = [("player", action_text)]
            messages.extend((segment.kind, segment.text) for segment in narration_segments)
            messages.extend(("combat", summary) for summary in summaries)
            self._append_messages(connection, campaign_id, turn_number, tuple(messages))
            for summary in summaries:
                self._append_event(connection, campaign_id, summary)
            self._refresh_narrative_prompt(
                connection, campaign_id, active=status == "active"
            )
            connection.execute(
                "UPDATE combat_encounters SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (encounter_id,),
            )
        return CombatActionResult(
            encounter_id, status, tuple(summaries), skill_check=skill_check
        )

    @staticmethod
    def _player_skill_check(
        connection: sqlite3.Connection,
        encounter_id: str,
        actor_id: str,
        command: CombatCommand,
    ) -> SkillCheckResult | None:
        if command.action not in {CombatAction.NEGOTIATE, CombatAction.FLEE}:
            return None
        row = connection.execute(
            "SELECT d20_roll, modifier, total, target_number FROM combat_turns "
            "WHERE encounter_id = ? AND actor_id = ? AND target_number IS NOT NULL "
            "ORDER BY sequence DESC LIMIT 1",
            (encounter_id, actor_id),
        ).fetchone()
        if row is None:
            return None
        name = "Negotiation" if command.action is CombatAction.NEGOTIATE else "Survival"
        total = int(row["total"])
        target = int(row["target_number"])
        return SkillCheckResult(
            name=name,
            roll=int(row["d20_roll"]),
            modifier=int(row["modifier"]),
            total=total,
            target=target,
            success=total >= target,
        )

    def _apply_preparation(
        self,
        connection: sqlite3.Connection,
        encounter: sqlite3.Row,
        preparation: str | None,
    ) -> str:
        choice = (preparation or "observe").casefold()
        player = connection.execute(
            "SELECT * FROM combatants WHERE encounter_id = ? AND side = 'player' LIMIT 1",
            (encounter["id"],),
        ).fetchone()
        if player is None:
            raise CombatError("The encounter has no player combatant.")
        if choice == "take_cover":
            connection.execute(
                "UPDATE combatants SET cover_bonus = cover_bonus + 2 WHERE id = ?",
                (player["id"],),
            )
            summary = f"{player['name']} takes cover before the first exchange (+2 Armor from cover)."
        elif choice == "scout":
            connection.execute(
                """
                INSERT INTO combat_conditions(
                    id, combatant_id, name, description, attack_modifier,
                    remaining_rounds, source
                ) VALUES (?, ?, 'Prepared', 'Studied enemy movement.', 1, 2, 'preparation')
                ON CONFLICT(combatant_id, name) DO UPDATE SET
                    attack_modifier=1, remaining_rounds=2, source='preparation'
                """,
                (f"condition-{uuid4().hex}", player["id"]),
            )
            summary = f"{player['name']} scouts the opposition (+1 Attack for two rounds)."
        elif choice == "charge":
            connection.execute(
                "UPDATE combatants SET distance_feet = MAX(0, distance_feet - 15) "
                "WHERE encounter_id = ? AND side = 'enemy' AND status = 'active'",
                (encounter["id"],),
            )
            summary = f"{player['name']} charges forward, closing 15 feet before combat begins."
        else:
            raise CombatError("Choose Take Cover, Scout, or Charge.")
        self._log_turn(connection, encounter, player, None, "wait", summary)
        return summary

    def _player_snapshot(
        self, connection: sqlite3.Connection, campaign_id: str
    ) -> dict[str, Any]:
        character = connection.execute(
            "SELECT * FROM characters WHERE campaign_id = ? AND is_player = 1",
            (campaign_id,),
        ).fetchone()
        if character is None:
            raise CombatError("Combat requires a player character.")
        character_id = str(character["id"])
        health = connection.execute(
            "SELECT current_value, maximum_value FROM character_resources "
            "WHERE character_id = ? AND resource_type = 'health'",
            (character_id,),
        ).fetchone()
        if health is None or int(health["current_value"]) <= 0:
            raise CombatError("The player must have health remaining to enter combat.")
        attributes = {
            str(row["name"]).lower(): int(row["modifier"])
            for row in connection.execute(
                "SELECT name, modifier FROM character_attributes WHERE character_id = ?",
                (character_id,),
            )
        }
        skills = {
            str(row["name"]).lower(): int(row["bonus"])
            for row in connection.execute(
                "SELECT name, bonus FROM skills WHERE character_id = ?",
                (character_id,),
            )
        }
        equipment = connection.execute(
            "SELECT equipment_slots.*, inventory_items.damage_text, "
            "inventory_items.armor_value FROM equipment_slots "
            "LEFT JOIN inventory_items ON inventory_items.id = equipment_slots.inventory_item_id "
            "WHERE equipment_slots.character_id = ?",
            (character_id,),
        ).fetchall()
        by_slot = {str(row["slot_name"]).lower(): row for row in equipment}
        weapon_row = by_slot.get("main hand")
        weapon_name = (
            "Unarmed Strike"
            if weapon_row is None or weapon_row["item_name"] is None
            else str(weapon_row["item_name"])
        )
        dice_count, die_size, attack_range = WEAPON_PROFILES.get(
            weapon_name.casefold(), (1, 4, 5)
        )
        if weapon_row is not None and weapon_row["damage_text"]:
            match = re.match(r"(\d+)d(\d+)", str(weapon_row["damage_text"]))
            if match:
                dice_count, die_size = int(match.group(1)), int(match.group(2))
        return {
            "character_id": character_id,
            "name": str(character["name"]),
            "side": "player",
            "current_health": int(health["current_value"]),
            "maximum_health": int(health["maximum_value"]),
            "armor_class": 10 + attributes.get("dexterity", 0) + int(character["equipment_armor_bonus"]),
            "attack_bonus": (
                attributes.get("strength", 0)
                + skills.get("attack", 0)
                + proficiency_bonus(int(character["level"]))
                + int(character["equipment_attack_bonus"])
            ),
            "damage_dice_count": dice_count,
            "damage_die_size": die_size,
            "damage_bonus": max(0, attributes.get("strength", 0)),
            "initiative_modifier": attributes.get("dexterity", 0),
            "distance_feet": 0,
            "movement_feet": 15,
            "attack_range_feet": attack_range,
            "cover_bonus": 0,
            "morale": 100,
            "intelligence": "player-controlled",
            "weapon_name": weapon_name,
            "weapon_item_id": None if weapon_row is None else weapon_row["inventory_item_id"],
        }

    def _apply_player_action(
        self,
        connection: sqlite3.Connection,
        encounter: sqlite3.Row,
        actor: sqlite3.Row,
        command: CombatCommand,
    ) -> str:
        encounter_id = str(encounter["id"])
        if command.action is CombatAction.ATTACK:
            target = self._enemy_target(connection, encounter_id, command.target_id)
            return self._attack(connection, encounter, actor, target)
        if command.action in {CombatAction.ABILITY, CombatAction.SPELL}:
            if command.ability_key:
                return self._apply_catalog_action(
                    connection, encounter, actor, command.ability_key,
                    expected_kind=command.action.value,
                    target_id=command.target_id,
                )
            target = self._enemy_target(connection, encounter_id, command.target_id)
            stamina = connection.execute(
                "SELECT * FROM character_resources WHERE character_id = ? "
                "AND resource_type = 'stamina'",
                (actor["character_id"],),
            ).fetchone()
            if stamina is None or int(stamina["current_value"]) < 5:
                raise CombatError("Power Strike requires 5 stamina.")
            connection.execute(
                "UPDATE character_resources SET current_value = current_value - 5 "
                "WHERE id = ?",
                (stamina["id"],),
            )
            return self._attack(
                connection,
                encounter,
                actor,
                target,
                action_type="ability",
                attack_bonus_extra=1,
                damage_bonus_extra=2,
                technique="Power Strike",
            )
        if command.action is CombatAction.ADVANCE:
            enemies = connection.execute(
                "SELECT * FROM combatants WHERE encounter_id = ? "
                "AND side = 'enemy' AND status = 'active'",
                (encounter_id,),
            ).fetchall()
            if not enemies or all(int(row["distance_feet"]) == 0 for row in enemies):
                raise CombatError("There is no remaining distance to close.")
            movement = int(actor["movement_feet"])
            connection.execute(
                "UPDATE combatants SET distance_feet = MAX(0, distance_feet - ?) "
                "WHERE encounter_id = ? AND side = 'enemy' AND status = 'active'",
                (movement, encounter_id),
            )
            summary = f"{actor['name']} advances {movement} feet toward the enemies."
            self._log_turn(connection, encounter, actor, None, "advance", summary)
            return summary
        if command.action is CombatAction.DEFEND:
            connection.execute(
                """
                INSERT INTO combat_conditions(
                    id, combatant_id, name, description, armor_modifier,
                    remaining_rounds, source
                ) VALUES (?, ?, 'Guarded', 'Focused on defense.', 2, 1, 'defend')
                ON CONFLICT(combatant_id, name) DO UPDATE SET
                    description = excluded.description,
                    armor_modifier = excluded.armor_modifier,
                    remaining_rounds = excluded.remaining_rounds,
                    source = excluded.source
                """,
                (f"condition-{uuid4().hex}", actor["id"]),
            )
            summary = f"{actor['name']} takes a guarded stance (+2 Armor until the next turn)."
            self._log_turn(connection, encounter, actor, None, "defend", summary)
            return summary
        if command.action is CombatAction.USE_ITEM:
            return self._use_combat_item(connection, encounter, actor, command.item_id)
        if command.action is CombatAction.NEGOTIATE:
            target = self._enemy_target(connection, encounter_id, command.target_id)
            charisma = connection.execute(
                "SELECT modifier FROM character_attributes WHERE character_id = ? "
                "AND lower(name) = 'charisma'",
                (actor["character_id"],),
            ).fetchone()
            modifier = 0 if charisma is None else int(charisma["modifier"])
            die = self.roll(1, 20)
            total = die + modifier
            difficulty = 10 + max(0, int(target["morale"]) // 20)
            success = total >= difficulty
            if success:
                connection.execute(
                    "UPDATE combatants SET status = 'surrendered', "
                    "declared_intent = 'surrender' WHERE id = ?",
                    (target["id"],),
                )
            summary = (
                f"{actor['name']} convinces {target['name']} to surrender "
                f"(Negotiation {die} + {modifier} = {total} vs {difficulty})."
                if success else
                f"{target['name']} rejects {actor['name']}'s terms "
                f"(Negotiation {die} + {modifier} = {total} vs {difficulty})."
            )
            self._log_turn(
                connection, encounter, actor, target,
                "surrender" if success else "wait", summary,
                d20=die, modifier=modifier, total=total,
                target_number=difficulty,
            )
            self._check_encounter_end(connection, encounter_id)
            return summary
        if command.action is CombatAction.FLEE:
            skill = connection.execute(
                "SELECT bonus FROM skills WHERE character_id = ? AND lower(name) = 'survival'",
                (actor["character_id"],),
            ).fetchone()
            modifier = 0 if skill is None else int(skill["bonus"])
            die = self.roll(1, 20)
            total = die + modifier
            success = total >= 12
            summary = (
                f"{actor['name']} escapes the encounter (Flee {die} + {modifier} = {total} vs 12)."
                if success
                else f"{actor['name']} cannot escape (Flee {die} + {modifier} = {total} vs 12)."
            )
            self._log_turn(
                connection, encounter, actor, None, "flee", summary,
                d20=die, modifier=modifier, total=total, target_number=12,
            )
            if success:
                self._end_encounter(connection, encounter_id, "escaped", "The player escaped.")
            return summary
        raise CombatError("Unsupported combat action.")

    def ensure_character_combat_catalog(
        self, connection: sqlite3.Connection, campaign_id: str
    ) -> None:
        character = connection.execute(
            "SELECT id, character_class, level FROM characters "
            "WHERE campaign_id = ? AND is_player = 1",
            (campaign_id,),
        ).fetchone()
        if character is None:
            raise CombatError("Combat requires a player character.")
        sync_character_combat_catalog(
            connection,
            str(character["id"]),
            character_class=str(character["character_class"]),
            level=int(character["level"]),
        )

    def _apply_catalog_action(
        self,
        connection: sqlite3.Connection,
        encounter: sqlite3.Row,
        actor: sqlite3.Row,
        ability_key: str,
        *,
        expected_kind: str,
        target_id: str | None,
    ) -> str:
        definition = CATALOG.get(ability_key)
        if definition is None or definition.kind != expected_kind:
            raise CombatError("The selected combat action is not available.")
        ability = connection.execute(
            "SELECT * FROM abilities WHERE character_id = ? AND action_key = ? "
            "AND unlocked = 1",
            (actor["character_id"], ability_key),
        ).fetchone()
        if ability is None:
            raise CombatError(f"{definition.name} is not available to this class.")
        if definition.is_cantrip:
            character = connection.execute(
                "SELECT level FROM characters WHERE id = ?",
                (actor["character_id"],),
            ).fetchone()
            definition = scaled_definition(
                definition, 1 if character is None else int(character["level"])
            )
        if definition.required_weapon == "ranged" and int(actor["attack_range_feet"]) <= 10:
            raise CombatError(f"{definition.name} requires an equipped ranged weapon.")
        if int(ability["cooldown_remaining"]) > 0:
            raise CombatError(
                f"{definition.name} is unavailable for "
                f"{ability['cooldown_remaining']} more round(s)."
            )
        if ability["current_uses"] is not None and int(ability["current_uses"]) <= 0:
            raise CombatError(f"{definition.name} has no uses remaining before a rest.")
        resource = connection.execute(
            "SELECT * FROM character_resources WHERE character_id = ? "
            "AND resource_type = ?",
            (actor["character_id"], definition.resource_type),
        ).fetchone()
        if definition.resource_cost:
            if resource is None or int(resource["current_value"]) < definition.resource_cost:
                raise CombatError(
                    f"{definition.name} requires {definition.resource_cost} "
                    f"{definition.resource_type.replace('_', ' ')}."
                )
        slots = None
        if definition.spell_slot_cost:
            slots = connection.execute(
                "SELECT * FROM character_resources WHERE character_id = ? "
                "AND resource_type = 'spell_slots'",
                (actor["character_id"],),
            ).fetchone()
            if slots is None or int(slots["current_value"]) < definition.spell_slot_cost:
                raise CombatError(f"{definition.name} requires a spell slot.")

        encounter_id = str(encounter["id"])
        target = None
        if definition.target == "enemy":
            target = self._enemy_target(connection, encounter_id, target_id)
            if int(target["distance_feet"]) > definition.range_feet:
                raise CombatError(
                    f"{target['name']} is {target['distance_feet']} feet away; "
                    f"{definition.name} reaches {definition.range_feet} feet."
                )
        elif definition.target == "all_enemies":
            targets = connection.execute(
                "SELECT * FROM combatants WHERE encounter_id = ? AND side = 'enemy' "
                "AND status = 'active' AND distance_feet <= ? ORDER BY display_order",
                (encounter_id, definition.range_feet),
            ).fetchall()
            if not targets:
                raise CombatError(f"No active enemy is within {definition.range_feet} feet.")

        if resource is not None and definition.resource_cost:
            connection.execute(
                "UPDATE character_resources SET current_value = current_value - ? WHERE id = ?",
                (definition.resource_cost, resource["id"]),
            )
        if slots is not None:
            connection.execute(
                "UPDATE character_resources SET current_value = current_value - ? WHERE id = ?",
                (definition.spell_slot_cost, slots["id"]),
            )
        connection.execute(
            "UPDATE abilities SET cooldown_remaining = ?, "
            "current_uses = CASE WHEN current_uses IS NULL THEN NULL ELSE current_uses - 1 END "
            "WHERE id = ?",
            (definition.cooldown_rounds, ability["id"]),
        )

        if definition.effect == "weapon_attack":
            assert target is not None
            return self._attack(
                connection, encounter, actor, target,
                action_type=definition.kind,
                attack_bonus_extra=definition.attack_bonus,
                damage_bonus_extra=definition.bonus,
                damage_dice_override=(definition.dice_count, definition.die_size)
                if definition.dice_count > 1 else None,
                technique=definition.name,
                action_key=definition.key,
            )
        if definition.effect == "spell_attack":
            assert target is not None
            return self._spell_attack(connection, encounter, actor, target, definition)
        if definition.effect in {"direct_damage", "damage_condition"}:
            assert target is not None
            damage = self._roll_effect_damage(definition)
            save_roll: int | None = None
            save_modifier = 0
            save_total: int | None = None
            saved = False
            if definition.save_type:
                save_roll, save_modifier, save_total = self._saving_throw(
                    target, definition.save_type
                )
                saved = save_total >= definition.save_dc
                if saved:
                    damage = damage // 2 if definition.save_half else 0
            damage = self._adjust_damage_for_traits(target, damage, definition.damage_type)
            remaining = self._apply_damage(connection, target, damage)
            if definition.effect == "damage_condition" and remaining > 0 and not saved:
                self._add_combat_condition(connection, target, definition)
            save_text = (
                f" {definition.save_type} save {save_roll} + {save_modifier} = "
                f"{save_total} vs {definition.save_dc}: "
                f"{'success' if saved else 'failure'}."
                if save_roll is not None else ""
            )
            summary = (
                f"{actor['name']} uses {definition.name} on {target['name']} for "
                f"{damage} damage; {remaining}/{target['maximum_health']} HP remains."
                f"{save_text}"
            )
            self._log_turn(
                connection, encounter, actor, target, definition.kind, summary,
                d20=save_roll, modifier=save_modifier, total=save_total,
                target_number=definition.save_dc if save_roll is not None else None,
                damage=damage, action_key=definition.key,
            )
        elif definition.effect == "area_damage":
            affected: list[str] = []
            total_damage = 0
            if definition.required_weapon == "ranged":
                for _enemy in targets:
                    self._consume_ammunition(connection, actor)
            for enemy in targets:
                damage = self._roll_effect_damage(definition)
                damage = self._adjust_damage_for_traits(
                    enemy, damage, definition.damage_type
                )
                remaining = self._apply_damage(connection, enemy, damage)
                total_damage += damage
                affected.append(f"{enemy['name']} {damage} ({remaining} HP)")
            summary = f"{actor['name']} uses {definition.name}: " + "; ".join(affected) + "."
            self._log_turn(
                connection, encounter, actor, None, definition.kind, summary,
                damage=total_damage, action_key=definition.key,
            )
        elif definition.effect == "heal":
            healing = self._roll_effect_damage(definition)
            restored = min(healing, int(actor["maximum_health"]) - int(actor["current_health"]))
            if restored <= 0:
                raise CombatError("Health is already full.")
            new_health = int(actor["current_health"]) + restored
            connection.execute(
                "UPDATE combatants SET current_health = ? WHERE id = ?",
                (new_health, actor["id"]),
            )
            self._sync_player_health(connection, actor, new_health)
            summary = (
                f"{actor['name']} uses {definition.name} and restores {restored} health "
                f"({new_health}/{actor['maximum_health']} HP)."
            )
            self._log_turn(
                connection, encounter, actor, actor, definition.kind, summary,
                healing=restored, action_key=definition.key,
            )
        elif definition.effect == "buff":
            self._add_combat_condition(connection, actor, definition)
            summary = (
                f"{actor['name']} uses {definition.name} and gains "
                f"{definition.condition_name} for {definition.condition_rounds} rounds."
            )
            self._log_turn(
                connection, encounter, actor, actor, definition.kind, summary,
                action_key=definition.key,
            )
        else:
            raise CombatError("The selected combat effect is not implemented.")
        self._check_encounter_end(connection, encounter_id)
        return summary

    def _spell_attack(
        self,
        connection: sqlite3.Connection,
        encounter: sqlite3.Row,
        actor: sqlite3.Row,
        target: sqlite3.Row,
        definition: CombatAbilityDefinition,
    ) -> str:
        magic = connection.execute(
            "SELECT bonus FROM skills WHERE character_id = ? AND lower(name) = 'magic'",
            (actor["character_id"],),
        ).fetchone()
        character = connection.execute(
            "SELECT level FROM characters WHERE id = ?",
            (actor["character_id"],),
        ).fetchone()
        modifier = (
            (0 if magic is None else int(magic["bonus"]))
            + proficiency_bonus(1 if character is None else int(character["level"]))
            + definition.attack_bonus
        )
        armor = int(target["armor_class"]) + int(target["cover_bonus"])
        die = self.roll(1, 20)
        total = die + modifier
        hit = die == 20 or (die != 1 and total >= armor)
        damage = self._roll_effect_damage(definition, critical=die == 20) if hit else 0
        damage = self._adjust_damage_for_traits(target, damage, definition.damage_type)
        remaining = self._apply_damage(connection, target, damage) if hit else int(target["current_health"])
        summary = (
            f"{actor['name']} casts {definition.name} and hits {target['name']} "
            f"({die} + {modifier} = {total} vs AC {armor}) for {damage} damage; "
            f"{remaining}/{target['maximum_health']} HP remains."
            if hit else
            f"{actor['name']} casts {definition.name}, but misses {target['name']} "
            f"({die} + {modifier} = {total} vs AC {armor})."
        )
        self._log_turn(
            connection, encounter, actor, target, "spell", summary, d20=die,
            modifier=modifier, total=total, target_number=armor, damage=damage,
            action_key=definition.key,
        )
        self._check_encounter_end(connection, str(encounter["id"]))
        return summary

    def _roll_effect_damage(
        self, definition: CombatAbilityDefinition, *, critical: bool = False
    ) -> int:
        count = definition.dice_count * (2 if critical else 1)
        return max(0, sum(self.roll(1, definition.die_size) for _ in range(count)) + definition.bonus)

    def _saving_throw(
        self, target: sqlite3.Row, save_type: str
    ) -> tuple[int, int, int]:
        normalized = save_type.casefold()
        if normalized == "dexterity":
            modifier = int(target["initiative_modifier"])
        elif normalized == "strength":
            modifier = int(target["attack_bonus"])
        elif normalized == "constitution":
            modifier = int(target["damage_bonus"])
        elif normalized == "wisdom":
            modifier = max(-2, min(2, (int(target["morale"]) - 50) // 20))
        else:
            modifier = 0
        die = self.roll(1, 20)
        return die, modifier, die + modifier

    def _apply_damage(
        self, connection: sqlite3.Connection, target: sqlite3.Row, damage: int
    ) -> int:
        remaining = max(0, int(target["current_health"]) - damage)
        connection.execute(
            "UPDATE combatants SET current_health = ?, status = ? WHERE id = ?",
            (remaining, "defeated" if remaining == 0 else "active", target["id"]),
        )
        if str(target["side"]) == "player":
            self._sync_player_health(connection, target, remaining)
            self._apply_low_health_warning(connection, target, remaining)
        return remaining

    @staticmethod
    def _adjust_damage_for_traits(
        target: sqlite3.Row, damage: int, damage_type: str
    ) -> int:
        if damage <= 0:
            return 0
        try:
            resistances = {
                str(value).casefold()
                for value in json.loads(str(target["resistances_json"]))
            }
            vulnerabilities = {
                str(value).casefold()
                for value in json.loads(str(target["vulnerabilities_json"]))
            }
        except (json.JSONDecodeError, TypeError, IndexError):
            return damage
        normalized = damage_type.casefold()
        if normalized in vulnerabilities:
            return damage * 2
        if normalized in resistances:
            return max(1, damage // 2)
        return damage

    @staticmethod
    def _add_combat_condition(
        connection: sqlite3.Connection,
        target: sqlite3.Row,
        definition: CombatAbilityDefinition,
    ) -> None:
        connection.execute(
            """
            INSERT INTO combat_conditions(
                id, combatant_id, name, description, armor_modifier,
                attack_modifier, remaining_rounds, source, damage_per_round
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(combatant_id, name) DO UPDATE SET
                description = excluded.description,
                armor_modifier = excluded.armor_modifier,
                attack_modifier = excluded.attack_modifier,
                remaining_rounds = excluded.remaining_rounds,
                source = excluded.source,
                damage_per_round = excluded.damage_per_round
            """,
            (
                f"condition-{uuid4().hex}", target["id"], definition.condition_name,
                definition.description, definition.armor_modifier,
                definition.attack_modifier, definition.condition_rounds,
                definition.name, definition.damage_per_round,
            ),
        )

    def _recover_after_combat(
        self, connection: sqlite3.Connection, campaign_id: str
    ) -> CombatActionResult:
        active = connection.execute(
            "SELECT 1 FROM combat_encounters WHERE campaign_id = ? AND status = 'active'",
            (campaign_id,),
        ).fetchone()
        if active is not None:
            raise CombatError("Rest is unavailable during an active encounter.")
        character = connection.execute(
            "SELECT id FROM characters WHERE campaign_id = ? AND is_player = 1",
            (campaign_id,),
        ).fetchone()
        if character is None:
            raise CombatError("Rest requires a player character.")
        character_id = str(character["id"])
        self.ensure_character_combat_catalog(connection, campaign_id)
        connection.execute(
            """
            UPDATE character_resources
            SET current_value = CASE
                WHEN resource_type IN ('spell_slots') THEN maximum_value
                WHEN resource_type IN ('health', 'stamina', 'focus', 'mana')
                    THEN MIN(maximum_value, current_value + MAX(1, maximum_value / 2))
                ELSE current_value END
            WHERE character_id = ?
            """,
            (character_id,),
        )
        connection.execute(
            "UPDATE abilities SET cooldown_remaining = 0, current_uses = maximum_uses "
            "WHERE character_id = ?",
            (character_id,),
        )
        turn_number = self._next_campaign_turn(connection, campaign_id)
        summary = "The party completes a short rest; combat resources and limited uses recover."
        self._append_messages(
            connection, campaign_id, turn_number,
            (("player", "Take a short rest"), ("system", summary)),
        )
        self._append_event(connection, campaign_id, summary)
        latest = connection.execute(
            "SELECT id, status FROM combat_encounters WHERE campaign_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (campaign_id,),
        ).fetchone()
        return CombatActionResult(
            "rest" if latest is None else str(latest["id"]),
            "resolved" if latest is None else str(latest["status"]),
            (summary,),
        )

    def _attack(
        self,
        connection: sqlite3.Connection,
        encounter: sqlite3.Row,
        actor: sqlite3.Row,
        target: sqlite3.Row,
        *,
        action_type: str = "attack",
        attack_bonus_extra: int = 0,
        damage_bonus_extra: int = 0,
        damage_dice_override: tuple[int, int] | None = None,
        technique: str = "",
        action_key: str = "",
        range_override: int | None = None,
    ) -> str:
        attack_range = int(actor["attack_range_feet"]) if range_override is None else range_override
        if int(target["distance_feet"]) > attack_range:
            raise CombatError(
                f"{target['name']} is {target['distance_feet']} feet away; "
                f"{technique or actor['weapon_name']} reaches {attack_range} feet."
            )
        if str(actor["side"]) == "player":
            self._consume_ammunition(connection, actor)
        attack_modifier = int(actor["attack_bonus"]) + attack_bonus_extra + self._condition_modifier(
            connection, str(actor["id"]), "attack_modifier"
        )
        armor = int(target["armor_class"]) + int(target["cover_bonus"]) + self._condition_modifier(
            connection, str(target["id"]), "armor_modifier"
        )
        die = self.roll(1, 20)
        total = die + attack_modifier
        hit = die == 20 or (die != 1 and total >= armor)
        damage = 0
        if hit:
            base_count, die_size = damage_dice_override or (
                int(actor["damage_dice_count"]), int(actor["damage_die_size"])
            )
            dice_count = base_count * (2 if die == 20 else 1)
            damage = sum(
                self.roll(1, die_size) for _ in range(dice_count)
            ) + int(actor["damage_bonus"]) + damage_bonus_extra
            damage = max(0, damage)
            damage = self._adjust_damage_for_traits(target, damage, "physical")
            remaining = max(0, int(target["current_health"]) - damage)
            status = "defeated" if remaining == 0 else "active"
            connection.execute(
                "UPDATE combatants SET current_health = ?, status = ? WHERE id = ?",
                (remaining, status, target["id"]),
            )
            if str(target["side"]) == "player":
                self._sync_player_health(connection, target, remaining)
                self._apply_low_health_warning(connection, target, remaining)
            if str(actor["side"]) == "player" and actor["weapon_item_id"] is not None:
                connection.execute(
                    "UPDATE inventory_items SET durability = MAX(0, durability - 1) "
                    "WHERE id = ? AND durability IS NOT NULL",
                    (actor["weapon_item_id"],),
                )
                connection.execute(
                    """
                    UPDATE equipment_slots
                    SET condition = COALESCE((
                        SELECT CAST(durability AS TEXT) || '%'
                        FROM inventory_items
                        WHERE inventory_items.id = equipment_slots.inventory_item_id
                    ), condition)
                    WHERE inventory_item_id = ?
                    """,
                    (actor["weapon_item_id"],),
                )
            critical = " critical" if die == 20 else ""
            technique_text = f" using {technique}" if technique else ""
            summary = (
                f"{actor['name']} lands a{critical} hit on {target['name']}{technique_text} with "
                f"{actor['weapon_name']} ({die} + {attack_modifier} = {total} vs AC {armor}) "
                f"for {damage} damage; {remaining}/{target['maximum_health']} HP remains."
            )
        else:
            technique_text = f" using {technique}" if technique else ""
            summary = (
                f"{actor['name']} misses {target['name']}{technique_text} with {actor['weapon_name']} "
                f"({die} + {attack_modifier} = {total} vs AC {armor})."
            )
        self._log_turn(
            connection, encounter, actor, target, action_type, summary,
            d20=die, modifier=attack_modifier, total=total,
            target_number=armor, damage=damage, action_key=action_key,
        )
        self._check_encounter_end(connection, str(encounter["id"]))
        return summary

    @staticmethod
    def _consume_ammunition(
        connection: sqlite3.Connection, actor: sqlite3.Row
    ) -> None:
        weapon = str(actor["weapon_name"]).casefold()
        ammunition = None
        if "crossbow" in weapon:
            ammunition = "bolts"
        elif "bow" in weapon:
            ammunition = "arrows"
        elif "sling" in weapon:
            ammunition = "sling stones"
        if ammunition is None:
            return
        item = connection.execute(
            "SELECT inventory_items.* FROM inventory_items "
            "JOIN equipment_slots ON equipment_slots.inventory_item_id = inventory_items.id "
            "WHERE inventory_items.character_id = ? AND lower(inventory_items.name) = ? "
            "AND lower(equipment_slots.slot_name) = 'ammunition' "
            "ORDER BY inventory_items.slot_index LIMIT 1",
            (actor["character_id"], ammunition),
        ).fetchone()
        if item is None:
            raise CombatError(
                f"{actor['weapon_name']} requires equipped {ammunition.title()}."
            )
        remaining = int(item["quantity"]) - 1
        if remaining <= 0:
            connection.execute(
                "UPDATE equipment_slots SET item_name = NULL, condition = '', "
                "inventory_item_id = NULL WHERE inventory_item_id = ?",
                (item["id"],),
            )
            connection.execute("DELETE FROM inventory_items WHERE id = ?", (item["id"],))
        else:
            connection.execute(
                "UPDATE inventory_items SET quantity = ? WHERE id = ?",
                (remaining, item["id"]),
            )

    def _run_until_player(
        self,
        connection: sqlite3.Connection,
        encounter_id: str,
        intents: dict[str, str],
    ) -> list[str]:
        summaries: list[str] = []
        guard = 0
        while self._encounter_status(connection, encounter_id) == "active":
            guard += 1
            if guard > 30:
                raise CombatError("Combat initiative could not advance safely.")
            encounter = connection.execute(
                "SELECT * FROM combat_encounters WHERE id = ?", (encounter_id,)
            ).fetchone()
            assert encounter is not None
            actor = self._current_actor(connection, encounter_id)
            if str(actor["side"]) == "player":
                break
            if str(actor["status"]) != "active":
                summaries.extend(self._advance_pointer(connection, encounter_id))
                continue
            connection.execute(
                "DELETE FROM combat_conditions WHERE combatant_id = ? AND name = 'Guarded'",
                (actor["id"],),
            )
            allowed = self._allowed_intents_for(connection, actor)
            intent = intents.get(str(actor["id"]))
            if intent not in allowed:
                intent = allowed[0]
            connection.execute(
                "UPDATE combatants SET declared_intent = ? WHERE id = ?",
                (intent, actor["id"]),
            )
            if intent == "attack":
                target = connection.execute(
                    "SELECT * FROM combatants WHERE encounter_id = ? "
                    "AND side = 'player' AND status = 'active' LIMIT 1",
                    (encounter_id,),
                ).fetchone()
                if target is None:
                    self._check_encounter_end(connection, encounter_id)
                    break
                summaries.append(self._attack(connection, encounter, actor, target))
            elif intent == "ability":
                summaries.append(
                    self._use_enemy_ability(connection, encounter, actor)
                )
            elif intent == "advance":
                movement = int(actor["movement_feet"])
                remaining = max(0, int(actor["distance_feet"]) - movement)
                connection.execute(
                    "UPDATE combatants SET distance_feet = ? WHERE id = ?",
                    (remaining, actor["id"]),
                )
                summary = f"{actor['name']} advances {movement} feet and is now {remaining} feet away."
                self._log_turn(connection, encounter, actor, None, "advance", summary)
                summaries.append(summary)
            elif intent == "defend":
                connection.execute(
                    """
                    INSERT INTO combat_conditions(
                        id, combatant_id, name, description, armor_modifier,
                        remaining_rounds, source
                    ) VALUES (?, ?, 'Guarded', 'Focused on defense.', 2, 1, 'enemy defend')
                    ON CONFLICT(combatant_id, name) DO UPDATE SET
                        armor_modifier = 2, remaining_rounds = 1,
                        source = 'enemy defend'
                    """,
                    (f"condition-{uuid4().hex}", actor["id"]),
                )
                summary = f"{actor['name']} braces defensively (+2 Armor)."
                self._log_turn(connection, encounter, actor, None, "defend", summary)
                summaries.append(summary)
            else:
                status = "retreated" if intent == "retreat" else "surrendered"
                connection.execute(
                    "UPDATE combatants SET status = ?, declared_intent = ? WHERE id = ?",
                    (status, intent, actor["id"]),
                )
                verb = "retreats from the fight" if intent == "retreat" else "drops their weapon and surrenders"
                summary = f"{actor['name']} {verb}."
                self._log_turn(connection, encounter, actor, None, intent, summary)
                summaries.append(summary)
                self._check_encounter_end(connection, encounter_id)
            if self._encounter_status(connection, encounter_id) == "active":
                summaries.extend(self._advance_pointer(connection, encounter_id))
        return summaries

    def _allowed_enemy_intents(
        self, connection: sqlite3.Connection, encounter_id: str
    ) -> dict[str, tuple[str, ...]]:
        return {
            str(row["id"]): self._allowed_intents_for(connection, row)
            for row in connection.execute(
                "SELECT * FROM combatants WHERE encounter_id = ? "
                "AND side = 'enemy' AND status = 'active' ORDER BY display_order",
                (encounter_id,),
            )
        }

    def _allowed_intents_for(
        self, connection: sqlite3.Connection, actor: sqlite3.Row
    ) -> tuple[str, ...]:
        intents: list[str] = []
        health_ratio = int(actor["current_health"]) / int(actor["maximum_health"])
        if health_ratio <= 0.35 or int(actor["morale"]) <= 30:
            intents.extend(("retreat", "surrender"))
        try:
            abilities = json.loads(str(actor["abilities_json"]))
        except (json.JSONDecodeError, TypeError):
            abilities = []
        encounter = connection.execute(
            "SELECT round_number FROM combat_encounters WHERE id = ?",
            (actor["encounter_id"],),
        ).fetchone()
        if abilities and encounter is not None and int(encounter["round_number"]) % 2 == 0:
            intents.append("ability")
        if int(actor["distance_feet"]) <= int(actor["attack_range_feet"]):
            intents.append("attack")
        else:
            intents.append("advance")
        intents.append("defend")
        return tuple(intents)

    def _use_enemy_ability(
        self,
        connection: sqlite3.Connection,
        encounter: sqlite3.Row,
        actor: sqlite3.Row,
    ) -> str:
        try:
            keys = tuple(json.loads(str(actor["abilities_json"])))
        except (json.JSONDecodeError, TypeError):
            keys = ()
        choices = tuple(ENEMY_ABILITIES[key] for key in keys if key in ENEMY_ABILITIES)
        if not choices:
            target = connection.execute(
                "SELECT * FROM combatants WHERE encounter_id = ? AND side = 'player' "
                "AND status = 'active' LIMIT 1",
                (encounter["id"],),
            ).fetchone()
            if target is None:
                raise CombatError("Enemy ability has no valid target.")
            return self._attack(connection, encounter, actor, target)
        ability = choices[(int(encounter["round_number"]) - 1) % len(choices)]
        target = connection.execute(
            "SELECT * FROM combatants WHERE encounter_id = ? AND side = 'player' "
            "AND status = 'active' LIMIT 1",
            (encounter["id"],),
        ).fetchone()
        if target is None:
            raise CombatError("Enemy ability has no valid target.")
        if ability.kind in {"attack", "attack_condition"}:
            before = int(target["current_health"])
            summary = self._attack(
                connection, encounter, actor, target, action_type="ability",
                attack_bonus_extra=ability.attack_bonus,
                damage_bonus_extra=ability.damage_bonus,
                technique=ability.name,
                action_key=ability.key,
                range_override=ability.range_feet,
            )
            refreshed = connection.execute(
                "SELECT * FROM combatants WHERE id = ?", (target["id"],)
            ).fetchone()
            if (
                ability.kind == "attack_condition" and refreshed is not None
                and int(refreshed["current_health"]) < before
                and int(refreshed["current_health"]) > 0
            ):
                self._insert_enemy_condition(connection, refreshed, ability)
            return summary
        if ability.kind == "debuff":
            self._insert_enemy_condition(connection, target, ability)
            summary = f"{actor['name']} uses {ability.name}; {target['name']} gains {ability.condition_name}."
            self._log_turn(
                connection, encounter, actor, target, "ability", summary,
                action_key=ability.key,
            )
            return summary
        self._insert_enemy_condition(connection, actor, ability)
        summary = f"{actor['name']} uses {ability.name} and gains {ability.condition_name}."
        self._log_turn(
            connection, encounter, actor, actor, "ability", summary,
            action_key=ability.key,
        )
        return summary

    @staticmethod
    def _insert_enemy_condition(
        connection: sqlite3.Connection,
        target: sqlite3.Row,
        ability: Any,
    ) -> None:
        connection.execute(
            """
            INSERT INTO combat_conditions(
                id, combatant_id, name, description, armor_modifier,
                attack_modifier, remaining_rounds, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(combatant_id, name) DO UPDATE SET
                armor_modifier=excluded.armor_modifier,
                attack_modifier=excluded.attack_modifier,
                remaining_rounds=excluded.remaining_rounds,
                source=excluded.source
            """,
            (
                f"condition-{uuid4().hex}", target["id"], ability.condition_name,
                ability.description, ability.armor_modifier,
                ability.attack_modifier, ability.duration, ability.name,
            ),
        )

    def _use_combat_item(
        self,
        connection: sqlite3.Connection,
        encounter: sqlite3.Row,
        actor: sqlite3.Row,
        item_id: str | None,
    ) -> str:
        if item_id is None:
            item = connection.execute(
                "SELECT * FROM inventory_items WHERE character_id = ? "
                "AND lower(name) = 'health potion' ORDER BY slot_index LIMIT 1",
                (actor["character_id"],),
            ).fetchone()
        else:
            item = connection.execute(
                "SELECT * FROM inventory_items WHERE id = ? AND character_id = ?",
                (item_id, actor["character_id"]),
            ).fetchone()
        if item is None:
            raise CombatError("The selected combat item is not in the player's inventory.")
        try:
            effect = json.loads(str(item["use_effect_json"]))
        except json.JSONDecodeError as exc:
            raise CombatError("The selected item has invalid effect data.") from exc
        resources = effect.get("resources", {}) if isinstance(effect, dict) else {}
        healing = int(resources.get("health", 0)) if isinstance(resources, dict) else 0
        if healing <= 0:
            raise CombatError(f"{item['name']} cannot be used as a combat healing item.")
        current = int(actor["current_health"])
        maximum = int(actor["maximum_health"])
        restored = min(healing, maximum - current)
        if restored <= 0:
            raise CombatError("Health is already full.")
        remaining_quantity = int(item["quantity"]) - 1
        if remaining_quantity <= 0:
            connection.execute("DELETE FROM inventory_items WHERE id = ?", (item["id"],))
        else:
            connection.execute(
                "UPDATE inventory_items SET quantity = ? WHERE id = ?",
                (remaining_quantity, item["id"]),
            )
        new_health = current + restored
        connection.execute(
            "UPDATE combatants SET current_health = ? WHERE id = ?",
            (new_health, actor["id"]),
        )
        self._sync_player_health(connection, actor, new_health)
        summary = (
            f"{actor['name']} uses {item['name']} and restores {restored} health "
            f"({new_health}/{maximum} HP)."
        )
        self._log_turn(connection, encounter, actor, actor, "use_item", summary)
        return summary

    @staticmethod
    def _sync_player_health(
        connection: sqlite3.Connection, player: sqlite3.Row, value: int
    ) -> None:
        connection.execute(
            "UPDATE character_resources SET current_value = ? "
            "WHERE character_id = ? AND resource_type = 'health'",
            (value, player["character_id"]),
        )

    def _apply_low_health_warning(
        self, connection: sqlite3.Connection, player: sqlite3.Row, health: int
    ) -> None:
        if health > int(player["maximum_health"]) * 0.25 or health <= 0:
            return
        connection.execute(
            """
            INSERT INTO combat_conditions(
                id, combatant_id, name, description, remaining_rounds, source
            ) VALUES (?, ?, 'Critical Health', 'Health is at or below 25%.', NULL, 'damage')
            ON CONFLICT(combatant_id, name) DO NOTHING
            """,
            (f"condition-{uuid4().hex}", player["id"]),
        )

    def _check_encounter_end(
        self, connection: sqlite3.Connection, encounter_id: str
    ) -> None:
        player = connection.execute(
            "SELECT * FROM combatants WHERE encounter_id = ? AND side = 'player' LIMIT 1",
            (encounter_id,),
        ).fetchone()
        if player is None or int(player["current_health"]) == 0:
            if player is not None:
                connection.execute(
                    "UPDATE combatants SET status = 'defeated' WHERE id = ?",
                    (player["id"],),
                )
                connection.execute(
                    """
                    INSERT INTO status_effects(
                        id, character_id, name, description, remaining_turns, source
                    ) VALUES (?, ?, 'Unconscious', 'Reduced to zero health in combat.', NULL, 'combat')
                    """,
                    (f"status-{uuid4().hex}", player["character_id"]),
                )
            self._end_encounter(
                connection, encounter_id, "defeat", "The player was reduced to zero health."
            )
            return
        active_enemy = connection.execute(
            "SELECT 1 FROM combatants WHERE encounter_id = ? "
            "AND side = 'enemy' AND status = 'active' LIMIT 1",
            (encounter_id,),
        ).fetchone()
        if active_enemy is None:
            self._end_encounter(
                connection, encounter_id, "victory", "No hostile combatants remain."
            )

    @staticmethod
    def _end_encounter(
        connection: sqlite3.Connection,
        encounter_id: str,
        status: str,
        reason: str,
    ) -> None:
        connection.execute(
            "UPDATE combat_encounters SET status = ?, end_reason = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, reason, encounter_id),
        )

    def _finalize_encounter(
        self, connection: sqlite3.Connection, encounter_id: str
    ) -> list[str]:
        encounter = connection.execute(
            "SELECT * FROM combat_encounters WHERE id = ?", (encounter_id,)
        ).fetchone()
        if encounter is None or str(encounter["status"]) == "active":
            return []
        reward = connection.execute(
            "SELECT * FROM combat_rewards WHERE encounter_id = ?", (encounter_id,)
        ).fetchone()
        if reward is None:
            enemies = connection.execute(
                "SELECT * FROM combatants WHERE encounter_id = ? AND side = 'enemy'",
                (encounter_id,),
            ).fetchall()
            victory = str(encounter["status"]) == "victory"
            experience = max(50, sum(int(row["maximum_health"]) * 2 for row in enemies)) if victory else 0
            skill_experience = max(25, experience // 2) if victory else 0
            loot_names: list[str] = []
            catalog_rewards = {}
            currency = 0
            if victory:
                currency = max(10, sum(max(1, int(row["maximum_health"]) // 3) for row in enemies))
                for row in enemies:
                    key = str(row["archetype_key"])
                    archetype = archetype_by_key(key)
                    loot_names.extend(() if archetype is None else archetype.loot)
                currency += 5 * sum(1 for name in loot_names if name == "Gold")
                loot_names = [name for name in loot_names if name != "Gold"]
                if not loot_names:
                    loot_names.append("Health Potion")
                catalog_reward = select_loot(
                    f"combat:{encounter_id}:{len(enemies)}", count=1
                )[0]
                loot_names.append(catalog_reward.name)
                catalog_rewards[catalog_reward.name] = catalog_reward
            reward_id = f"reward-{uuid4().hex}"
            connection.execute(
                "INSERT INTO combat_rewards("
                "id, encounter_id, outcome, experience, skill_experience, currency"
                ") VALUES (?, ?, ?, ?, ?, ?)",
                (
                    reward_id, encounter_id, encounter["status"], experience,
                    skill_experience, currency,
                ),
            )
            quantities: dict[str, int] = {}
            for name in loot_names:
                quantities[name] = quantities.get(name, 0) + (10 if name == "Arrows" else 1)
            for name, quantity in quantities.items():
                catalog_reward = catalog_rewards.get(name)
                rarity = (
                    catalog_reward.rarity if catalog_reward is not None
                    else "uncommon" if name in {"Moonstone", "Antidote"} else "common"
                )
                description = (
                    catalog_reward.description if catalog_reward is not None
                    else f"Recovered after the encounter at {encounter['environment']}."
                )
                connection.execute(
                    "INSERT INTO combat_reward_items("
                    "id, reward_id, item_key, name, quantity, rarity, description"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"reward-item-{uuid4().hex}", reward_id,
                        name.casefold().replace(" ", "_"), name, quantity,
                        rarity, description,
                    ),
                )
            reward = connection.execute(
                "SELECT * FROM combat_rewards WHERE id = ?", (reward_id,)
            ).fetchone()
        assert reward is not None
        if bool(reward["progression_applied"]):
            return []
        if str(reward["outcome"]) != "victory":
            connection.execute(
                "UPDATE combat_rewards SET progression_applied = 1 WHERE id = ?",
                (reward["id"],),
            )
            return [f"Encounter ended: {reward['outcome']}. No rewards were awarded."]
        campaign_id = str(encounter["campaign_id"])
        character = connection.execute(
            "SELECT id, level FROM characters WHERE campaign_id = ? AND is_player = 1",
            (campaign_id,),
        ).fetchone()
        assert character is not None
        experience_amount = int(reward["experience"])
        skill_amount = int(reward["skill_experience"])
        currency_amount = int(reward["currency"])
        summaries = [
            f"Victory: {experience_amount} character XP, {skill_amount} Attack XP, "
            f"and {currency_amount} gold awarded."
        ]
        progression = award_character_experience(
            connection, str(character["id"]), experience_amount
        )
        summaries.extend(progression.summaries)
        skill = connection.execute(
            "SELECT * FROM skills WHERE character_id = ? AND lower(name) = 'attack'",
            (character["id"],),
        ).fetchone()
        if skill is not None:
            xp = int(skill["current_xp"]) + skill_amount
            threshold = int(skill["next_level_xp"])
            level = int(skill["level"])
            increased = 0
            while threshold > 0 and xp >= threshold:
                xp -= threshold
                level += 1
                threshold = max(threshold + 100, int(threshold * 1.15))
                increased = 1
                summaries.append(f"Attack increased to level {level}.")
            connection.execute(
                "UPDATE skills SET level = ?, current_xp = ?, next_level_xp = ?, "
                "recently_increased = ? WHERE id = ?",
                (level, xp, threshold, increased, skill["id"]),
            )
        connection.execute(
            "UPDATE characters SET currency = currency + ? WHERE id = ?",
            (currency_amount, character["id"]),
        )
        connection.execute(
            "UPDATE combat_rewards SET progression_applied = 1 WHERE id = ?",
            (reward["id"],),
        )
        for enemy in enemies:
            if str(enemy["status"]) not in {"defeated", "retreated", "surrendered"}:
                continue
            summaries.extend(
                progress_quests(
                    connection,
                    campaign_id,
                    "combat",
                    str(enemy["archetype_key"] or enemy["name"]),
                    detail=f"Defeated {enemy['name']} in combat.",
                )
            )
        return summaries

    def claim_reward_item(
        self, campaign_id: str, reward_item_id: str
    ) -> str:
        with self.database.transaction() as connection:
            return self._claim_reward_item(connection, campaign_id, reward_item_id)

    def claim_all_reward_items(
        self, campaign_id: str, reward_id: str
    ) -> tuple[tuple[str, ...], int]:
        claimed: list[str] = []
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT combat_reward_items.id FROM combat_reward_items "
                "JOIN combat_rewards ON combat_rewards.id = combat_reward_items.reward_id "
                "JOIN combat_encounters ON combat_encounters.id = combat_rewards.encounter_id "
                "WHERE combat_rewards.id = ? AND combat_encounters.campaign_id = ? "
                "AND combat_reward_items.claimed = 0 ORDER BY combat_reward_items.name",
                (reward_id, campaign_id),
            ).fetchall()
            for row in rows:
                try:
                    claimed.append(
                        self._claim_reward_item(connection, campaign_id, str(row["id"]))
                    )
                except CombatError as exc:
                    if "inventory is full" not in str(exc).lower():
                        raise
                    break
            remaining = int(
                connection.execute(
                    "SELECT COUNT(*) FROM combat_reward_items WHERE reward_id = ? AND claimed = 0",
                    (reward_id,),
                ).fetchone()[0]
            )
        return tuple(claimed), remaining

    def _claim_reward_item(
        self,
        connection: sqlite3.Connection,
        campaign_id: str,
        reward_item_id: str,
    ) -> str:
        row = connection.execute(
            """
            SELECT combat_reward_items.*, characters.id AS character_id,
                   characters.inventory_capacity
            FROM combat_reward_items
            JOIN combat_rewards ON combat_rewards.id = combat_reward_items.reward_id
            JOIN combat_encounters ON combat_encounters.id = combat_rewards.encounter_id
            JOIN characters ON characters.campaign_id = combat_encounters.campaign_id
                           AND characters.is_player = 1
            WHERE combat_reward_items.id = ? AND combat_encounters.campaign_id = ?
            """,
            (reward_item_id, campaign_id),
        ).fetchone()
        if row is None:
            raise CombatError("The selected reward is unavailable.")
        if bool(row["claimed"]):
            raise CombatError(f"{row['name']} was already claimed.")
        character_id = str(row["character_id"])
        existing = connection.execute(
            "SELECT id FROM inventory_items WHERE character_id = ? AND lower(name) = lower(?) "
            "AND item_type != 'equipment' AND inventory_position IS NOT NULL "
            "ORDER BY inventory_position LIMIT 1",
            (character_id, row["name"]),
        ).fetchone()
        if existing is not None:
            connection.execute(
                "UPDATE inventory_items SET quantity = quantity + ? WHERE id = ?",
                (row["quantity"], existing["id"]),
            )
        else:
            occupied = {
                int(item[0]) for item in connection.execute(
                    "SELECT inventory_position FROM inventory_items WHERE character_id = ? "
                    "AND inventory_position IS NOT NULL",
                    (character_id,),
                )
            }
            slot = next(
                (index for index in range(int(row["inventory_capacity"])) if index not in occupied),
                None,
            )
            if slot is None:
                raise CombatError("The inventory is full; this reward remains unclaimed.")
            legacy_slot = int(connection.execute(
                "SELECT COALESCE(MAX(slot_index), -1) + 1 FROM inventory_items WHERE character_id = ?",
                (character_id,),
            ).fetchone()[0])
            definition = item_definition(str(row["name"]))
            new_item_id = f"item-{uuid4().hex}"
            connection.execute(
                """
                INSERT INTO inventory_items(
                    id, character_id, slot_index, inventory_position, name, quantity, rarity,
                    description, item_type, consumable, charges, maximum_charges,
                    equip_slot, use_effect_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_item_id, character_id, legacy_slot, slot, row["name"],
                    row["quantity"], row["rarity"], row["description"],
                    definition.item_type, int(definition.consumable),
                    definition.charges, definition.maximum_charges,
                    definition.equip_slot, definition.effect_json(),
                ),
            )
            difficulty_row = connection.execute(
                "SELECT difficulty FROM campaign_preferences WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            materialize_item_metadata(
                connection, new_item_id,
                difficulty="Adventurer" if difficulty_row is None else str(difficulty_row["difficulty"]),
            )
        recalculate_character_item_totals(connection, character_id)
        connection.execute(
            "UPDATE combat_reward_items SET claimed = 1, claimed_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND claimed = 0",
            (reward_item_id,),
        )
        summary = f"Claimed {row['quantity']} x {row['name']}."
        updates = progress_quests(
            connection,
            campaign_id,
            "item_collect",
            str(row["name"]),
            amount=int(row["quantity"]),
            detail=summary,
        )
        return " ".join((summary, *updates))

    def acknowledge_reward(self, campaign_id: str, reward_id: str) -> None:
        with self.database.transaction() as connection:
            updated = connection.execute(
                "UPDATE combat_rewards SET acknowledged = 1, "
                "acknowledged_at = CURRENT_TIMESTAMP WHERE id = ? AND encounter_id IN "
                "(SELECT id FROM combat_encounters WHERE campaign_id = ?)",
                (reward_id, campaign_id),
            )
            if updated.rowcount != 1:
                raise CombatError("The selected encounter reward is unavailable.")

    @staticmethod
    def _enemy_target(
        connection: sqlite3.Connection,
        encounter_id: str,
        target_id: str | None,
    ) -> sqlite3.Row:
        if target_id is None:
            row = connection.execute(
                "SELECT * FROM combatants WHERE encounter_id = ? AND side = 'enemy' "
                "AND status = 'active' ORDER BY display_order LIMIT 1",
                (encounter_id,),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT * FROM combatants WHERE id = ? AND encounter_id = ? "
                "AND side = 'enemy' AND status = 'active'",
                (target_id, encounter_id),
            ).fetchone()
        if row is None:
            raise CombatError("Select an active enemy target.")
        return row

    @staticmethod
    def _condition_modifier(
        connection: sqlite3.Connection, combatant_id: str, field: str
    ) -> int:
        if field not in {"armor_modifier", "attack_modifier"}:
            return 0
        row = connection.execute(
            f"SELECT COALESCE(SUM({field}), 0) FROM combat_conditions WHERE combatant_id = ?",
            (combatant_id,),
        ).fetchone()
        return 0 if row is None else int(row[0])

    @staticmethod
    def _current_actor(
        connection: sqlite3.Connection, encounter_id: str
    ) -> sqlite3.Row:
        encounter = connection.execute(
            "SELECT current_index FROM combat_encounters WHERE id = ?",
            (encounter_id,),
        ).fetchone()
        if encounter is None:
            raise CombatError("Combat encounter could not be loaded.")
        actor = connection.execute(
            "SELECT * FROM combatants WHERE encounter_id = ? AND display_order = ?",
            (encounter_id, encounter["current_index"]),
        ).fetchone()
        if actor is None:
            raise CombatError("Combat initiative is invalid.")
        return actor

    def _advance_pointer(
        self, connection: sqlite3.Connection, encounter_id: str
    ) -> list[str]:
        encounter = connection.execute(
            "SELECT current_index, round_number FROM combat_encounters WHERE id = ?",
            (encounter_id,),
        ).fetchone()
        count = connection.execute(
            "SELECT COUNT(*) FROM combatants WHERE encounter_id = ?",
            (encounter_id,),
        ).fetchone()[0]
        if encounter is None or int(count) <= 0:
            raise CombatError("Combat initiative is empty.")
        next_index = (int(encounter["current_index"]) + 1) % int(count)
        next_round = int(encounter["round_number"]) + (
            1 if next_index == 0 else 0
        )
        connection.execute(
            "UPDATE combat_encounters SET current_index = ?, round_number = ? WHERE id = ?",
            (next_index, next_round, encounter_id),
        )
        if next_round > int(encounter["round_number"]):
            return self._process_round_effects(connection, encounter_id)
        return []

    def _process_round_effects(
        self, connection: sqlite3.Connection, encounter_id: str
    ) -> list[str]:
        encounter = connection.execute(
            "SELECT * FROM combat_encounters WHERE id = ?", (encounter_id,)
        ).fetchone()
        if encounter is None:
            return []
        summaries: list[str] = []
        reinforcement = self._maybe_add_reinforcement(
            connection, encounter, encounter_id
        )
        if reinforcement:
            summaries.append(reinforcement)
        rows = connection.execute(
            "SELECT combatants.*, "
            "combat_conditions.damage_per_round AS effect_damage_per_round, "
            "combat_conditions.healing_per_round AS effect_healing_per_round, "
            "combat_conditions.source AS effect_source "
            "FROM combat_conditions "
            "JOIN combatants ON combatants.id = combat_conditions.combatant_id "
            "WHERE combatants.encounter_id = ? AND combatants.status = 'active' "
            "AND combat_conditions.remaining_rounds IS NOT NULL",
            (encounter_id,),
        ).fetchall()
        for row in rows:
            damage = int(row["effect_damage_per_round"])
            healing = int(row["effect_healing_per_round"])
            if damage:
                remaining = self._apply_damage(connection, row, damage)
                summary = (
                    f"{row['name']} suffers {damage} damage from "
                    f"{row['effect_source']} ({remaining}/{row['maximum_health']} HP)."
                )
                self._log_turn(
                    connection, encounter, row, row, "effect", summary, damage=damage
                )
                summaries.append(summary)
            if healing and int(row["current_health"]) > 0:
                restored = min(
                    healing, int(row["maximum_health"]) - int(row["current_health"])
                )
                if restored:
                    new_health = int(row["current_health"]) + restored
                    connection.execute(
                        "UPDATE combatants SET current_health = ? WHERE id = ?",
                        (new_health, row["id"]),
                    )
                    if str(row["side"]) == "player":
                        self._sync_player_health(connection, row, new_health)
                    summary = f"{row['name']} recovers {restored} health from {row['effect_source']}."
                    self._log_turn(
                        connection, encounter, row, row, "effect", summary,
                        healing=restored,
                    )
                    summaries.append(summary)
        connection.execute(
            "UPDATE combat_conditions SET remaining_rounds = remaining_rounds - 1 "
            "WHERE combatant_id IN (SELECT id FROM combatants WHERE encounter_id = ?) "
            "AND remaining_rounds IS NOT NULL",
            (encounter_id,),
        )
        connection.execute(
            "DELETE FROM combat_conditions WHERE remaining_rounds = 0 AND combatant_id IN "
            "(SELECT id FROM combatants WHERE encounter_id = ?)",
            (encounter_id,),
        )
        connection.execute(
            "UPDATE abilities SET cooldown_remaining = MAX(0, cooldown_remaining - 1) "
            "WHERE character_id IN (SELECT character_id FROM combatants "
            "WHERE encounter_id = ? AND character_id IS NOT NULL)",
            (encounter_id,),
        )
        self._check_encounter_end(connection, encounter_id)
        return summaries

    def _maybe_add_reinforcement(
        self,
        connection: sqlite3.Connection,
        encounter: sqlite3.Row,
        encounter_id: str,
    ) -> str:
        key = str(encounter["reinforcement_archetype_key"])
        round_due = encounter["reinforcement_round"]
        if (
            not key or round_due is None or bool(encounter["reinforcement_arrived"])
            or int(encounter["round_number"]) < int(round_due)
        ):
            return ""
        archetype = archetype_by_key(key)
        if archetype is None:
            connection.execute(
                "UPDATE combat_encounters SET reinforcement_arrived = 1 WHERE id = ?",
                (encounter_id,),
            )
            return ""
        order = int(
            connection.execute(
                "SELECT COALESCE(MAX(display_order), -1) + 1 FROM combatants "
                "WHERE encounter_id = ?", (encounter_id,)
            ).fetchone()[0]
        )
        combatant_id = f"combatant-{uuid4().hex}"
        connection.execute(
            """
            INSERT INTO combatants(
                id, encounter_id, name, side, current_health, maximum_health,
                armor_class, attack_bonus, damage_dice_count, damage_die_size,
                damage_bonus, initiative, initiative_modifier, distance_feet,
                movement_feet, attack_range_feet, morale, intelligence,
                weapon_name, display_order, archetype_key, abilities_json,
                resistances_json, vulnerabilities_json, behavior_profile
            ) VALUES (?, ?, ?, 'enemy', ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                combatant_id, encounter_id, archetype.name,
                archetype.maximum_health, archetype.maximum_health,
                archetype.armor_class, archetype.attack_bonus,
                archetype.damage_die_size, archetype.damage_bonus,
                5 + archetype.initiative_modifier, archetype.initiative_modifier,
                archetype.distance_feet, archetype.movement_feet,
                archetype.attack_range_feet, archetype.morale,
                archetype.intelligence, archetype.weapon_name, order,
                archetype.key, json.dumps(archetype.abilities),
                json.dumps(archetype.resistances),
                json.dumps(archetype.vulnerabilities),
                archetype.behavior_profile,
            ),
        )
        connection.execute(
            "UPDATE combat_encounters SET reinforcement_arrived = 1 WHERE id = ?",
            (encounter_id,),
        )
        actor = connection.execute(
            "SELECT * FROM combatants WHERE id = ?", (combatant_id,)
        ).fetchone()
        summary = f"Reinforcement arrives: {archetype.name} joins the encounter."
        if actor is not None:
            self._log_turn(connection, encounter, actor, None, "wait", summary)
        return summary

    @staticmethod
    def _encounter_status(connection: sqlite3.Connection, encounter_id: str) -> str:
        row = connection.execute(
            "SELECT status FROM combat_encounters WHERE id = ?", (encounter_id,)
        ).fetchone()
        if row is None:
            raise CombatError("Combat encounter could not be loaded.")
        return str(row["status"])

    def _log_turn(
        self,
        connection: sqlite3.Connection,
        encounter: sqlite3.Row,
        actor: sqlite3.Row,
        target: sqlite3.Row | None,
        action_type: str,
        summary: str,
        *,
        d20: int | None = None,
        modifier: int = 0,
        total: int | None = None,
        target_number: int | None = None,
        damage: int = 0,
        healing: int = 0,
        action_key: str = "",
    ) -> None:
        sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence), -1) + 1 FROM combat_turns "
                "WHERE encounter_id = ?",
                (encounter["id"],),
            ).fetchone()[0]
        )
        connection.execute(
            """
            INSERT INTO combat_turns(
                id, encounter_id, round_number, sequence, actor_id, target_id,
                action_type, action_key, d20_roll, modifier, total, target_number,
                damage, healing, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"combat-turn-{uuid4().hex}", encounter["id"],
                encounter["round_number"], sequence, actor["id"],
                None if target is None else target["id"], action_type, action_key,
                d20, modifier, total, target_number, damage, healing, summary,
            ),
        )

    @staticmethod
    def _next_campaign_turn(
        connection: sqlite3.Connection, campaign_id: str
    ) -> int:
        connection.execute(
            "UPDATE campaign_clock SET turn_number = turn_number + 1 WHERE campaign_id = ?",
            (campaign_id,),
        )
        row = connection.execute(
            "SELECT turn_number FROM campaign_clock WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        assert row is not None
        return int(row["turn_number"])

    @staticmethod
    def _append_messages(
        connection: sqlite3.Connection,
        campaign_id: str,
        turn_number: int,
        messages: tuple[tuple[str, str], ...],
    ) -> None:
        connection.executemany(
            "INSERT INTO narrative_messages("
            "id, campaign_id, turn_number, sequence, kind, text"
            ") VALUES (?, ?, ?, ?, ?, ?)",
            (
                (
                    f"message-{uuid4().hex}", campaign_id, turn_number,
                    sequence, kind, text,
                )
                for sequence, (kind, text) in enumerate(messages)
                if text.strip()
            ),
        )

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection, campaign_id: str, summary: str
    ) -> None:
        clock = connection.execute(
            "SELECT time_label FROM campaign_clock WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence), -1) + 1 FROM events WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()[0]
        )
        connection.execute(
            "INSERT INTO events("
            "id, campaign_id, time_label, category, summary, sequence, is_recent"
            ") VALUES (?, ?, ?, 'combat', ?, ?, 1)",
            (
                f"event-{uuid4().hex}", campaign_id,
                "Now" if clock is None else str(clock["time_label"]),
                summary, sequence,
            ),
        )

    @staticmethod
    def _refresh_narrative_prompt(
        connection: sqlite3.Connection, campaign_id: str, *, active: bool
    ) -> None:
        prompt = (
            "Combat is active. Choose an action from the Combat tab."
            if active
            else "Combat has ended. What do you do next?"
        )
        suggestions = (
            (
                "Attack the selected enemy", "Advance toward the enemy",
                "Take a defensive stance", "Use a Health Potion",
                "Attempt to flee", "Assess the battlefield",
            )
            if active
            else (
                "Check for injuries", "Inspect the battlefield", "Collect yourself",
                "Review your equipment", "Continue the journey", "Search the area",
            )
        )
        connection.execute(
            "UPDATE narratives SET prompt = ?, suggested_actions_json = ? "
            "WHERE campaign_id = ?",
            (prompt, json.dumps(suggestions), campaign_id),
        )

    @staticmethod
    def _narration_context(
        connection: sqlite3.Connection,
        encounter_id: str,
        player_summary: str,
    ) -> dict[str, Any]:
        encounter = connection.execute(
            "SELECT round_number, environment, hazard FROM combat_encounters WHERE id = ?",
            (encounter_id,),
        ).fetchone()
        combatants = connection.execute(
            "SELECT id, name, side, status, current_health, maximum_health, "
            "distance_feet, morale, weapon_name FROM combatants "
            "WHERE encounter_id = ? ORDER BY display_order",
            (encounter_id,),
        ).fetchall()
        return {
            "round": int(encounter["round_number"]),
            "environment": str(encounter["environment"]),
            "hazard": str(encounter["hazard"]),
            "resolved_player_action": player_summary,
            "combatants": [dict(row) for row in combatants],
        }

    @staticmethod
    def _command_text(
        command: CombatCommand,
        connection: sqlite3.Connection,
        encounter_id: str,
    ) -> str:
        if command.action is CombatAction.ATTACK:
            target = connection.execute(
                "SELECT name FROM combatants WHERE id = ? AND encounter_id = ?",
                (command.target_id, encounter_id),
            ).fetchone()
            return f"Attack {target['name'] if target is not None else 'the enemy'}"
        if command.action is CombatAction.PREPARE:
            return {
                "take_cover": "Take cover before the encounter",
                "scout": "Scout the opposition before engaging",
                "charge": "Charge into the encounter",
            }.get(command.preparation or "", "Prepare for the encounter")
        if command.action is CombatAction.NEGOTIATE:
            target = connection.execute(
                "SELECT name FROM combatants WHERE id = ? AND encounter_id = ?",
                (command.target_id, encounter_id),
            ).fetchone()
            return f"Offer terms to {target['name'] if target is not None else 'the enemy'}"
        if command.action in {CombatAction.ABILITY, CombatAction.SPELL}:
            target = connection.execute(
                "SELECT name FROM combatants WHERE id = ? AND encounter_id = ?",
                (command.target_id, encounter_id),
            ).fetchone()
            definition = CATALOG.get(command.ability_key or "power_strike")
            name = "Power Strike" if definition is None else definition.name
            target_text = target["name"] if target is not None else "self or nearby enemies"
            verb = "Cast" if command.action is CombatAction.SPELL else "Use"
            return f"{verb} {name} on {target_text}"
        return {
            CombatAction.ADVANCE: "Advance toward the enemy",
            CombatAction.DEFEND: "Take a defensive stance",
            CombatAction.USE_ITEM: "Use a healing item",
            CombatAction.FLEE: "Attempt to flee",
        }[command.action]
