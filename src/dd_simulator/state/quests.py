"""Deterministic quest progression, deadlines, and persistent rewards."""

from __future__ import annotations

import json
import re
import sqlite3
from uuid import uuid4

from dd_simulator.state.database import GameStateDatabase
from dd_simulator.state.errors import GameStateError
from dd_simulator.state.item_actions import (
    item_definition,
    materialize_item_metadata,
    recalculate_character_item_totals,
)
from dd_simulator.state.item_catalog import select_loot
from dd_simulator.state.presets import advance_preset_after_quest
from dd_simulator.state.progression import award_character_experience


TRIGGER_TYPES = {
    "combat", "travel", "item_collect", "item_use", "item_examine",
    "dialogue", "custom_action",
}

_RESOLUTION_VERBS = re.compile(
    r"\b(destroy(?:ed|ing)?|repair(?:ed|ing)?|release(?:d|ing)?|defeat(?:ed|ing)?|"
    r"resolve(?:d|ing)?|finish(?:ed|ing)?|complete(?:d|ing)?|stop(?:ped|ping)?|"
    r"save(?:d|ing)?|rescue(?:d|ing)?|seal(?:ed|ing)?|banish(?:ed|ing)?|"
    r"secure(?:d|ing)?|recover(?:ed|ing)?|align(?:ed|ing)?|rewrite|rewrote|"
    r"persuade(?:d|ing)?|decide(?:d|ing)?|negotiate(?:d|ing)?|"
    r"establish(?:ed|ing)?|free(?:d|ing)?)\b",
    re.IGNORECASE,
)


def _prior_required_objectives_complete(
    connection: sqlite3.Connection,
    quest_id: str,
    display_order: int,
) -> bool:
    return connection.execute(
        "SELECT 1 FROM quest_objectives WHERE quest_id = ? AND optional = 0 "
        "AND display_order < ? AND completed = 0 LIMIT 1",
        (quest_id, display_order),
    ).fetchone() is None
_TENTATIVE_WORDS = re.compile(
    r"\b(consider|inspect|examine|prepare|plan|whether|might|could|should|try to|"
    r"before|look for|search for)\b",
    re.IGNORECASE,
)


def _completion_gate_is_resolved(evidence: str) -> bool:
    normalized = " ".join(evidence.split())
    return bool(_RESOLUTION_VERBS.search(normalized)) and not bool(
        _TENTATIVE_WORDS.search(normalized)
    )


def progress_quests(
    connection: sqlite3.Connection,
    campaign_id: str,
    trigger_type: str,
    target: str = "",
    *,
    amount: int = 1,
    detail: str = "",
) -> tuple[str, ...]:
    """Advance matching active objectives inside the caller's transaction."""

    if trigger_type not in TRIGGER_TYPES or amount <= 0:
        return ()
    target_folded = target.casefold().strip()
    detail_folded = detail.casefold().strip()
    rows = connection.execute(
        """
        SELECT quest_objectives.*, quests.title AS quest_title
        FROM quest_objectives
        JOIN quests ON quests.id = quest_objectives.quest_id
        WHERE quests.campaign_id = ? AND quests.status = 'active'
          AND quest_objectives.completed = 0
          AND quest_objectives.trigger_type = ?
        ORDER BY quests.display_order, quest_objectives.display_order
        """,
        (campaign_id, trigger_type),
    ).fetchall()
    summaries: list[str] = []
    touched: set[str] = set()
    for row in rows:
        expected = str(row["trigger_target"]).casefold().strip()
        matches = not expected and trigger_type not in {"custom_action", "dialogue"}
        if expected:
            if trigger_type in {"custom_action", "dialogue"}:
                matches = expected in detail_folded or expected == target_folded
            else:
                matches = expected == target_folded or expected in detail_folded
        if not matches:
            continue
        if bool(row["completion_gate"]):
            if not _prior_required_objectives_complete(
                connection, str(row["quest_id"]), int(row["display_order"])
            ):
                continue
            if trigger_type in {"custom_action", "dialogue"} and (
                not expected
                or expected not in detail_folded
                or not _completion_gate_is_resolved(detail)
            ):
                continue
        current = min(
            int(row["required_count"]), int(row["current_count"]) + amount
        )
        completed = current >= int(row["required_count"])
        connection.execute(
            "UPDATE quest_objectives SET current_count = ?, completed = ?, "
            "completed_at = CASE WHEN ? = 1 THEN CURRENT_TIMESTAMP ELSE completed_at END "
            "WHERE id = ?",
            (current, int(completed), int(completed), row["id"]),
        )
        summary = (
            f"Completed objective: {row['text']}"
            if completed
            else f"Quest progress: {row['text']} ({current}/{row['required_count']})."
        )
        connection.execute(
            "INSERT INTO quest_updates(id, quest_id, objective_id, update_type, summary) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                f"quest-update-{uuid4().hex}", row["quest_id"], row["id"],
                "completed" if completed else "progress", summary,
            ),
        )
        summaries.append(summary)
        touched.add(str(row["quest_id"]))
    for quest_id in touched:
        completion = _refresh_quest(connection, campaign_id, quest_id)
        if completion:
            summaries.append(completion)
    return tuple(summaries)


