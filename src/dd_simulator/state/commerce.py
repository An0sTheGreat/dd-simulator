"""Deterministic merchant pricing and atomic inventory transactions."""

from __future__ import annotations

from dataclasses import dataclass
import math
import sqlite3
from uuid import uuid4

from dd_simulator.state.database import GameStateDatabase
from dd_simulator.state.errors import GameStateError
from dd_simulator.state.item_actions import (
    item_definition,
    materialize_item_metadata,
    recalculate_character_item_totals,
)


RARITY_MULTIPLIERS = {
    "common": 1.0,
    "uncommon": 1.25,
    "rare": 1.75,
    "epic": 2.5,
    "legendary": 4.0,
}
DIFFICULTY_MULTIPLIERS = {
    "story": 0.9,
    "adventurer": 1.0,
    "veteran": 1.1,
    "deadly": 1.25,
    "heroic": 1.25,
}


@dataclass(frozen=True, slots=True)
class CommerceQuote:
    action: str
    npc_id: str
    item_id: str
    item_name: str
    quantity: int
    unit_price: int
    total_price: int


@dataclass(frozen=True, slots=True)
class CommerceResult:
    quote: CommerceQuote
    summary: str
    remaining_currency: int


def _condition_multiplier(durability: object, maximum: object) -> float:
    if durability is None or maximum in {None, 0}:
        return 1.0
    return 0.5 + 0.5 * max(0.0, min(1.0, int(durability) / int(maximum)))


def merchant_price(
    base_value: int,
    rarity: str,
    durability: object,
    maximum_durability: object,
    difficulty: str,
    relationship: int,
    *,
    action: str,
) -> int:
    """Return a stable whole-gold quote from authoritative item metadata."""

    value = max(1, int(base_value))
    condition = _condition_multiplier(durability, maximum_durability)
    rarity_factor = RARITY_MULTIPLIERS.get(rarity.casefold(), 1.0)
    difficulty_factor = DIFFICULTY_MULTIPLIERS.get(difficulty.casefold(), 1.0)
    relationship = max(-50, min(50, int(relationship)))
    market_value = value * rarity_factor * condition
    if action in {"buy", "barter"}:
        price = market_value * difficulty_factor * (1.0 - relationship * 0.003)
        if action == "barter":
            price *= 1.0 - min(0.15, 0.05 + max(0, relationship) / 500)
        return max(1, math.ceil(price))
    if action == "sell":
        price = market_value * (0.45 + relationship * 0.002) / difficulty_factor
        return max(1, math.floor(price))
    raise GameStateError(f"Unsupported trade action: {action}")


