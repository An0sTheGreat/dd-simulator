"""Typed inventory commands and deterministic item catalog rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
import sqlite3
from typing import Any

from dd_simulator.state.item_catalog import catalog_item


class ItemAction(StrEnum):
    USE = "use"
    EQUIP = "equip"
    UNEQUIP = "unequip"
    DROP = "drop"


@dataclass(frozen=True, slots=True)
class ItemCommand:
    action: ItemAction
    slot_index: int
    destination_index: int | None = None


@dataclass(frozen=True, slots=True)
class ItemMutationResult:
    action: ItemAction
    item_name: str
    summary: str


@dataclass(frozen=True, slots=True)
class ItemDefinition:
    item_type: str = "misc"
    consumable: bool = False
    charges: int | None = None
    maximum_charges: int | None = None
    equip_slot: str = ""
    resource_effects: tuple[tuple[str, int], ...] = ()
    remove_statuses: tuple[str, ...] = ()
    use_summary: str = ""
    category: str = "misc"
    weight: float = 0.1
    value_gp: int = 1
    damage: str = ""
    armor: int = 0
    compatible_slots: tuple[str, ...] = ()
    requirements: tuple[tuple[str, object], ...] = ()
    bonuses: tuple[tuple[str, int], ...] = ()
    penalties: tuple[tuple[str, int], ...] = ()
    description: str = ""

    def effect_json(self) -> str:
        if not self.resource_effects and not self.remove_statuses and not self.use_summary:
            return "{}"
        return json.dumps(
            {
                "resources": dict(self.resource_effects),
                "remove_statuses": self.remove_statuses,
                "use_summary": self.use_summary,
            },
            separators=(",", ":"),
        )


_WEAPONS = {
    "iron dagger", "longsword", "shortsword", "battleaxe", "warhammer",
    "spear", "quarterstaff", "dagger", "mace", "rapier", "greatsword",
    "handaxe", "wand", "parrying blade", "shortbow", "longbow",
    "light crossbow", "heavy crossbow", "throwing knives", "sling",
}
_SHIELDS = {"oak shield", "wooden shield", "round shield", "kite shield", "buckler"}
_BODY_ARMOR = {
    "traveling clothes", "padded armor", "leather armor", "studded leather",
    "chain shirt", "scale mail", "chain mail", "mage robes", "druidic leathers",
    "warden coat",
}

_WEAPON_DETAILS: dict[str, tuple[str, float, int, tuple[str, ...]]] = {
    "iron dagger": ("1d4 piercing", 1.0, 2, ("Main Hand", "Off Hand")),
    "dagger": ("1d4 piercing", 1.0, 2, ("Main Hand", "Off Hand")),
    "shortsword": ("1d6 piercing", 2.0, 10, ("Main Hand", "Off Hand")),
    "longsword": ("1d8 slashing", 3.0, 15, ("Main Hand", "Off Hand")),
    "rapier": ("1d8 piercing", 2.0, 25, ("Main Hand", "Off Hand")),
    "handaxe": ("1d6 slashing", 2.0, 5, ("Main Hand", "Off Hand")),
    "battleaxe": ("1d8 slashing", 4.0, 10, ("Main Hand", "Off Hand")),
    "mace": ("1d6 bludgeoning", 4.0, 5, ("Main Hand", "Off Hand")),
    "warhammer": ("1d8 bludgeoning", 5.0, 15, ("Main Hand", "Off Hand")),
    "spear": ("1d6 piercing", 3.0, 1, ("Main Hand", "Off Hand")),
    "quarterstaff": ("1d6 bludgeoning", 4.0, 1, ("Main Hand", "Off Hand")),
    "greatsword": ("2d6 slashing", 6.0, 50, ("Main Hand",)),
    "shortbow": ("1d6 piercing", 2.0, 25, ("Main Hand",)),
    "longbow": ("1d8 piercing", 2.0, 50, ("Main Hand",)),
    "light crossbow": ("1d8 piercing", 5.0, 25, ("Main Hand",)),
    "heavy crossbow": ("1d10 piercing", 18.0, 50, ("Main Hand",)),
    "sling": ("1d4 bludgeoning", 0.2, 1, ("Main Hand",)),
    "throwing knives": ("1d4 piercing", 1.0, 5, ("Main Hand", "Off Hand")),
    "wand": ("1d6 arcane", 1.0, 10, ("Main Hand", "Off Hand")),
    "parrying blade": ("1d6 piercing", 2.0, 20, ("Main Hand", "Off Hand")),
}

_ARMOR_DETAILS: dict[str, tuple[int, float, int]] = {
    "traveling clothes": (0, 3.0, 2),
    "padded armor": (1, 8.0, 5),
    "leather armor": (2, 10.0, 10),
    "studded leather": (3, 13.0, 45),
    "chain shirt": (4, 20.0, 50),
    "scale mail": (5, 45.0, 50),
    "chain mail": (6, 55.0, 75),
    "mage robes": (1, 4.0, 15),
    "druidic leathers": (3, 12.0, 35),
    "warden coat": (1, 8.0, 25),
}

_UTILITY_DETAILS: dict[str, tuple[str, float, int, str]] = {
    "lockpick": ("tool", 0.1, 5, "Used to open locked doors, chests, and other secured mechanisms."),
    "rope": ("tool", 10.0, 1, "A sturdy length of rope for climbing, binding, and securing gear."),
    "torch": ("travel", 1.0, 1, "Provides light in dark places until consumed."),
    "flint & steel": ("tool", 0.2, 5, "Produces sparks for lighting fires and torches."),
    "map fragment": ("quest", 0.1, 0, "A partial map whose markings may reveal a hidden route."),
    "merchant letter": ("quest", 0.1, 0, "A sealed letter connected to the roadside merchant."),
    "gold": ("currency", 0.0172, 1, "Standard currency accepted by most merchants."),
    "travel rations": ("travel", 2.0, 1, "Preserved food that restores stamina during a journey."),
    "water flask": ("travel", 2.0, 1, "A refillable flask used to stay hydrated while traveling."),
    "bandages": ("consumable", 0.5, 2, "Clean bandages used to treat minor injuries."),
    "antidote": ("consumable", 0.5, 25, "Neutralizes common poisons when used in time."),
    "health potion": ("potion", 0.5, 50, "A restorative potion that heals wounds when consumed."),
    "healer's kit": ("tool", 3.0, 25, "A compact kit of salves and dressings for treating wounds."),
    "arrows": ("ammunition", 0.05, 1, "Ammunition used by bows."),
    "bolts": ("ammunition", 0.075, 1, "Ammunition used by crossbows."),
    "sling stones": ("ammunition", 0.1, 0, "Smooth stones selected as sling ammunition."),
    "cloth": ("crafting", 0.2, 1, "Clean cloth suitable for crafting and field repairs."),
    "herbs": ("crafting", 0.1, 2, "Medicinal herbs used in restorative recipes."),
    "iron scraps": ("crafting", 0.5, 1, "Small iron pieces ready to be reshaped."),
}

_SPECIAL: dict[str, ItemDefinition] = {
    "gold": ItemDefinition(item_type="currency", category="currency", weight=0.0172),
    "map fragment": ItemDefinition(item_type="quest", category="quest", weight=0.1, value_gp=0),
    "merchant letter": ItemDefinition(item_type="quest", category="quest", weight=0.1, value_gp=0),
    "health potion": ItemDefinition(
        item_type="consumable",
        consumable=True,
        resource_effects=(("health", 15),),
        use_summary="Drank a Health Potion.",
        category="potion", weight=0.5, value_gp=50,
    ),
    "bandages": ItemDefinition(
        item_type="consumable",
        consumable=True,
        resource_effects=(("health", 8),),
        use_summary="Applied Bandages.",
        category="consumable", weight=0.5, value_gp=2,
    ),
    "travel rations": ItemDefinition(
        item_type="consumable",
        consumable=True,
        resource_effects=(("stamina", 6),),
        use_summary="Ate Travel Rations.",
        category="travel", weight=2.0, value_gp=1,
    ),
    "water flask": ItemDefinition(
        item_type="consumable",
        consumable=True,
        resource_effects=(("stamina", 2),),
        use_summary="Drank from a Water Flask.",
        category="travel", weight=2.0, value_gp=1,
    ),
    "antidote": ItemDefinition(
        item_type="consumable",
        consumable=True,
        remove_statuses=("Poisoned",),
        use_summary="Used an Antidote.",
        category="consumable", weight=0.5, value_gp=25,
    ),
    "torch": ItemDefinition(
        item_type="consumable",
        consumable=True,
        use_summary="Lit a Torch.",
        category="travel", weight=1.0, value_gp=1,
    ),
    "flint & steel": ItemDefinition(
        item_type="charged",
        charges=20,
        maximum_charges=20,
        use_summary="Struck Flint & Steel.",
        category="tool", weight=0.2, value_gp=5,
    ),
    "healer's kit": ItemDefinition(
        item_type="charged",
        charges=5,
        maximum_charges=5,
        resource_effects=(("health", 5),),
        use_summary="Used the Healer's Kit.",
        category="tool", weight=3.0, value_gp=25,
    ),
    "silver ring": ItemDefinition(item_type="equipment", equip_slot="Ring", category="jewelry", weight=0.1, value_gp=25, compatible_slots=("Ring",)),
    "signet ring": ItemDefinition(item_type="equipment", equip_slot="Ring", category="jewelry", weight=0.1, value_gp=20, compatible_slots=("Ring",)),
    "family locket": ItemDefinition(item_type="equipment", equip_slot="Neck", category="jewelry", weight=0.2, value_gp=15, compatible_slots=("Neck",)),
    "prayer beads": ItemDefinition(item_type="equipment", equip_slot="Neck", category="jewelry", weight=0.2, value_gp=10, compatible_slots=("Neck",)),
    "arrows": ItemDefinition(item_type="equipment", equip_slot="Ammunition", category="ammunition", weight=0.05, value_gp=1, compatible_slots=("Ammunition",)),
    "bolts": ItemDefinition(item_type="equipment", equip_slot="Ammunition", category="ammunition", weight=0.075, value_gp=1, compatible_slots=("Ammunition",)),
    "sling stones": ItemDefinition(item_type="equipment", equip_slot="Ammunition", category="ammunition", weight=0.1, value_gp=0, compatible_slots=("Ammunition",)),
}


def item_definition(name: str) -> ItemDefinition:
    normalized = " ".join(name.lower().split())
    special = _SPECIAL.get(normalized)
    if special is not None:
        return special
    if normalized in _SHIELDS:
        return ItemDefinition(
            item_type="equipment", equip_slot="Off Hand", category="shield",
            weight=6.0, value_gp=10, armor=2, compatible_slots=("Off Hand",),
            bonuses=(("armor", 2),),
        )
    if normalized in _BODY_ARMOR:
        armor, weight, value_gp = _ARMOR_DETAILS.get(normalized, (1, 8.0, 10))
        return ItemDefinition(
            item_type="equipment", equip_slot="Body", category="armor",
            weight=weight, value_gp=value_gp, armor=armor,
            compatible_slots=("Body",), bonuses=(("armor", armor),),
        )
    if normalized in _WEAPONS:
        damage, weight, value_gp, slots = _WEAPON_DETAILS.get(
            normalized, ("1d6", 3.0, 5, ("Main Hand", "Off Hand"))
        )
        return ItemDefinition(
            item_type="equipment", equip_slot="Main Hand", category="weapon",
            weight=weight, value_gp=value_gp, damage=damage,
            compatible_slots=slots,
        )
    catalog = catalog_item(normalized)
    if catalog is not None:
        tags = set(catalog.tags)
        description = catalog.description
        if catalog.category == "weapon":
            if catalog.subtype == "arrow":
                return ItemDefinition(
                    item_type="equipment", equip_slot="Ammunition",
                    category="ammunition", weight=0.05, value_gp=1,
                    compatible_slots=("Ammunition",), description=description,
                )
            two_handed = catalog.subtype in {
                "bow", "crossbow", "greataxe", "greatsword", "staff", "scythe"
            }
            die = (6, 8, 10, 12, 12)[catalog.tier]
            return ItemDefinition(
                item_type="equipment", equip_slot="Main Hand", category="weapon",
                weight=4.0 if two_handed else 2.0,
                value_gp=5 * (catalog.tier + 1), damage=f"1d{die}",
                compatible_slots=("Main Hand",) if two_handed else ("Main Hand", "Off Hand"),
                description=description,
            )
        if catalog.category == "armor" and catalog.subtype != "shield":
            slot = {
                "helmet": "Head", "hat": "Head", "hood": "Head",
                "gloves": "Hands", "gauntlets": "Hands", "boots": "Feet",
                "ring": "Ring", "amulet": "Neck", "necklace": "Neck",
            }.get(catalog.subtype, "Body")
            armor = 0 if slot in {"Ring", "Neck"} else max(1, catalog.tier + 1)
            return ItemDefinition(
                item_type="equipment", equip_slot=slot, category="armor",
                weight=0.2 if slot in {"Ring", "Neck"} else 2.0 + armor * 2,
                value_gp=8 * (catalog.tier + 1), armor=armor,
                compatible_slots=(slot,), bonuses=(("armor", armor),) if armor else (),
                description=description,
            )
        if catalog.subtype == "shield":
            return ItemDefinition(
                item_type="equipment", equip_slot="Off Hand", category="shield",
                weight=5.0, value_gp=10 * (catalog.tier + 1), armor=2 + catalog.tier,
                compatible_slots=("Off Hand",), bonuses=(("armor", 2 + catalog.tier),),
                description=description,
            )
        if catalog.category in {"potion", "food", "consumable"}:
            healing = 5 + catalog.tier * 5 if "healing" in tags or "healing" in normalized else 0
            return ItemDefinition(
                item_type="consumable", consumable=True, category=catalog.category,
                weight=0.5, value_gp=5 * (catalog.tier + 1),
                resource_effects=(("health", healing),) if healing else (),
                use_summary=f"Used {catalog.name}.", description=description,
            )
        return ItemDefinition(
            item_type="currency" if catalog.category == "currency" else "misc",
            category=catalog.category, weight=0.1,
            value_gp=max(1, 3 * (catalog.tier + 1)), description=description,
        )
    utility = _UTILITY_DETAILS.get(normalized)
    if utility is not None:
        category, weight, value_gp, description = utility
        return ItemDefinition(
            item_type=(
                category
                if category in {"consumable", "charged", "equipment", "quest", "currency", "tool"}
                else "misc"
            ),
            category=category, weight=weight, value_gp=value_gp,
            description=description,
        )
    if any(word in normalized for word in ("gloves", "gauntlets")):
        return ItemDefinition(item_type="equipment", equip_slot="Hands", category="armor", weight=1.0, value_gp=5, compatible_slots=("Hands",))
    if any(word in normalized for word in ("boots", "shoes")):
        return ItemDefinition(item_type="equipment", equip_slot="Feet", category="armor", weight=2.0, value_gp=5, compatible_slots=("Feet",))
    if any(word in normalized for word in ("helm", "helmet", "hood")):
        return ItemDefinition(item_type="equipment", equip_slot="Head", category="armor", weight=3.0, value_gp=10, armor=1, compatible_slots=("Head",), bonuses=(("armor", 1),))
    if any(word in normalized for word in ("amulet", "charm", "necklace")):
        return ItemDefinition(item_type="equipment", equip_slot="Neck", category="jewelry", weight=0.2, value_gp=10, compatible_slots=("Neck",))
    return ItemDefinition(description=f"A {name.strip() or 'miscellaneous item'} carried for use during the adventure.")


def build_item_metadata(
    name: str,
    *,
    rarity: str = "common",
    difficulty: str = "Adventurer",
    description: str = "",
) -> dict[str, object]:
    """Return stable application-owned mechanics for one item identity."""

    definition = item_definition(name)
    rarity_key = rarity.casefold()
    value_factor = {
        "common": 1, "uncommon": 2, "rare": 5, "epic": 12, "legendary": 25,
    }.get(rarity_key, 1)
    bonus_step = {
        "common": 0, "uncommon": 0, "rare": 1, "epic": 2, "legendary": 3,
    }.get(rarity_key, 0)
    difficulty_key = difficulty.casefold()
    healing_factor = {
        "story": 1.2, "adventurer": 1.0, "veteran": 0.9, "deadly": 0.8,
    }.get(difficulty_key, 1.0)
    effects = dict(definition.resource_effects)
    healing = max(0, round(int(effects.get("health", 0)) * healing_factor))
    bonuses = dict(definition.bonuses)
    if bonus_step and definition.category in {"weapon", "armor", "shield", "jewelry"}:
        key = "attack" if definition.category == "weapon" else "armor"
        bonuses[key] = bonuses.get(key, 0) + bonus_step
    seed = int.from_bytes(
        sha256(f"{name.casefold()}|{rarity_key}|{difficulty_key}".encode("utf-8")).digest()[:2],
        "big",
    )
    mechanical_description = definition.description
    if not mechanical_description:
        if definition.damage:
            mechanical_description = f"A {definition.category} dealing {definition.damage}."
        elif definition.armor:
            mechanical_description = f"Protective {definition.category} that grants {definition.armor} armor."
        elif definition.equip_slot:
            mechanical_description = f"Equipment worn in the {definition.equip_slot.lower()} slot."
        else:
            mechanical_description = f"A {definition.category} used during the adventure."
    authored = description.strip()
    if authored.casefold() in {"starting equipment", "unequipped equipment"}:
        authored = ""
    return {
        "item_category": definition.category,
        "weight": definition.weight,
        "value_gp": max(0, definition.value_gp * value_factor),
        "identified": 0 if rarity_key in {"epic", "legendary"} and seed % 5 == 0 else 1,
        "damage_text": definition.damage,
        "armor_value": definition.armor + (bonus_step if definition.armor else 0),
        "healing_value": healing,
        "compatible_slots_json": json.dumps(definition.compatible_slots, separators=(",", ":")),
        "requirements_json": json.dumps(dict(definition.requirements), separators=(",", ":")),
        "bonuses_json": json.dumps(bonuses, separators=(",", ":")),
        "penalties_json": json.dumps(dict(definition.penalties), separators=(",", ":")),
        "generated_difficulty": difficulty,
        "item_generation_version": 1,
        "description": authored or mechanical_description,
    }


def materialize_item_metadata(
    connection: sqlite3.Connection,
    item_id: str,
    *,
    difficulty: str = "Adventurer",
) -> None:
    row = connection.execute(
        "SELECT * FROM inventory_items WHERE id = ?", (item_id,)
    ).fetchone()
    if row is None:
        return
    metadata = build_item_metadata(
        str(row["name"]), rarity=str(row["rarity"]), difficulty=difficulty,
        description=str(row["description"]),
    )
    assignments = ", ".join(f"{key} = ?" for key in metadata)
    connection.execute(
        f"UPDATE inventory_items SET {assignments} WHERE id = ?",
        (*metadata.values(), item_id),
    )
    definition = item_definition(str(row["name"]))
    effect_json = definition.effect_json()
    if definition.resource_effects:
        effects = decode_effects(effect_json)
        resources = effects.get("resources")
        if isinstance(resources, dict) and "health" in resources:
            resources["health"] = int(metadata["healing_value"])
            effect_json = json.dumps(effects, separators=(",", ":"))
    if definition.item_type != "misc":
        connection.execute(
            "UPDATE inventory_items SET item_type = ?, consumable = ?, "
            "charges = COALESCE(charges, ?), maximum_charges = COALESCE(maximum_charges, ?), "
            "equip_slot = CASE WHEN equip_slot = '' THEN ? ELSE equip_slot END, "
            "use_effect_json = CASE WHEN ? != '{}' THEN ? ELSE use_effect_json END "
            "WHERE id = ?",
            (
                definition.item_type, int(definition.consumable), definition.charges,
                definition.maximum_charges, definition.equip_slot,
                effect_json, effect_json, item_id,
            ),
        )
    if definition.equip_slot and row["maximum_durability"] is None:
        durability = 82 + int.from_bytes(sha256(item_id.encode("utf-8")).digest()[:1], "big") % 19
        connection.execute(
            "UPDATE inventory_items SET durability = COALESCE(durability, ?), "
            "maximum_durability = COALESCE(maximum_durability, 100) WHERE id = ?",
            (durability, item_id),
        )


def backfill_item_metadata(connection: sqlite3.Connection) -> None:
    legacy_equipment = connection.execute(
        "SELECT equipment_slots.*, characters.campaign_id FROM equipment_slots "
        "JOIN characters ON characters.id = equipment_slots.character_id "
        "WHERE equipment_slots.item_name IS NOT NULL "
        "AND equipment_slots.inventory_item_id IS NULL"
    ).fetchall()
    for slot in legacy_equipment:
        item_id = "item-equipped-" + sha256(str(slot["id"]).encode("utf-8")).hexdigest()[:16]
        legacy_index = int(connection.execute(
            "SELECT COALESCE(MAX(slot_index), -1) + 1 FROM inventory_items WHERE character_id = ?",
            (slot["character_id"],),
        ).fetchone()[0])
        condition = str(slot["condition"])
        durability = int(condition[:-1]) if condition.endswith("%") and condition[:-1].isdigit() else None
        connection.execute(
            "INSERT OR IGNORE INTO inventory_items("
            "id, character_id, slot_index, inventory_position, name, quantity, rarity, "
            "durability, maximum_durability, description, item_type, equip_slot"
            ") VALUES (?, ?, ?, NULL, ?, 1, 'common', ?, ?, '', 'equipment', ?)",
            (
                item_id, slot["character_id"], legacy_index, slot["item_name"],
                durability, 100 if durability is not None else None, slot["slot_name"],
            ),
        )
        connection.execute(
            "UPDATE equipment_slots SET inventory_item_id = ? WHERE id = ?",
            (item_id, slot["id"]),
        )
        connection.execute(
            "UPDATE inventory_items SET inventory_position = NULL WHERE id = ?",
            (item_id,),
        )
    rows = connection.execute(
        "SELECT inventory_items.id, COALESCE(campaign_preferences.difficulty, 'Adventurer') "
        "AS difficulty FROM inventory_items "
        "JOIN characters ON characters.id = inventory_items.character_id "
        "LEFT JOIN campaign_preferences ON campaign_preferences.campaign_id = characters.campaign_id "
        "WHERE inventory_items.item_generation_version < 1"
    ).fetchall()
    for row in rows:
        materialize_item_metadata(
            connection, str(row["id"]), difficulty=str(row["difficulty"])
        )


def recalculate_character_item_totals(
    connection: sqlite3.Connection,
    character_id: str,
) -> None:
    owned = connection.execute(
        "SELECT COALESCE(SUM(weight * quantity), 0) FROM inventory_items WHERE character_id = ?",
        (character_id,),
    ).fetchone()
    equipped = connection.execute(
        "SELECT inventory_items.armor_value, inventory_items.bonuses_json "
        "FROM equipment_slots JOIN inventory_items "
        "ON inventory_items.id = equipment_slots.inventory_item_id "
        "WHERE equipment_slots.character_id = ?",
        (character_id,),
    ).fetchall()
    armor = 0
    attack = 0
    combined: dict[str, int] = {}
    for row in equipped:
        armor += int(row["armor_value"])
        bonuses = decode_effects(str(row["bonuses_json"]))
        for key, value in bonuses.items():
            if isinstance(value, int):
                combined[str(key)] = combined.get(str(key), 0) + value
        attack += int(bonuses.get("attack", 0)) if isinstance(bonuses.get("attack", 0), int) else 0
    connection.execute(
        "UPDATE characters SET carry_weight = ?, equipment_armor_bonus = ?, "
        "equipment_attack_bonus = ?, equipment_bonuses_json = ? WHERE id = ?",
        (
            round(float(owned[0])), armor, attack,
            json.dumps(combined, separators=(",", ":")), character_id,
        ),
    )


def decode_effects(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