def complete_objective(
    connection: sqlite3.Connection,
    campaign_id: str,
    objective_id: str,
    *,
    evidence: str = "",
) -> str:
    row = connection.execute(
        """
        SELECT quest_objectives.*, quests.status, quests.title AS quest_title
        FROM quest_objectives JOIN quests ON quests.id = quest_objectives.quest_id
        WHERE quest_objectives.id = ? AND quests.campaign_id = ?
        """,
        (objective_id, campaign_id),
    ).fetchone()
    if row is None:
        raise GameStateError("The selected objective is not in the active campaign.")
    if str(row["status"]) != "active":
        raise GameStateError("Objectives can only advance on active quests.")
    if bool(row["completed"]):
        raise GameStateError("That objective is already complete.")
    if bool(row["completion_gate"]):
        if not _prior_required_objectives_complete(
            connection, str(row["quest_id"]), int(row["display_order"])
        ):
            raise GameStateError(
                "Complete the earlier required objectives before resolving this encounter."
            )
        trigger_type = str(row["trigger_type"])
        if trigger_type not in {"custom_action", "dialogue"}:
            raise GameStateError(
                f"That objective must be completed through the {trigger_type.replace('_', ' ')} system."
            )
        expected = str(row["trigger_target"]).casefold().strip()
        if (
            not expected
            or expected not in evidence.casefold()
            or not _completion_gate_is_resolved(evidence)
        ):
            raise GameStateError(
                "That encounter requires its named target and a clearly resolved outcome."
            )
    connection.execute(
        "UPDATE quest_objectives SET completed = 1, current_count = required_count, "
        "completed_at = CURRENT_TIMESTAMP WHERE id = ?",
        (objective_id,),
    )
    summary = f"Completed objective: {row['text']}"
    connection.execute(
        "INSERT INTO quest_updates(id, quest_id, objective_id, update_type, summary) "
        "VALUES (?, ?, ?, 'completed', ?)",
        (f"quest-update-{uuid4().hex}", row["quest_id"], objective_id, summary),
    )
    completion = _refresh_quest(connection, campaign_id, str(row["quest_id"]))
    return summary if not completion else f"{summary} {completion}"


def check_deadlines(
    connection: sqlite3.Connection, campaign_id: str
) -> tuple[str, ...]:
    clock = connection.execute(
        "SELECT day, minute_of_day FROM campaign_clock WHERE campaign_id = ?",
        (campaign_id,),
    ).fetchone()
    if clock is None:
        return ()
    now = int(clock["day"]) * 1440 + int(clock["minute_of_day"])
    rows = connection.execute(
        "SELECT * FROM quests WHERE campaign_id = ? AND status = 'active' "
        "AND deadline_day IS NOT NULL AND deadline_minute IS NOT NULL",
        (campaign_id,),
    ).fetchall()
    summaries: list[str] = []
    for row in rows:
        deadline = int(row["deadline_day"]) * 1440 + int(row["deadline_minute"])
        if now <= deadline:
            continue
        summary = f"Quest failed: {row['title']} (deadline passed)."
        connection.execute(
            "UPDATE quests SET status = 'failed', failed_at = CURRENT_TIMESTAMP, "
            "failure_reason = 'Deadline passed', selected = 0 WHERE id = ?",
            (row["id"],),
        )
        connection.execute(
            "INSERT INTO quest_updates(id, quest_id, update_type, summary) "
            "VALUES (?, ?, 'failed', ?)",
            (f"quest-update-{uuid4().hex}", row["id"], summary),
        )
        summaries.append(summary)
    if summaries:
        _select_next_active(connection, campaign_id)
    return tuple(summaries)


