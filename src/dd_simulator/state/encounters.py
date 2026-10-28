"""Persistent enemy catalog and deterministic encounter generation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import sqlite3


@dataclass(frozen=True, slots=True)
class EnemyArchetype:
    key: str
    name: str
    tier: int
    biome: str
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
    abilities: tuple[str, ...] = ()
    resistances: tuple[str, ...] = ()
    vulnerabilities: tuple[str, ...] = ()
    behavior_profile: str = "Press the attack while morale holds."
    loot: tuple[str, ...] = ()
    reinforcement_key: str = ""


@dataclass(frozen=True, slots=True)
class EnemyAbility:
    key: str
    name: str
    kind: str
    range_feet: int
    description: str
    attack_bonus: int = 0
    damage_bonus: int = 0
    condition_name: str = ""
    armor_modifier: int = 0
    attack_modifier: int = 0
    duration: int = 0


@dataclass(frozen=True, slots=True)
class GeneratedEncounter:
    enemies: tuple[EnemyArchetype, ...]
    environment: str
    terrain: str
    hazard: str
    introduction: str
    awareness_state: str
    difficulty_rating: int
    reinforcement_key: str = ""
    reinforcement_round: int | None = None


ENEMY_ABILITIES: dict[str, EnemyAbility] = {
    "pounce": EnemyAbility("pounce", "Pounce", "attack", 15, "Leap into a violent opening strike.", attack_bonus=2, damage_bonus=2),
    "poison_strike": EnemyAbility("poison_strike", "Poison Strike", "attack_condition", 5, "A poisoned weapon weakens its victim.", attack_bonus=1, condition_name="Poisoned", attack_modifier=-1, duration=2),
    "war_cry": EnemyAbility("war_cry", "War Cry", "debuff", 30, "A brutal cry shakes enemy resolve.", condition_name="Shaken", attack_modifier=-2, duration=2),
    "arcane_bolt": EnemyAbility("arcane_bolt", "Arcane Bolt", "attack", 60, "A focused bolt of hostile magic.", attack_bonus=2, damage_bonus=3),
    "bone_guard": EnemyAbility("bone_guard", "Bone Guard", "buff", 0, "Necrotic force hardens old bones.", condition_name="Bone Guard", armor_modifier=2, duration=2),
    "crushing_blow": EnemyAbility("crushing_blow", "Crushing Blow", "attack", 5, "A massive overhead strike.", attack_bonus=-1, damage_bonus=5),
    "shadow_step": EnemyAbility("shadow_step", "Shadow Step", "buff", 0, "Fold into darkness and become difficult to strike.", condition_name="Shadowed", armor_modifier=3, duration=2),
}


ENEMY_ARCHETYPES: tuple[EnemyArchetype, ...] = (
    EnemyArchetype("road_bandit", "Road Bandit", 1, "road", 14, 11, 3, 6, 1, 2, morale=45, intelligence="cunning", weapon_name="Shortsword", abilities=("poison_strike",), loot=("Gold", "Bandages"), reinforcement_key="road_bandit"),
    EnemyArchetype("goblin_skirmisher", "Goblin Skirmisher", 1, "any", 12, 12, 3, 6, 1, 3, morale=35, intelligence="cunning", weapon_name="Rusty Scimitar", abilities=("pounce",), vulnerabilities=("radiant",), loot=("Gold", "Health Potion"), reinforcement_key="goblin_archer"),
    EnemyArchetype("goblin_archer", "Goblin Archer", 1, "forest", 10, 11, 3, 6, 0, 3, attack_range_feet=60, morale=30, intelligence="cautious", weapon_name="Shortbow", loot=("Arrows", "Gold")),
    EnemyArchetype("dire_wolf", "Dire Wolf", 2, "forest", 22, 12, 4, 8, 2, 3, movement_feet=25, morale=55, intelligence="instinctive", weapon_name="Fangs", abilities=("pounce",), vulnerabilities=("fire",), behavior_profile="Circle isolated prey, pounce, and retreat when badly wounded.", loot=("Bandages",)),
    EnemyArchetype("restless_skeleton", "Restless Skeleton", 2, "ruins", 20, 13, 4, 6, 2, 1, morale=100, intelligence="relentless", weapon_name="Ancient Blade", abilities=("bone_guard",), resistances=("poison",), vulnerabilities=("radiant",), loot=("Gold", "Moonstone")),
    EnemyArchetype("cult_adept", "Cult Adept", 3, "ruins", 26, 12, 5, 8, 2, 2, attack_range_feet=60, morale=48, intelligence="calculating", weapon_name="Ritual Staff", abilities=("arcane_bolt", "war_cry"), resistances=("shadow",), vulnerabilities=("radiant",), loot=("Health Potion", "Moonstone"), reinforcement_key="road_bandit"),
    EnemyArchetype("hill_ogre", "Hill Ogre", 4, "mountain", 48, 13, 6, 10, 4, -1, morale=62, intelligence="simple", weapon_name="Great Club", abilities=("crushing_blow", "war_cry"), vulnerabilities=("cold",), loot=("Gold", "Travel Rations", "Health Potion")),
    EnemyArchetype("living_shadow", "Living Shadow", 4, "any", 36, 15, 6, 8, 3, 4, attack_range_feet=30, morale=80, intelligence="alien", weapon_name="Shadow Claws", abilities=("shadow_step", "arcane_bolt"), resistances=("physical", "shadow"), vulnerabilities=("radiant",), loot=("Moonstone", "Antidote")),
)


def sync_enemy_archetypes(connection: sqlite3.Connection) -> None:
    for enemy in ENEMY_ARCHETYPES:
        connection.execute(
            """
            INSERT INTO enemy_archetypes(
                archetype_key, name, tier, biome, maximum_health, armor_class,
                attack_bonus, damage_die_size, damage_bonus, initiative_modifier,
                distance_feet, movement_feet, attack_range_feet, morale,
                intelligence, weapon_name, abilities_json, resistances_json,
                vulnerabilities_json, behavior_profile, loot_table_json,
                reinforcement_key, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(archetype_key) DO UPDATE SET
                name=excluded.name, tier=excluded.tier, biome=excluded.biome,
                maximum_health=excluded.maximum_health, armor_class=excluded.armor_class,
                attack_bonus=excluded.attack_bonus, damage_die_size=excluded.damage_die_size,
                damage_bonus=excluded.damage_bonus, initiative_modifier=excluded.initiative_modifier,
                distance_feet=excluded.distance_feet, movement_feet=excluded.movement_feet,
                attack_range_feet=excluded.attack_range_feet, morale=excluded.morale,
                intelligence=excluded.intelligence, weapon_name=excluded.weapon_name,
                abilities_json=excluded.abilities_json, resistances_json=excluded.resistances_json,
                vulnerabilities_json=excluded.vulnerabilities_json,
                behavior_profile=excluded.behavior_profile, loot_table_json=excluded.loot_table_json,
                reinforcement_key=excluded.reinforcement_key, updated_at=CURRENT_TIMESTAMP
            """,
            (
                enemy.key, enemy.name, enemy.tier, enemy.biome, enemy.maximum_health,
                enemy.armor_class, enemy.attack_bonus, enemy.damage_die_size,
                enemy.damage_bonus, enemy.initiative_modifier, enemy.distance_feet,
                enemy.movement_feet, enemy.attack_range_feet, enemy.morale,
                enemy.intelligence, enemy.weapon_name, json.dumps(enemy.abilities),
                json.dumps(enemy.resistances), json.dumps(enemy.vulnerabilities),
                enemy.behavior_profile, json.dumps(enemy.loot), enemy.reinforcement_key,
            ),
        )


def generate_encounter(
    connection: sqlite3.Connection, campaign_id: str
) -> GeneratedEncounter:
    character = connection.execute(
        "SELECT level FROM characters WHERE campaign_id = ? AND is_player = 1",
        (campaign_id,),
    ).fetchone()
    location = connection.execute(
        "SELECT name, region, danger FROM locations WHERE campaign_id = ? AND is_current = 1",
        (campaign_id,),
    ).fetchone()
    preference = connection.execute(
        "SELECT difficulty FROM campaign_preferences WHERE campaign_id = ?",
        (campaign_id,),
    ).fetchone()
    clock = connection.execute(
        "SELECT turn_number FROM campaign_clock WHERE campaign_id = ?", (campaign_id,)
    ).fetchone()
    level = 1 if character is None else int(character["level"])
    difficulty_name = "Adventurer" if preference is None else str(preference["difficulty"])
    base = {"Story": 1, "Adventurer": 2, "Veteran": 3, "Deadly": 4}.get(difficulty_name, 2)
    rating = max(1, min(10, base + max(0, (level - 1) // 3)))
    location_name = "Unknown Road" if location is None else str(location["name"])
    region = "" if location is None else str(location["region"])
    danger = "" if location is None else str(location["danger"])
    text = f"{location_name} {region}".casefold()
    biome = (
        "forest" if any(word in text for word in ("forest", "wood", "grove"))
        else "ruins" if any(word in text for word in ("ruin", "temple", "crypt"))
        else "mountain" if any(word in text for word in ("mountain", "hill", "peak"))
        else "road"
    )
    turn = 0 if clock is None else int(clock["turn_number"])
    digest = hashlib.sha256(f"{campaign_id}|{location_name}|{turn}|{rating}".encode()).digest()
    max_tier = max(1, min(4, (rating + 1) // 2))
    eligible = tuple(
        enemy for enemy in ENEMY_ARCHETYPES
        if enemy.tier <= max_tier and enemy.biome in {"any", biome}
    ) or ENEMY_ARCHETYPES[:2]
    count = 1 + (1 if rating >= 2 else 0) + (1 if rating >= 5 else 0)
    enemies = tuple(eligible[digest[index] % len(eligible)] for index in range(count))
    awareness_state = ("aware", "enemies_surprised", "player_surprised")[digest[5] % 3]
    terrain_options = {
        "forest": ("Dense trees and tangled roots", "A narrow trail between old trees"),
        "ruins": ("Broken masonry and unstable columns", "A debris-strewn chamber"),
        "mountain": ("Loose stone on a steep incline", "A windswept rocky shelf"),
        "road": ("A rutted road with shallow ditches", "An abandoned cart blocks part of the road"),
    }
    terrain = terrain_options[biome][digest[6] % 2]
    hazard = (
        f"{terrain}; partial cover is available."
        if digest[7] % 2 == 0
        else f"{terrain}; movement through the center is difficult."
    )
    names = ", ".join(enemy.name for enemy in enemies)
    introduction = (
        f"At {location_name}, {names} move into view. {terrain}. "
        f"Awareness: {awareness_state.replace('_', ' ')}."
    )
    reinforcement_key = ""
    reinforcement_round = None
    if rating >= 4:
        reinforcement_key = next(
            (enemy.reinforcement_key for enemy in enemies if enemy.reinforcement_key), ""
        )
        reinforcement_round = 3 if reinforcement_key else None
    return GeneratedEncounter(
        enemies, location_name, terrain, hazard, introduction, awareness_state,
        rating, reinforcement_key, reinforcement_round,
    )


def archetype_by_key(key: str) -> EnemyArchetype | None:
    return next((enemy for enemy in ENEMY_ARCHETYPES if enemy.key == key), None)
