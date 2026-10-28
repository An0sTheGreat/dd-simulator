"""Small data-driven preset-campaign adapter."""

from __future__ import annotations

import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dd_simulator.state.character_creation import CharacterCreationDraft


LAST_ORRERY_OF_SOL = "last_orrery_of_sol"
_PRESET_FILES = {
    LAST_ORRERY_OF_SOL: "the_last_orrery_of_sol.json",
}
_GATED_OBJECTIVE = re.compile(
    r"^(?:assign|confront|defeat|destroy|earn|free|negotiate|resolve|secure)\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=None)
def load_preset(preset_id: str) -> dict[str, Any]:
    filename = _PRESET_FILES.get(preset_id)
    if filename is None:
        raise KeyError(preset_id)
    path = Path(__file__).with_name("presets") / filename
    return json.loads(path.read_text(encoding="utf-8"))


def preset_choices() -> tuple[tuple[str, str], ...]:
    return tuple(
        (str(load_preset(preset_id)["display_name"]), preset_id)
        for preset_id in _PRESET_FILES
    )


def preset_fallback_intro(draft: CharacterCreationDraft) -> str | None:
    if not draft.preset_id:
        return None
    preset = load_preset(draft.preset_id)
    opening = preset["opening"]
    return str(opening["fallback"]).format(
        name=draft.name,
        character=draft.name,
        ancestry=draft.ancestry,
        character_class=draft.character_class,
        weapon=draft.primary_weapon,
        motivation=(draft.motivation or "an unanswered purpose").rstrip("."),
    )


def preset_intro_context(preset_id: str) -> dict[str, Any]:
    preset = load_preset(preset_id)
    return {
        "preset_id": preset_id,
        "act": preset["act"],
        "act_title": preset["act_title"],
        "opening": preset["opening"],
        "dm_rules": preset["dm_rules"],
        "active_quest": preset["quests"][0],
    }


def seed_preset_campaign(
    connection: sqlite3.Connection,
    campaign_id: str,
    character_id: str,
    preset_id: str,
) -> None:
    """Replace generic world seed data with one packaged preset."""

    preset = load_preset(preset_id)
    connection.execute("DELETE FROM quests WHERE campaign_id = ?", (campaign_id,))
    connection.execute("DELETE FROM locations WHERE campaign_id = ?", (campaign_id,))
    connection.execute(
        "UPDATE campaigns SET name = ?, premise = ? WHERE id = ?",
        (preset["name"], preset["premise"], campaign_id),
    )

    location_ids: dict[str, str] = {}
    for raw in preset["locations"]:
        location_id = f"{campaign_id}-preset-location-{raw['id']}"
        location_ids[raw["id"]] = location_id
        connection.execute(
            """
            INSERT INTO locations(
                id, campaign_id, name, region, weather, danger, route_status,
                is_current, description, biome, discovered, visit_count,
                first_discovered_at, last_visited_at, can_camp, map_x, map_y
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      CASE WHEN ? = 1 THEN CURRENT_TIMESTAMP END,
                      CASE WHEN ? = 1 THEN CURRENT_TIMESTAMP END, ?, ?, ?)
            """,
            (
                location_id, campaign_id, raw["name"], raw["region"],
                raw.get("weather", "Controlled climate"), raw["danger"],
                raw["route_status"], int(raw["current"]), raw["description"], raw["biome"],
                int(raw["discovered"]), int(raw["current"]), int(raw["discovered"]),
                int(raw["current"]), int(raw["can_camp"]), raw["map_x"], raw["map_y"],
            ),
        )

    route_ids: dict[str, str] = {}
    for raw in preset["routes"]:
        route_id = f"{campaign_id}-preset-route-{raw['id']}"
        route_ids[raw["id"]] = route_id
        connection.execute(
            """
            INSERT INTO travel_routes(
                id, campaign_id, origin_location_id, destination_location_id,
                distance_miles, travel_minutes, stamina_cost, danger_rating,
                status, description, bidirectional, discovered
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, 'open', ?, 1, ?)
            """,
            (
                route_id, campaign_id, location_ids[raw["origin"]],
                location_ids[raw["destination"]], max(1, int(raw["minutes"]) // 30),
                raw["minutes"], raw["danger"], raw["description"], int(raw["discovered"]),
            ),
        )

    quest_ids: dict[str, str] = {}
    for order, raw in enumerate(preset["quests"]):
        quest_id = f"{campaign_id}-preset-quest-{raw['id']}"
        quest_ids[raw["id"]] = quest_id
        connection.execute(
            """
            INSERT INTO quests(
                id, campaign_id, title, status, summary, progress_current,
                progress_maximum, selected, display_order, quest_type,
                started_day, started_minute, reward_experience, reward_currency,
                reward_reputation, reward_faction, reward_items_json
            ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, 'main', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                quest_id, campaign_id, raw["title"], "active" if order == 0 else "rumored",
                raw["summary"], len(raw["objectives"]), int(order == 0), order,
                1 if order == 0 else None, 480 if order == 0 else None,
                raw["reward_xp"], raw["reward_gold"], raw["reward_reputation"],
                raw["reward_faction"], json.dumps(raw["reward_items"]),
            ),
        )
        required_orders = tuple(
            index for index, objective in enumerate(raw["objectives"])
            if not objective.get("optional", False)
        )
        final_required_order = required_orders[-1] if required_orders else -1
        for objective_order, objective in enumerate(raw["objectives"]):
            connection.execute(
                """
                INSERT INTO quest_objectives(
                    id, quest_id, text, completed, optional, display_order,
                    trigger_type, trigger_target, current_count, required_count,
                    completion_gate
                ) VALUES (?, ?, ?, 0, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    f"{quest_id}-objective-{objective_order}", quest_id, objective["text"],
                    int(objective.get("optional", False)), objective_order,
                    objective["trigger"], objective["target"], objective.get("required", 1),
                    int(objective.get(
                        "completion_gate",
                        objective_order == final_required_order
                        or bool(_GATED_OBJECTIVE.match(str(objective["text"]))),
                    )),
                ),
            )
    for current, following in zip(preset["quests"], preset["quests"][1:]):
        connection.execute(
            "UPDATE quests SET follow_up_quest_id = ? WHERE id = ?",
            (quest_ids[following["id"]], quest_ids[current["id"]]),
        )

    for raw in preset["npcs"]:
        npc_id = f"{campaign_id}-preset-npc-{raw['id']}"
        connection.execute(
            """
            INSERT INTO npcs(
                id, campaign_id, name, location_id, disposition, notes, status,
                title, portrait_initials, personality, voice_style, biography,
                faction, available, known
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                npc_id, campaign_id, raw["name"], location_ids[raw["location"]],
                raw["disposition"], raw["biography"], raw["disposition"], raw["title"],
                "".join(part[0] for part in raw["name"].split()[:2]).upper(),
                raw["personality"], raw["voice"], raw["biography"], raw["faction"],
                int(raw["known"]),
            ),
        )
        connection.execute(
            """
            INSERT INTO relationships(
                id, campaign_id, source_entity_id, target_entity_id,
                relationship_type, score, notes
            ) VALUES (?, ?, ?, ?, 'acquaintance', ?, ?)
            """,
            (
                f"{campaign_id}-preset-relationship-{raw['id']}", campaign_id,
                character_id, npc_id, 10 if raw["disposition"] == "friendly" else 0,
                f"Initial relationship for {preset['act_title']}.",
            ),
        )

    for key, value in (
        ("preset_id", preset_id),
        ("preset_act", preset["act"]),
        ("preset_current_quest_id", preset["quests"][0]["id"]),
    ):
        connection.execute(
            "INSERT INTO campaign_flags(campaign_id, flag_key, value_json) VALUES (?, ?, ?) "
            "ON CONFLICT(campaign_id, flag_key) DO UPDATE SET value_json = excluded.value_json",
            (campaign_id, key, json.dumps(value)),
        )
    connection.execute(
        "UPDATE narratives SET title = ?, suggested_actions_json = ? WHERE campaign_id = ?",
        (
            preset["opening"]["location"],
            json.dumps(tuple(preset["opening"]["suggested_actions"])),
            campaign_id,
        ),
    )
    connection.execute(
        "UPDATE events SET summary = ? WHERE campaign_id = ? AND sequence = 0",
        (str(preset["opening"]["event_summary"]), campaign_id),
    )


def active_preset_context(
    connection: sqlite3.Connection, campaign_id: str
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT value_json FROM campaign_flags WHERE campaign_id = ? AND flag_key = 'preset_id'",
        (campaign_id,),
    ).fetchone()
    if row is None:
        return None
    preset_id = str(json.loads(str(row["value_json"])))
    preset = load_preset(preset_id)
    active = connection.execute(
        "SELECT title FROM quests WHERE campaign_id = ? AND status = 'active' "
        "ORDER BY display_order LIMIT 1",
        (campaign_id,),
    ).fetchone()
    active_title = "" if active is None else str(active["title"])
    quest = next(
        (raw for raw in preset["quests"] if raw["title"] == active_title),
        preset["quests"][0],
    )
    discovered = {
        str(raw["name"])
        for raw in connection.execute(
            "SELECT name FROM locations WHERE campaign_id = ? AND discovered = 1",
            (campaign_id,),
        ).fetchall()
    }
    return {
        "id": preset_id,
        "act": preset["act"],
        "act_title": preset["act_title"],
        "dm_rules": preset["dm_rules"],
        "active_quest": {
            "title": quest["title"],
            "summary": quest["summary"],
            "dm_context": quest["dm_context"],
            "known_locations": [
                raw["name"] for raw in preset["locations"] if raw["name"] in discovered
            ],
        },
    }


def advance_preset_after_quest(
    connection: sqlite3.Connection, campaign_id: str, completed_quest_id: str
) -> None:
    context = active_preset_context(connection, campaign_id)
    if context is None:
        return
    preset = load_preset(str(context["id"]))
    completed = next(
        (
            raw for raw in preset["quests"]
            if completed_quest_id.endswith(f"preset-quest-{raw['id']}")
        ),
        None,
    )
    if completed is None:
        return
    for slug in completed["unlock_locations"]:
        connection.execute(
            "UPDATE locations SET discovered = 1, first_discovered_at = "
            "COALESCE(first_discovered_at, CURRENT_TIMESTAMP) "
            "WHERE id = ?",
            (f"{campaign_id}-preset-location-{slug}",),
        )
    for slug in completed["unlock_npcs"]:
        connection.execute(
            "UPDATE npcs SET known = 1 WHERE id = ?",
            (f"{campaign_id}-preset-npc-{slug}",),
        )
    connection.execute(
        "UPDATE travel_routes SET discovered = 1 WHERE campaign_id = ? "
        "AND origin_location_id IN (SELECT id FROM locations WHERE campaign_id = ? AND discovered = 1) "
        "AND destination_location_id IN (SELECT id FROM locations WHERE campaign_id = ? AND discovered = 1)",
        (campaign_id, campaign_id, campaign_id),
    )
    next_row = connection.execute(
        "SELECT id FROM quests WHERE campaign_id = ? AND status = 'active' "
        "ORDER BY display_order LIMIT 1",
        (campaign_id,),
    ).fetchone()
    if next_row is not None:
        next_id = str(next_row["id"]).split("preset-quest-", 1)[-1]
        connection.execute(
            "UPDATE campaign_flags SET value_json = ? "
            "WHERE campaign_id = ? AND flag_key = 'preset_current_quest_id'",
            (json.dumps(next_id), campaign_id),
        )