def abandon_quest(
    connection: sqlite3.Connection, campaign_id: str, quest_id: str
) -> str:
    quest = connection.execute(
        "SELECT * FROM quests WHERE id = ? AND campaign_id = ?",
        (quest_id, campaign_id),
    ).fetchone()
    if quest is None or str(quest["status"]) != "active":
        raise GameStateError("Only an active quest can be abandoned.")
    connection.execute(
        "UPDATE quests SET status = 'abandoned', abandoned_at = CURRENT_TIMESTAMP, "
        "selected = 0 WHERE id = ?",
        (quest_id,),
    )
    summary = f"Quest abandoned: {quest['title']}."
    connection.execute(
        "INSERT INTO quest_updates(id, quest_id, update_type, summary) "
        "VALUES (?, ?, 'abandoned', ?)",
        (f"quest-update-{uuid4().hex}", quest_id, summary),
    )
    _select_next_active(connection, campaign_id)
    return summary


def _refresh_quest(
    connection: sqlite3.Connection, campaign_id: str, quest_id: str
) -> str:
    counts = connection.execute(
        "SELECT COUNT(*) AS total, SUM(completed) AS complete, "
        "SUM(CASE WHEN optional = 0 THEN 1 ELSE 0 END) AS required_total, "
        "SUM(CASE WHEN optional = 0 AND completed = 1 THEN 1 ELSE 0 END) AS required_complete "
        "FROM quest_objectives WHERE quest_id = ?",
        (quest_id,),
    ).fetchone()
    total = max(1, int(counts["total"] or 0))
    complete = int(counts["complete"] or 0)
    required_total = int(counts["required_total"] or 0)
    required_complete = int(counts["required_complete"] or 0)
    connection.execute(
        "UPDATE quests SET progress_current = ?, progress_maximum = ? WHERE id = ?",
        (complete, total, quest_id),
    )
    if not required_total or required_complete != required_total:
        return ""
    quest = connection.execute(
        "SELECT * FROM quests WHERE id = ? AND campaign_id = ?", (quest_id, campaign_id)
    ).fetchone()
    if quest is None or str(quest["status"]) != "active":
        return ""
    connection.execute(
        "UPDATE quests SET status = 'completed', completed_at = CURRENT_TIMESTAMP, "
        "selected = 0 WHERE id = ?",
        (quest_id,),
    )
    summary = f"Quest completed: {quest['title']}."
    connection.execute(
        "INSERT INTO quest_updates(id, quest_id, update_type, summary) "
        "VALUES (?, ?, 'completed', ?)",
        (f"quest-update-{uuid4().hex}", quest_id, summary),
    )
    _create_reward(connection, campaign_id, quest)
    follow_up = str(quest["follow_up_quest_id"] or "")
    if follow_up:
        connection.execute(
            "UPDATE quests SET status = 'active', started_day = "
            "(SELECT day FROM campaign_clock WHERE campaign_id = ?), started_minute = "
            "(SELECT minute_of_day FROM campaign_clock WHERE campaign_id = ?) "
            "WHERE id = ? AND campaign_id = ? AND status = 'rumored'",
            (campaign_id, campaign_id, follow_up, campaign_id),
        )
    _select_next_active(connection, campaign_id)
    advance_preset_after_quest(connection, campaign_id, quest_id)
    return summary


def _select_next_active(connection: sqlite3.Connection, campaign_id: str) -> None:
    selected = connection.execute(
        "SELECT 1 FROM quests WHERE campaign_id = ? AND selected = 1", (campaign_id,)
    ).fetchone()
    if selected is not None:
        return
    row = connection.execute(
        "SELECT id FROM quests WHERE campaign_id = ? AND status = 'active' "
        "ORDER BY display_order LIMIT 1",
        (campaign_id,),
    ).fetchone()
    if row is not None:
        connection.execute("UPDATE quests SET selected = 1 WHERE id = ?", (row["id"],))


