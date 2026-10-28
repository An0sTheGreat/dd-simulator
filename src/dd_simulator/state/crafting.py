"""Deterministic recipe validation and atomic crafting resolution."""

from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from uuid import uuid4

from dd_simulator.state.database import GameStateDatabase
from dd_simulator.state.errors import GameStateError
from dd_simulator.state.item_actions import (
    item_definition,
    materialize_item_metadata,
    recalculate_character_item_totals,
)


RECIPE_TEMPLATES = (
    (
        "field-bandages", "Field Bandages",
        "Cut and bind clean cloth into dependable field dressings.",
        20, "Bandages", 2, "common", 12, "", 0, (("Cloth", 2),),
    ),
    (
        "health-potion", "Restorative Draught",
        "Steep medicinal herbs in clean water to produce a healing potion.",
        30, "Health Potion", 1, "common", 25, "Healer's Kit", 1,
        (("Herbs", 2), ("Water Flask", 1)),
    ),
    (
        "lockpick-set", "Lockpick Set",
        "Shape narrow iron scraps into a matched set of lockpicks.",
        38, "Lockpick", 3, "common", 30, "Flint & Steel", 1,
        (("Iron Scraps", 2),),
    ),
)


@dataclass(frozen=True, slots=True)
class CraftingResult:
    id: str
    recipe_id: str
    recipe_name: str
    success: bool
    score: int
    difficulty: int
    output_name: str
    output_quantity: int
    output_rarity: str
    quality: str
    ingredients_consumed: tuple[tuple[str, int], ...]
    tool_uses: tuple[tuple[str, int], ...]
    crafting_xp: int
    summary: str


def seed_crafting_recipes(connection: sqlite3.Connection, campaign_id: str) -> None:
    for order, template in enumerate(RECIPE_TEMPLATES):
        (
            key, name, description, difficulty, output_name, output_quantity,
            output_rarity, xp, tool_name, tool_cost, ingredients,
        ) = template
        recipe_id = f"recipe-{campaign_id}-{key}"
        connection.execute(
            "INSERT OR IGNORE INTO crafting_recipes(" 
            "id, campaign_id, name, description, skill_name, difficulty, output_name, "
            "output_quantity, output_rarity, crafting_xp, required_tool, tool_use_cost, "
            "unlocked, display_order" 
            ") VALUES (?, ?, ?, ?, 'Crafting', ?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (
                recipe_id, campaign_id, name, description, difficulty, output_name,
                output_quantity, output_rarity, xp, tool_name, tool_cost, order,
            ),
        )
        for ingredient_order, (ingredient, quantity) in enumerate(ingredients):
            connection.execute(
                "INSERT OR IGNORE INTO crafting_recipe_ingredients(" 
                "id, recipe_id, item_name, quantity, display_order" 
                ") VALUES (?, ?, ?, ?, ?)",
                (
                    f"ingredient-{campaign_id}-{key}-{ingredient_order}", recipe_id,
                    ingredient, quantity, ingredient_order,
                ),
            )