class CommerceService:
    def __init__(self, database: GameStateDatabase) -> None:
        self.database = database

    def quote(self, campaign_id: str, npc_id: str, action: str, item_id: str) -> CommerceQuote:
        with self.database.connect() as connection:
            return self._quote(connection, campaign_id, npc_id, action, item_id)

    def transact(
        self, campaign_id: str, npc_id: str, action: str, item_id: str
    ) -> CommerceResult:
        with self.database.transaction() as connection:
            quote = self._quote(connection, campaign_id, npc_id, action, item_id)
            character = self._character(connection, campaign_id)
            character_id = str(character["id"])
            if action in {"buy", "barter"}:
                if int(character["currency"]) < quote.total_price:
                    raise GameStateError("You do not have enough gold for that purchase.")
                stock = connection.execute(
                    "SELECT * FROM merchant_stock WHERE id = ? AND npc_id = ? AND quantity > 0",
                    (item_id, npc_id),
                ).fetchone()
                if stock is None:
                    raise GameStateError("That merchant item is no longer available.")
                self._add_player_item(connection, character, stock)
                connection.execute(
                    "UPDATE merchant_stock SET quantity = quantity - 1 WHERE id = ?",
                    (item_id,),
                )
                connection.execute(
                    "UPDATE characters SET currency = currency - ? WHERE id = ?",
                    (quote.total_price, character_id),
                )
                verb = "Bartered for" if action == "barter" else "Bought"
                summary = f"{verb} {quote.item_name} for {quote.total_price} gold."
            else:
                item = connection.execute(
                    "SELECT * FROM inventory_items WHERE id = ? AND character_id = ? "
                    "AND inventory_position IS NOT NULL",
                    (item_id, character_id),
                ).fetchone()
                if item is None:
                    raise GameStateError("That item is not available to sell.")
                if bool(item["quest_item"]) or str(item["item_type"]) == "currency":
                    raise GameStateError("Quest items and currency cannot be sold.")
                self._add_merchant_item(connection, npc_id, item)
                if int(item["quantity"]) == 1:
                    connection.execute("DELETE FROM inventory_items WHERE id = ?", (item_id,))
                else:
                    connection.execute(
                        "UPDATE inventory_items SET quantity = quantity - 1 WHERE id = ?",
                        (item_id,),
                    )
                connection.execute(
                    "UPDATE characters SET currency = currency + ? WHERE id = ?",
                    (quote.total_price, character_id),
                )
                summary = f"Sold {quote.item_name} for {quote.total_price} gold."

            connection.execute(
                "INSERT INTO commerce_transactions(" 
                "id, campaign_id, npc_id, character_id, action, item_name, quantity, unit_price, total_price" 
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"trade-{uuid4().hex}", campaign_id, npc_id, character_id,
                    action, quote.item_name, quote.quantity, quote.unit_price,
                    quote.total_price,
                ),
            )
            sequence = int(connection.execute(
                "SELECT COALESCE(MAX(sequence), -1) + 1 FROM events WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()[0])
            time_row = connection.execute(
                "SELECT time_label FROM campaign_clock WHERE campaign_id = ?", (campaign_id,)
            ).fetchone()
            connection.execute(
                "INSERT INTO events(id, campaign_id, time_label, category, summary, sequence, is_recent) "
                "VALUES (?, ?, ?, 'system', ?, ?, 0)",
                (
                    f"event-trade-{uuid4().hex}", campaign_id,
                    str(time_row["time_label"]) if time_row else "Now", summary, sequence,
                ),
            )
            recalculate_character_item_totals(connection, character_id)
            connection.execute(
                "UPDATE campaigns SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (campaign_id,),
            )
            remaining = int(connection.execute(
                "SELECT currency FROM characters WHERE id = ?", (character_id,)
            ).fetchone()[0])
        return CommerceResult(quote=quote, summary=summary, remaining_currency=remaining)

    def _quote(
        self,
        connection: sqlite3.Connection,
        campaign_id: str,
        npc_id: str,
        action: str,
        item_id: str,
    ) -> CommerceQuote:
        character = self._character(connection, campaign_id)
        npc = connection.execute(
            "SELECT npcs.id, npcs.location_id, npcs.available, npcs.status, "
            "COALESCE(relationships.score, 0) AS relationship_score "
            "FROM npcs JOIN locations ON locations.id = npcs.location_id AND locations.is_current = 1 "
            "LEFT JOIN relationships ON relationships.campaign_id = npcs.campaign_id "
            "AND relationships.source_entity_id = ? AND relationships.target_entity_id = npcs.id "
            "WHERE npcs.id = ? AND npcs.campaign_id = ?",
            (character["id"], npc_id, campaign_id),
        ).fetchone()
        if npc is None or not bool(npc["available"]) or str(npc["status"]) in {"departed", "deceased"}:
            raise GameStateError("That merchant is not available at this location.")
        difficulty_row = connection.execute(
            "SELECT difficulty FROM campaign_preferences WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()
        difficulty = "Adventurer" if difficulty_row is None else str(difficulty_row["difficulty"])
        relationship = int(npc["relationship_score"])
        if action in {"buy", "barter"}:
            row = connection.execute(
                "SELECT * FROM merchant_stock WHERE id = ? AND npc_id = ? AND quantity > 0",
                (item_id, npc_id),
            ).fetchone()
            if row is None:
                raise GameStateError("That merchant item is no longer available.")
            base_value = int(row["base_value"])
        elif action == "sell":
            row = connection.execute(
                "SELECT * FROM inventory_items WHERE id = ? AND character_id = ? "
                "AND inventory_position IS NOT NULL",
                (item_id, character["id"]),
            ).fetchone()
            if row is None:
                raise GameStateError("That item is not available to sell.")
            if bool(row["quest_item"]) or str(row["item_type"]) == "currency":
                raise GameStateError("Quest items and currency cannot be sold.")
            base_value = int(row["value_gp"])
        else:
            raise GameStateError(f"Unsupported trade action: {action}")
        price = merchant_price(
            base_value, str(row["rarity"]), row["durability"],
            row["maximum_durability"], difficulty, relationship, action=action,
        )
        return CommerceQuote(action, npc_id, item_id, str(row["name"]), 1, price, price)

    @staticmethod
    def _character(connection: sqlite3.Connection, campaign_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM characters WHERE campaign_id = ? AND is_player = 1", (campaign_id,)
        ).fetchone()
        if row is None:
            raise GameStateError("The campaign has no player character.")
        return row

    @staticmethod
    def _add_player_item(
        connection: sqlite3.Connection, character: sqlite3.Row, stock: sqlite3.Row
    ) -> None:
        character_id = str(character["id"])
        definition = item_definition(str(stock["name"]))
        stack = None
        if definition.item_type != "equipment":
            stack = connection.execute(
                "SELECT id FROM inventory_items WHERE character_id = ? "
                "AND inventory_position IS NOT NULL AND lower(name) = lower(?) AND rarity = ? "
                "AND durability IS NULL AND charges IS NULL LIMIT 1",
                (character_id, stock["name"], stock["rarity"]),
            ).fetchone()
        if stack is not None:
            connection.execute(
                "UPDATE inventory_items SET quantity = quantity + 1 WHERE id = ?", (stack["id"],)
            )
            return
        occupied = {
            int(row[0]) for row in connection.execute(
                "SELECT inventory_position FROM inventory_items WHERE character_id = ? "
                "AND inventory_position IS NOT NULL", (character_id,)
            )
        }
        position = next(
            (index for index in range(int(character["inventory_capacity"])) if index not in occupied),
            None,
        )
        if position is None:
            raise GameStateError("Your inventory is full.")
        slot_index = int(connection.execute(
            "SELECT COALESCE(MAX(slot_index), -1) + 1 FROM inventory_items WHERE character_id = ?",
            (character_id,),
        ).fetchone()[0])
        item_id = f"item-{uuid4().hex}"
        connection.execute(
            "INSERT INTO inventory_items(" 
            "id, character_id, slot_index, inventory_position, name, quantity, rarity, durability, "
            "maximum_durability, quest_item, selected, description" 
            ") VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, 0, 0, ?)",
            (
                item_id, character_id, slot_index, position, stock["name"], stock["rarity"],
                stock["durability"], stock["maximum_durability"], stock["description"],
            ),
        )
        materialize_item_metadata(connection, item_id, difficulty="Adventurer")

    @staticmethod
    def _add_merchant_item(
        connection: sqlite3.Connection, npc_id: str, item: sqlite3.Row
    ) -> None:
        existing = connection.execute(
            "SELECT id FROM merchant_stock WHERE npc_id = ? AND lower(name) = lower(?) "
            "AND rarity = ? AND COALESCE(durability, -1) = COALESCE(?, -1) LIMIT 1",
            (npc_id, item["name"], item["rarity"], item["durability"]),
        ).fetchone()
        if existing is not None:
            connection.execute(
                "UPDATE merchant_stock SET quantity = quantity + 1 WHERE id = ?", (existing["id"],)
            )
            return
        order = int(connection.execute(
            "SELECT COALESCE(MAX(display_order), -1) + 1 FROM merchant_stock WHERE npc_id = ?",
            (npc_id,),
        ).fetchone()[0])
        connection.execute(
            "INSERT INTO merchant_stock(" 
            "id, npc_id, name, quantity, rarity, durability, maximum_durability, "
            "base_value, description, display_order" 
            ") VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)",
            (
                f"stock-{uuid4().hex}", npc_id, item["name"], item["rarity"],
                item["durability"], item["maximum_durability"], item["value_gp"],
                item["description"], order,
            ),
        )
