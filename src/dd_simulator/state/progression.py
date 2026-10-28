"""Deterministic level, experience, and ability-score progression."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from dd_simulator.state.character_creation import CLASS_DETAILS, ability_modifier
from dd_simulator.state.turns import record_turn_note


MAX_LEVEL = 20
TOTAL_XP_BY_LEVEL = (
    0, 300, 900, 2_700, 6_500, 14_000, 23_000, 34_000, 48_000, 64_000,
    85_000, 100_000, 120_000, 140_000, 165_000, 195_000, 225_000,
    265_000, 305_000, 355_000,
)
BASE_ASI_LEVELS = frozenset({4, 8, 12, 16, 19})
CLASS_ASI_LEVELS = {
    "fighter": frozenset({6, 14}),
    "warrior": frozenset({6, 14}),
    "rogue": frozenset({10}),
}


@dataclass(frozen=True, slots=True)
class ProgressionResult:
    previous_level: int
    level: int
    levels_gained: tuple[int, ...]
    pending_ability_points: int
    summaries: tuple[str, ...]


def xp_to_next(level: int) -> int:
    """Return the fixed XP required to advance from ``level``."""

    normalized = max(1, min(MAX_LEVEL, int(level)))
    if normalized >= MAX_LEVEL:
        return 1
    return TOTAL_XP_BY_LEVEL[normalized] - TOTAL_XP_BY_LEVEL[normalized - 1]


def proficiency_bonus(level: int) -> int:
    return 2 + (max(1, min(MAX_LEVEL, int(level))) - 1) // 4


def saving_throw_proficiencies(character_class: str) -> frozenset[str]:
    details = CLASS_DETAILS.get(character_class, CLASS_DETAILS["Fighter"])
    raw = str(details.get("saves", ""))
    if raw.casefold().startswith("choose"):
        return frozenset()
    return frozenset(value.strip().casefold() for value in raw.split(",") if value.strip())


def grants_ability_score_increase(character_class: str, level: int) -> bool:
    normalized = character_class.casefold().strip()
    return level in BASE_ASI_LEVELS or level in CLASS_ASI_LEVELS.get(
        normalized, frozenset()
    )


def _hit_point_gain(character_class: str, constitution_modifier: int) -> int:
    details = CLASS_DETAILS.get(character_class, CLASS_DETAILS["Fighter"])
    return max(1, int(details["hit_die"]) // 2 + 1 + constitution_modifier)


def award_character_experience(
    connection: sqlite3.Connection,
    character_id: str,
    amount: int,
) -> ProgressionResult:
    """Award XP once, applying all deterministic level benefits atomically."""

    if amount < 0:
        raise ValueError("Experience awards cannot be negative.")
    character = connection.execute(
        "SELECT id, campaign_id, level, character_class, pending_ability_points "
        "FROM characters WHERE id = ?",
        (character_id,),
    ).fetchone()
    if character is None:
        raise ValueError("The character does not exist.")
    experience = connection.execute(
        "SELECT * FROM character_resources WHERE character_id = ? "
        "AND resource_type = 'experience'",
        (character_id,),
    ).fetchone()
    if experience is None:
        raise ValueError("The character is missing an experience resource.")

    previous_level = max(1, min(MAX_LEVEL, int(character["level"])))
    level = previous_level
    value = int(experience["current_value"]) + int(amount)
    character_class = str(character["character_class"])
    constitution = connection.execute(
        "SELECT modifier FROM character_attributes WHERE character_id = ? "
        "AND lower(name) = 'constitution'",
        (character_id,),
    ).fetchone()
    constitution_modifier = 0 if constitution is None else int(constitution["modifier"])
    pending = int(character["pending_ability_points"])
    gained: list[int] = []
    summaries: list[str] = []

    while level < MAX_LEVEL and value >= xp_to_next(level):
        value -= xp_to_next(level)
        level += 1
        gained.append(level)
        summaries.append(f"Character level increased to {level}.")
        health_gain = _hit_point_gain(character_class, constitution_modifier)
        connection.execute(
            "UPDATE character_resources SET maximum_value = maximum_value + ?, "
            "current_value = current_value + ? WHERE character_id = ? "
            "AND resource_type = 'health'",
            (health_gain, health_gain, character_id),
        )
        if grants_ability_score_increase(character_class, level):
            pending += 2
            summaries.append("Choose two ability-score increases before continuing.")

    if level >= MAX_LEVEL:
        value = 0
    connection.execute(
        "UPDATE characters SET level = ?, pending_ability_points = ? WHERE id = ?",
        (level, pending, character_id),
    )
    connection.execute(
        "UPDATE character_resources SET current_value = ?, maximum_value = ? WHERE id = ?",
        (value, xp_to_next(level), experience["id"]),
    )
    campaign_id = str(character["campaign_id"])
    if amount:
        record_turn_note(connection, campaign_id, "xp", f"+{int(amount)} XP")
    for gained_level in gained:
        record_turn_note(connection, campaign_id, "other", f"Reached level {gained_level}")

    # Import locally to avoid making the static ability catalog depend on SQLite.
    from dd_simulator.state.abilities import sync_character_combat_catalog

    sync_character_combat_catalog(
        connection, character_id, character_class=character_class, level=level
    )
    return ProgressionResult(
        previous_level=previous_level,
        level=level,
        levels_gained=tuple(gained),
        pending_ability_points=pending,
        summaries=tuple(summaries),
    )


def allocate_ability_points(
    connection: sqlite3.Connection,
    character_id: str,
    allocations: dict[str, int],
) -> tuple[str, ...]:
    """Spend every pending ASI point, with the normal score cap of 20."""

    character = connection.execute(
        "SELECT level, pending_ability_points FROM characters WHERE id = ?",
        (character_id,),
    ).fetchone()
    if character is None:
        raise ValueError("The character does not exist.")
    pending = int(character["pending_ability_points"])
    normalized = {
        str(name).strip().casefold(): int(points)
        for name, points in allocations.items()
        if int(points) > 0
    }
    if pending <= 0:
        raise ValueError("No ability-score increases are pending.")
    if sum(normalized.values()) != pending:
        raise ValueError(f"Allocate all {pending} pending ability-score points.")

    rows = connection.execute(
        "SELECT id, name, value, modifier FROM character_attributes "
        "WHERE character_id = ?",
        (character_id,),
    ).fetchall()
    by_name = {str(row["name"]).casefold(): row for row in rows}
    for name, points in normalized.items():
        row = by_name.get(name)
        if row is None:
            raise ValueError(f"Unknown ability score: {name}.")
        if int(row["value"]) + points > 20:
            raise ValueError(f"{row['name']} cannot exceed 20.")

    constitution_modifier_delta = 0
    summaries: list[str] = []
    for name, points in normalized.items():
        row = by_name[name]
        new_value = int(row["value"]) + points
        new_modifier = ability_modifier(new_value)
        if name == "constitution":
            constitution_modifier_delta = new_modifier - int(row["modifier"])
        connection.execute(
            "UPDATE character_attributes SET value = ?, modifier = ? WHERE id = ?",
            (new_value, new_modifier, row["id"]),
        )
        summaries.append(f"{row['name']} increased to {new_value}.")

    if constitution_modifier_delta:
        health_gain = constitution_modifier_delta * int(character["level"])
        connection.execute(
            "UPDATE character_resources SET maximum_value = maximum_value + ?, "
            "current_value = current_value + ? WHERE character_id = ? "
            "AND resource_type = 'health'",
            (health_gain, health_gain, character_id),
        )
    connection.execute(
        "UPDATE characters SET pending_ability_points = 0 WHERE id = ?",
        (character_id,),
    )
    return tuple(summaries)