def _create_reward(
    connection: sqlite3.Connection, campaign_id: str, quest: sqlite3.Row
) -> None:
    existing = connection.execute(
        "SELECT id FROM quest_rewards WHERE quest_id = ?", (quest["id"],)
    ).fetchone()
    if existing is not None:
        return
    reward_id = f"quest-reward-{uuid4().hex}"
    experience = int(quest["reward_experience"])
    currency = int(quest["reward_currency"])
    reputation = int(quest["reward_reputation"])
    faction = str(quest["reward_faction"])
    connection.execute(
        "INSERT INTO quest_rewards(id, quest_id, campaign_id, experience, currency, "
        "reputation, faction) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (reward_id, quest["id"], campaign_id, experience, currency, reputation, faction),
    )
    try:
        raw_items = json.loads(str(quest["reward_items_json"] or "[]"))
    except (TypeError, ValueError):
        raw_items = []
    quantities: dict[str, int] = {}
    catalog_rewards = {}
    for raw in raw_items if isinstance(raw_items, list) else []:
        name = str(raw.get("name", "")) if isinstance(raw, dict) else str(raw)
        quantity = int(raw.get("quantity", 1)) if isinstance(raw, dict) else 1
        if name:
            quantities[name] = quantities.get(name, 0) + max(1, quantity)
    catalog_reward = select_loot(
        f"quest:{campaign_id}:{quest['id']}", count=1
    )[0]
    quantities[catalog_reward.name] = quantities.get(catalog_reward.name, 0) + 1
    catalog_rewards[catalog_reward.name] = catalog_reward
    for name, quantity in quantities.items():
        catalog_item = catalog_rewards.get(name)
        connection.execute(
            "INSERT INTO quest_reward_items(id, reward_id, item_key, name, quantity, "
            "rarity, description) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                f"quest-reward-item-{uuid4().hex}", reward_id,
                name.casefold().replace(" ", "_"), name, quantity,
                catalog_item.rarity if catalog_item is not None else "common",
                catalog_item.description if catalog_item is not None
                else f"Reward for completing {quest['title']}.",
            ),
        )
    _apply_reward_progression(connection, campaign_id, reward_id)


def _apply_reward_progression(
    connection: sqlite3.Connection, campaign_id: str, reward_id: str
) -> None:
    reward = connection.execute(
        "SELECT * FROM quest_rewards WHERE id = ?", (reward_id,)
    ).fetchone()
    if reward is None or bool(reward["progression_applied"]):
        return
    character = connection.execute(
        "SELECT id, level FROM characters WHERE campaign_id = ? AND is_player = 1",
        (campaign_id,),
    ).fetchone()
    if character is not None:
        award_character_experience(
            connection, str(character["id"]), int(reward["experience"])
        )
        connection.execute(
            "UPDATE characters SET currency = currency + ? WHERE id = ?",
            (reward["currency"], character["id"]),
        )
    if reward["faction"] and int(reward["reputation"]):
        connection.execute(
            "INSERT INTO faction_reputation(campaign_id, faction, score) VALUES (?, ?, ?) "
            "ON CONFLICT(campaign_id, faction) DO UPDATE SET score = score + excluded.score",
            (campaign_id, reward["faction"], reward["reputation"]),
        )
    connection.execute(
        "UPDATE quest_rewards SET progression_applied = 1 WHERE id = ?", (reward_id,)
    )


class QuestService:
    def __init__(self, database: GameStateDatabase) -> None:
        self.database = database

    def abandon(self, campaign_id: str, quest_id: str) -> str:
        with self.database.transaction() as connection:
            return abandon_quest(connection, campaign_id, quest_id)

    def claim_item(self, campaign_id: str, item_id: str) -> str:
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT quest_reward_items.*, characters.id AS character_id,
                       characters.inventory_capacity
                FROM quest_reward_items
                JOIN quest_rewards ON quest_rewards.id = quest_reward_items.reward_id
                JOIN characters ON characters.campaign_id = quest_rewards.campaign_id
                               AND characters.is_player = 1
                WHERE quest_reward_items.id = ? AND quest_rewards.campaign_id = ?
                """,
                (item_id, campaign_id),
            ).fetchone()
            if row is None or bool(row["claimed"]):
                raise GameStateError("The selected quest reward is unavailable.")
            character_id = str(row["character_id"])
            existing = connection.execute(
                "SELECT id FROM inventory_items WHERE character_id = ? AND lower(name) = lower(?) "
                "AND item_type != 'equipment' AND inventory_position IS NOT NULL LIMIT 1",
                (character_id, row["name"]),
            ).fetchone()
            if existing is not None:
                connection.execute(
                    "UPDATE inventory_items SET quantity = quantity + ? WHERE id = ?",
                    (row["quantity"], existing["id"]),
                )
            else:
                occupied = {
                    int(value[0]) for value in connection.execute(
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
                    raise GameStateError("The inventory is full; this quest reward remains unclaimed.")
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
                        definition.item_type, int(definition.consumable), definition.charges,
                        definition.maximum_charges, definition.equip_slot,
                        definition.effect_json(),
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
                "UPDATE quest_reward_items SET claimed = 1, claimed_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (item_id,),
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

    def acknowledge(self, campaign_id: str, reward_id: str) -> None:
        with self.database.transaction() as connection:
            updated = connection.execute(
                "UPDATE quest_rewards SET acknowledged = 1, acknowledged_at = CURRENT_TIMESTAMP "
                "WHERE id = ? AND campaign_id = ?",
                (reward_id, campaign_id),
            )
            if updated.rowcount != 1:
                raise GameStateError("The selected quest reward is unavailable.")