class CraftingService:
    def __init__(self, database: GameStateDatabase) -> None:
        self.database = database

    def craft(self, campaign_id: str, recipe_id: str) -> CraftingResult:
        with self.database.transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM crafting_results WHERE campaign_id = ? AND acknowledged = 0",
                (campaign_id,),
            ).fetchone() is not None:
                raise GameStateError("A previous crafting result must be acknowledged first.")
            recipe = connection.execute(
                "SELECT * FROM crafting_recipes WHERE id = ? AND campaign_id = ? AND unlocked = 1",
                (recipe_id, campaign_id),
            ).fetchone()
            if recipe is None:
                raise GameStateError("That crafting recipe is unavailable.")
            character = connection.execute(
                "SELECT characters.*, COALESCE(campaign_preferences.difficulty, 'Adventurer') "
                "AS campaign_difficulty FROM characters LEFT JOIN campaign_preferences "
                "ON campaign_preferences.campaign_id = characters.campaign_id "
                "WHERE characters.campaign_id = ? AND characters.is_player = 1",
                (campaign_id,),
            ).fetchone()
            if character is None:
                raise GameStateError("The campaign has no player character.")
            skill = connection.execute(
                "SELECT * FROM skills WHERE character_id = ? AND lower(name) = lower(?)",
                (character["id"], recipe["skill_name"]),
            ).fetchone()
            if skill is None or bool(skill["locked"]):
                raise GameStateError("The required crafting skill is unavailable.")
            ingredients = connection.execute(
                "SELECT * FROM crafting_recipe_ingredients WHERE recipe_id = ? "
                "ORDER BY display_order, id",
                (recipe_id,),
            ).fetchall()
            ingredient_rows: dict[str, list[sqlite3.Row]] = {}
            for ingredient in ingredients:
                rows = connection.execute(
                    "SELECT * FROM inventory_items WHERE character_id = ? "
                    "AND inventory_position IS NOT NULL AND lower(name) = lower(?) "
                    "ORDER BY inventory_position",
                    (character["id"], ingredient["item_name"]),
                ).fetchall()
                if sum(int(row["quantity"]) for row in rows) < int(ingredient["quantity"]):
                    raise GameStateError(
                        f"Crafting requires {ingredient['quantity']} x {ingredient['item_name']}."
                    )
                ingredient_rows[str(ingredient["item_name"])] = list(rows)

            tool = None
            tool_name = str(recipe["required_tool"])
            tool_cost = int(recipe["tool_use_cost"])
            if tool_name:
                tool = connection.execute(
                    "SELECT * FROM inventory_items WHERE character_id = ? "
                    "AND inventory_position IS NOT NULL AND lower(name) = lower(?) "
                    "ORDER BY inventory_position LIMIT 1",
                    (character["id"], tool_name),
                ).fetchone()
                if tool is None:
                    raise GameStateError(f"Crafting requires {tool_name}.")
                if tool["charges"] is not None and int(tool["charges"]) < tool_cost:
                    raise GameStateError(f"{tool_name} does not have enough uses remaining.")
                if tool["durability"] is not None and int(tool["durability"]) < tool_cost:
                    raise GameStateError(f"{tool_name} does not have enough durability remaining.")

            equipment_bonuses = json.loads(str(character["equipment_bonuses_json"]))
            equipment_bonus = int(equipment_bonuses.get("crafting", 0))
            score = int(skill["level"]) + int(skill["bonus"]) + equipment_bonus
            difficulty_modifier = {
                "story": -5, "adventurer": 0, "veteran": 5,
                "deadly": 10, "custom": 5,
            }.get(str(character["campaign_difficulty"]).casefold(), 0)
            target = int(recipe["difficulty"]) + difficulty_modifier
            success = score >= target
            margin = score - target
            quality, rarity = self._quality(str(recipe["output_rarity"]), margin, success)
            consumed: tuple[tuple[str, int], ...] = ()
            tool_uses: tuple[tuple[str, int], ...] = ()
            output_name = str(recipe["output_name"]) if success else ""
            output_quantity = int(recipe["output_quantity"]) if success else 0
            if success:
                self._ensure_output_capacity(
                    connection, character, output_name, rarity
                )
                for ingredient in ingredients:
                    name = str(ingredient["item_name"])
                    self._consume_rows(
                        connection, ingredient_rows[name], int(ingredient["quantity"])
                    )
                consumed = tuple(
                    (str(row["item_name"]), int(row["quantity"])) for row in ingredients
                )
                if tool is not None and tool_cost:
                    if tool["charges"] is not None:
                        connection.execute(
                            "UPDATE inventory_items SET charges = charges - ? WHERE id = ?",
                            (tool_cost, tool["id"]),
                        )
                    elif tool["durability"] is not None:
                        connection.execute(
                            "UPDATE inventory_items SET durability = durability - ? WHERE id = ?",
                            (tool_cost, tool["id"]),
                        )
                    tool_uses = ((tool_name, tool_cost),)
                self._add_output(
                    connection, character, output_name, output_quantity, rarity,
                    str(character["campaign_difficulty"]),
                )

            xp = int(recipe["crafting_xp"]) if success else max(1, int(recipe["crafting_xp"]) // 4)
            self._award_skill_xp(connection, skill, xp)
            result_id = f"craft-{uuid4().hex}"
            summary = (
                f"Crafted {output_quantity} x {output_name} ({quality})."
                if success else f"Crafting attempt failed: {recipe['name']}."
            )
            connection.execute(
                "INSERT INTO crafting_results(" 
                "id, campaign_id, character_id, recipe_id, recipe_name, status, score, "
                "difficulty, output_name, output_quantity, output_rarity, quality, "
                "ingredients_consumed_json, tool_uses_json, crafting_xp, summary" 
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    result_id, campaign_id, character["id"], recipe_id, recipe["name"],
                    "success" if success else "failure", score, target, output_name,
                    output_quantity, rarity if success else "", quality,
                    json.dumps(consumed, separators=(",", ":")),
                    json.dumps(tool_uses, separators=(",", ":")), xp, summary,
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
                    f"event-craft-{uuid4().hex}", campaign_id,
                    str(time_row["time_label"]) if time_row else "Now", summary, sequence,
                ),
            )
            recalculate_character_item_totals(connection, str(character["id"]))
            connection.execute(
                "UPDATE campaigns SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (campaign_id,),
            )
        return CraftingResult(
            result_id, recipe_id, str(recipe["name"]), success, score, target,
            output_name, output_quantity, rarity if success else "", quality,
            consumed, tool_uses, xp, summary,
        )

    def acknowledge(self, campaign_id: str, result_id: str) -> None:
        with self.database.transaction() as connection:
            updated = connection.execute(
                "UPDATE crafting_results SET acknowledged = 1, acknowledged_at = CURRENT_TIMESTAMP "
                "WHERE id = ? AND campaign_id = ? AND acknowledged = 0",
                (result_id, campaign_id),
            )
            if updated.rowcount != 1:
                raise GameStateError("That crafting result is unavailable.")

    @staticmethod
    def _quality(base_rarity: str, margin: int, success: bool) -> tuple[str, str]:
        if not success:
            return "Failed", ""
        rarities = ["common", "uncommon", "rare", "epic", "legendary"]
        base = base_rarity.casefold() if base_rarity.casefold() in rarities else "common"
        steps = 2 if margin >= 25 else 1 if margin >= 10 else 0
        rarity = rarities[min(len(rarities) - 1, rarities.index(base) + steps)]
        quality = "Masterwork" if steps == 2 else "Fine" if steps == 1 else "Standard"
        return quality, rarity

    @staticmethod
    def _consume_rows(
        connection: sqlite3.Connection, rows: list[sqlite3.Row], quantity: int
    ) -> None:
        remaining = quantity
        for row in rows:
            take = min(remaining, int(row["quantity"]))
            if take == int(row["quantity"]):
                connection.execute("DELETE FROM inventory_items WHERE id = ?", (row["id"],))
            else:
                connection.execute(
                    "UPDATE inventory_items SET quantity = quantity - ? WHERE id = ?",
                    (take, row["id"]),
                )
            remaining -= take
            if remaining == 0:
                return

    @staticmethod
    def _ensure_output_capacity(
        connection: sqlite3.Connection,
        character: sqlite3.Row,
        output_name: str,
        rarity: str,
    ) -> None:
        definition = item_definition(output_name)
        if definition.item_type != "equipment" and connection.execute(
            "SELECT 1 FROM inventory_items WHERE character_id = ? "
            "AND inventory_position IS NOT NULL AND lower(name) = lower(?) AND rarity = ? "
            "AND durability IS NULL AND charges IS NULL LIMIT 1",
            (character["id"], output_name, rarity),
        ).fetchone() is not None:
            return
        occupied = int(connection.execute(
            "SELECT COUNT(*) FROM inventory_items WHERE character_id = ? "
            "AND inventory_position IS NOT NULL", (character["id"],)
        ).fetchone()[0])
        if occupied >= int(character["inventory_capacity"]):
            raise GameStateError("Your inventory needs an empty slot for the crafted item.")

    @staticmethod
    def _add_output(
        connection: sqlite3.Connection,
        character: sqlite3.Row,
        name: str,
        quantity: int,
        rarity: str,
        difficulty: str,
    ) -> None:
        definition = item_definition(name)
        stack = None
        if definition.item_type != "equipment":
            stack = connection.execute(
                "SELECT id FROM inventory_items WHERE character_id = ? "
                "AND inventory_position IS NOT NULL AND lower(name) = lower(?) AND rarity = ? "
                "AND durability IS NULL AND charges IS NULL LIMIT 1",
                (character["id"], name, rarity),
            ).fetchone()
        if stack is not None:
            connection.execute(
                "UPDATE inventory_items SET quantity = quantity + ? WHERE id = ?",
                (quantity, stack["id"]),
            )
            return
        occupied = {
            int(row[0]) for row in connection.execute(
                "SELECT inventory_position FROM inventory_items WHERE character_id = ? "
                "AND inventory_position IS NOT NULL", (character["id"],)
            )
        }
        position = next(
            index for index in range(int(character["inventory_capacity"])) if index not in occupied
        )
        slot_index = int(connection.execute(
            "SELECT COALESCE(MAX(slot_index), -1) + 1 FROM inventory_items WHERE character_id = ?",
            (character["id"],),
        ).fetchone()[0])
        item_id = f"item-{uuid4().hex}"
        connection.execute(
            "INSERT INTO inventory_items(" 
            "id, character_id, slot_index, inventory_position, name, quantity, rarity, description" 
            ") VALUES (?, ?, ?, ?, ?, ?, ?, 'Crafted by the player.')",
            (item_id, character["id"], slot_index, position, name, quantity, rarity),
        )
        materialize_item_metadata(connection, item_id, difficulty=difficulty)

    @staticmethod
    def _award_skill_xp(
        connection: sqlite3.Connection, skill: sqlite3.Row, amount: int
    ) -> None:
        level = int(skill["level"])
        current = int(skill["current_xp"]) + amount
        threshold = int(skill["next_level_xp"])
        increased = 0
        while threshold > 0 and current >= threshold:
            current -= threshold
            level += 1
            threshold = max(threshold + 25, round(threshold * 1.2))
            increased = 1
        connection.execute(
            "UPDATE skills SET level = ?, current_xp = ?, next_level_xp = ?, "
            "recently_increased = ? WHERE id = ?",
            (level, current, threshold, increased, skill["id"]),
        )
