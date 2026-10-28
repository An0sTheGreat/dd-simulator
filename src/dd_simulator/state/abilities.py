"""Deterministic Phase 10 combat action catalog and class loadouts."""

from __future__ import annotations

from dataclasses import dataclass, replace
import sqlite3


@dataclass(frozen=True, slots=True)
class CombatAbilityDefinition:
    key: str
    name: str
    kind: str
    description: str
    effect: str
    target: str = "enemy"
    range_feet: int = 60
    resource_type: str = "stamina"
    resource_cost: int = 0
    spell_slot_cost: int = 0
    dice_count: int = 1
    die_size: int = 6
    bonus: int = 0
    attack_bonus: int = 0
    condition_name: str = ""
    condition_rounds: int = 0
    armor_modifier: int = 0
    attack_modifier: int = 0
    damage_per_round: int = 0
    cooldown_rounds: int = 0
    max_uses: int | None = None
    required_weapon: str = ""
    save_type: str = ""
    save_dc: int = 0
    save_half: bool = False
    damage_type: str = "physical"
    unlock_level: int = 1
    is_cantrip: bool = False


def _weapon(key: str, name: str, description: str, **values: object) -> CombatAbilityDefinition:
    return CombatAbilityDefinition(
        key, name, "ability", description, "weapon_attack", range_feet=120, **values
    )


def _spell(key: str, name: str, description: str, effect: str = "spell_attack", **values: object) -> CombatAbilityDefinition:
    options: dict[str, object] = {
        "resource_type": "mana", "resource_cost": 2, "spell_slot_cost": 1,
        "damage_type": "arcane",
    }
    options.update(values)
    return CombatAbilityDefinition(key, name, "spell", description, effect, **options)


def _cantrip(
    key: str,
    name: str,
    description: str,
    effect: str = "spell_attack",
    **values: object,
) -> CombatAbilityDefinition:
    return _spell(
        key,
        name,
        description,
        effect,
        resource_cost=0,
        spell_slot_cost=0,
        is_cantrip=True,
        **values,
    )


CATALOG: dict[str, CombatAbilityDefinition] = {
    # Martial actions
    "power_strike": _weapon("power_strike", "Power Strike", "A committed weapon blow with improved force.", resource_cost=5, attack_bonus=1, bonus=2),
    "second_wind": CombatAbilityDefinition("second_wind", "Second Wind", "ability", "Regain health through discipline.", "heal", target="self", resource_cost=4, dice_count=1, die_size=8, bonus=2, cooldown_rounds=3, max_uses=2),
    "shield_wall": CombatAbilityDefinition("shield_wall", "Shield Wall", "ability", "Brace for incoming attacks.", "buff", target="self", resource_cost=3, condition_name="Shield Wall", condition_rounds=2, armor_modifier=3, cooldown_rounds=2),
    "cleave": CombatAbilityDefinition("cleave", "Cleave", "ability", "Sweep through every nearby enemy.", "area_damage", target="all_enemies", range_feet=5, resource_cost=6, dice_count=1, die_size=6, bonus=1, cooldown_rounds=2),
    "sneak_attack": _weapon("sneak_attack", "Sneak Attack", "Exploit an opening for extra damage.", resource_cost=4, attack_bonus=2, dice_count=2, die_size=6, cooldown_rounds=1),
    "poisoned_blade": CombatAbilityDefinition("poisoned_blade", "Poisoned Blade", "ability", "A precise strike that leaves lingering poison.", "damage_condition", range_feet=5, resource_cost=4, dice_count=1, die_size=4, condition_name="Poisoned", condition_rounds=3, damage_per_round=2, cooldown_rounds=3, max_uses=2),
    "evasive_stance": CombatAbilityDefinition("evasive_stance", "Evasive Stance", "ability", "Become difficult to pin down.", "buff", target="self", resource_cost=3, condition_name="Evasive", condition_rounds=2, armor_modifier=2, attack_modifier=1, cooldown_rounds=2),
    "quick_shot": _weapon("quick_shot", "Quick Shot", "Loose a fast, accurate ranged attack.", resource_cost=3, attack_bonus=2, cooldown_rounds=1, required_weapon="ranged"),
    "piercing_shot": _weapon("piercing_shot", "Piercing Shot", "Drive an arrow through armor.", resource_cost=5, attack_bonus=3, bonus=2, cooldown_rounds=2, required_weapon="ranged"),
    "volley": CombatAbilityDefinition("volley", "Volley", "ability", "Rain missiles across all enemies.", "area_damage", target="all_enemies", range_feet=120, resource_cost=7, dice_count=1, die_size=6, cooldown_rounds=3, required_weapon="ranged"),
    "field_dressing": CombatAbilityDefinition("field_dressing", "Field Dressing", "ability", "Quickly treat combat injuries.", "heal", target="self", resource_cost=4, dice_count=1, die_size=6, bonus=3, cooldown_rounds=3, max_uses=2),
    "battle_song": CombatAbilityDefinition("battle_song", "Battle Song", "ability", "A rallying verse sharpens attacks.", "buff", target="self", resource_type="focus", resource_cost=3, condition_name="Inspired", condition_rounds=3, attack_modifier=2, cooldown_rounds=3),
    "lay_on_hands": CombatAbilityDefinition("lay_on_hands", "Lay on Hands", "ability", "Channel resolve into healing.", "heal", target="self", resource_type="resolve", resource_cost=5, dice_count=2, die_size=6, bonus=2, cooldown_rounds=3, max_uses=2),
    "flurry": CombatAbilityDefinition("flurry", "Flurry of Blows", "ability", "A rapid sequence of focused strikes.", "direct_damage", range_feet=5, resource_type="focus", resource_cost=5, dice_count=2, die_size=6, cooldown_rounds=2),
    "patient_defense": CombatAbilityDefinition("patient_defense", "Patient Defense", "ability", "Read the battlefield and turn aside attacks.", "buff", target="self", resource_type="focus", resource_cost=3, condition_name="Patient Defense", condition_rounds=2, armor_modifier=3, cooldown_rounds=2),
    "arcane_turret": CombatAbilityDefinition("arcane_turret", "Arcane Turret", "ability", "Deploy a compact magical weapon.", "direct_damage", resource_type="focus", resource_cost=5, dice_count=2, die_size=4, cooldown_rounds=2, max_uses=3),
    "combat_ward": CombatAbilityDefinition("combat_ward", "Combat Ward", "ability", "Project a short-lived defensive field.", "buff", target="self", resource_type="focus", resource_cost=4, condition_name="Combat Ward", condition_rounds=3, armor_modifier=2, cooldown_rounds=3),

    # Spells
    "fire_bolt": _cantrip("fire_bolt", "Fire Bolt", "Hurl a focused bolt of flame.", die_size=10, damage_type="fire"),
    "magic_missile": _spell("magic_missile", "Magic Missile", "Unerring darts of force strike one target.", effect="direct_damage", dice_count=2, die_size=4, bonus=2),
    "ice_bind": _spell("ice_bind", "Ice Bind", "Cold damages and hinders the target on a failed Dexterity save.", effect="damage_condition", dice_count=1, die_size=6, condition_name="Icebound", condition_rounds=2, attack_modifier=-2, save_type="Dexterity", save_dc=12, damage_type="cold"),
    "arcane_ward": _spell("arcane_ward", "Arcane Ward", "A barrier turns aside attacks.", effect="buff", target="self", condition_name="Arcane Ward", condition_rounds=3, armor_modifier=3),
    "sacred_flame": _cantrip("sacred_flame", "Sacred Flame", "Radiant power sears a foe that fails a Dexterity save.", effect="direct_damage", die_size=8, save_type="Dexterity", save_dc=12, damage_type="radiant"),
    "healing_word": _spell("healing_word", "Healing Word", "Restore health with a brief invocation.", effect="heal", target="self", dice_count=2, die_size=4, bonus=2),
    "bless": _spell("bless", "Bless", "Divine favor improves combat accuracy.", effect="buff", target="self", condition_name="Blessed", condition_rounds=3, attack_modifier=2),
    "radiant_wave": _spell("radiant_wave", "Radiant Wave", "Radiance washes over every foe.", effect="area_damage", target="all_enemies", range_feet=30, dice_count=1, die_size=8, cooldown_rounds=2, damage_type="radiant"),
    "cutting_words": _cantrip("cutting_words", "Cutting Words", "Magic-laced mockery weakens a foe.", effect="damage_condition", die_size=6, condition_name="Unnerved", condition_rounds=2, attack_modifier=-2),
    "thunder_note": _spell("thunder_note", "Thunder Note", "A resonant note bursts against one foe.", dice_count=2, die_size=4, bonus=1),
    "heroic_chorus": _spell("heroic_chorus", "Heroic Chorus", "A refrain reinforces courage and defense.", effect="buff", target="self", condition_name="Heroic Chorus", condition_rounds=3, armor_modifier=2),
    "smite": _spell("smite", "Radiant Smite", "Radiant force empowers a martial blow.", effect="direct_damage", range_feet=5, dice_count=2, die_size=6, bonus=2, damage_type="radiant"),
    "aura_guard": _spell("aura_guard", "Aura of Guarding", "A holy aura hardens your defense.", effect="buff", target="self", condition_name="Guarding Aura", condition_rounds=3, armor_modifier=2),
    "thorn_whip": _cantrip("thorn_whip", "Thorn Whip", "A living vine lashes a distant foe.", die_size=6, range_feet=30),
    "regrowth": _spell("regrowth", "Regrowth", "Natural magic closes wounds.", effect="heal", target="self", dice_count=2, die_size=6),
    "entangle": _spell("entangle", "Entangle", "Roots hinder and wound a foe that fails a Strength save.", effect="damage_condition", dice_count=1, die_size=4, condition_name="Entangled", condition_rounds=3, attack_modifier=-2, save_type="Strength", save_dc=12),
    "moonburst": _spell("moonburst", "Moonburst", "Moonlight strikes every hostile creature.", effect="area_damage", target="all_enemies", range_feet=60, dice_count=1, die_size=8, cooldown_rounds=2, damage_type="radiant"),
    "eldritch_bolt": _cantrip("eldritch_bolt", "Eldritch Bolt", "Unsettling force tears into a foe.", die_size=10, damage_type="shadow"),
    "radiant_spark": _cantrip("radiant_spark", "Radiant Spark", "A mote of oath-bound light strikes a nearby foe.", die_size=8, damage_type="radiant"),
    "hunter_spark": _cantrip("hunter_spark", "Hunter's Spark", "A minor primal mark flashes against a hunted foe.", die_size=6, damage_type="nature"),
    "arc_spark": _cantrip("arc_spark", "Arc Spark", "A compact arcane discharge leaps from an artificer's implement.", die_size=8, damage_type="arcane"),
    "hex": _spell("hex", "Hex", "A curse inflicts lingering harm after a failed Wisdom save.", effect="damage_condition", dice_count=1, die_size=4, condition_name="Hexed", condition_rounds=3, damage_per_round=2, save_type="Wisdom", save_dc=12, damage_type="shadow"),
    "dark_bargain": _spell("dark_bargain", "Dark Bargain", "Trade resolve for immediate magical force.", effect="direct_damage", resource_type="resolve", resource_cost=4, spell_slot_cost=0, dice_count=3, die_size=4, cooldown_rounds=2),
    "shadow_veil": _spell("shadow_veil", "Shadow Veil", "Shadows obscure incoming attacks.", effect="buff", target="self", condition_name="Veiled", condition_rounds=3, armor_modifier=2),
    "alchemical_bomb": _spell("alchemical_bomb", "Alchemical Bomb", "A volatile charge catches every enemy.", effect="area_damage", target="all_enemies", resource_type="focus", resource_cost=4, spell_slot_cost=0, range_feet=40, dice_count=2, die_size=4, max_uses=3),
    "mending_vapor": _spell("mending_vapor", "Mending Vapor", "Restorative vapor repairs injuries.", effect="heal", target="self", resource_type="focus", resource_cost=4, spell_slot_cost=0, dice_count=2, die_size=4, bonus=2, max_uses=3),
    "warden_mark": CombatAbilityDefinition("warden_mark", "Warden's Mark", "ability", "Mark a foe and focus every strike.", "damage_condition", resource_type="focus", resource_cost=4, dice_count=1, die_size=6, condition_name="Warden's Mark", condition_rounds=3, attack_modifier=-1, cooldown_rounds=2),
}


_UNLOCK_LEVELS = {
    "shield_wall": 3, "cleave": 5, "poisoned_blade": 3,
    "evasive_stance": 2, "piercing_shot": 3, "volley": 5,
    "field_dressing": 2, "battle_song": 3, "lay_on_hands": 2,
    "flurry": 2, "patient_defense": 3, "arcane_turret": 3,
    "combat_ward": 5, "magic_missile": 1, "ice_bind": 3,
    "arcane_ward": 5, "healing_word": 1, "bless": 3,
    "radiant_wave": 5, "thunder_note": 1, "heroic_chorus": 3,
    "smite": 2, "aura_guard": 5, "regrowth": 1, "entangle": 3,
    "moonburst": 5, "hex": 1, "dark_bargain": 3,
    "shadow_veil": 5, "alchemical_bomb": 1, "mending_vapor": 2,
    "warden_mark": 1,
}
CATALOG = {
    key: replace(definition, unlock_level=_UNLOCK_LEVELS.get(key, 1))
    for key, definition in CATALOG.items()
}


CLASS_LOADOUTS: dict[str, tuple[str, ...]] = {
    "barbarian": ("power_strike", "second_wind", "cleave", "evasive_stance"),
    "fighter": ("power_strike", "second_wind", "shield_wall", "cleave"),
    "warrior": ("power_strike", "second_wind", "shield_wall", "cleave"),
    "rogue": ("sneak_attack", "poisoned_blade", "evasive_stance", "quick_shot"),
    "ranger": ("hunter_spark", "quick_shot", "piercing_shot", "volley", "field_dressing"),
    "mage": ("fire_bolt", "magic_missile", "ice_bind", "arcane_ward"),
    "wizard": ("fire_bolt", "magic_missile", "ice_bind", "arcane_ward"),
    "sorcerer": ("fire_bolt", "magic_missile", "ice_bind", "arcane_ward"),
    "cleric": ("sacred_flame", "healing_word", "bless", "radiant_wave"),
    "bard": ("cutting_words", "thunder_note", "heroic_chorus", "battle_song"),
    "paladin": ("radiant_spark", "lay_on_hands", "smite", "shield_wall", "aura_guard"),
    "druid": ("thorn_whip", "regrowth", "entangle", "moonburst"),
    "monk": ("flurry", "patient_defense", "second_wind", "evasive_stance"),
    "artificer": ("arc_spark", "alchemical_bomb", "mending_vapor", "arcane_turret", "combat_ward"),
    "warlock": ("eldritch_bolt", "hex", "dark_bargain", "shadow_veil"),
    "warden": ("warden_mark", "quick_shot", "field_dressing", "shield_wall"),
    "custom hybrid class": ("power_strike", "fire_bolt", "second_wind", "arcane_ward"),
}


CASTER_CLASSES = frozenset({"mage", "wizard", "sorcerer", "cleric", "bard", "paladin", "druid", "artificer", "warlock", "custom hybrid class"})


def class_catalog(character_class: str) -> tuple[CombatAbilityDefinition, ...]:
    keys = CLASS_LOADOUTS.get(character_class.casefold(), CLASS_LOADOUTS["custom hybrid class"])
    return tuple(CATALOG[key] for key in keys)


_FULL_CASTER_SLOTS = (0, 2, 3, 6, 7, 9, 10, 11, 12, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 22, 22)
_HALF_CASTER_SLOTS = (0, 0, 2, 3, 3, 6, 6, 7, 7, 9, 9, 10, 10, 11, 11, 12, 12, 14, 14, 15, 15)
_ARTIFICER_SLOTS = (0, 2, 2, 3, 3, 6, 6, 7, 7, 9, 9, 10, 10, 11, 11, 12, 12, 14, 14, 15, 15)
_WARLOCK_SLOTS = (0, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4)


def spell_slot_maximum(character_class: str, level: int) -> int:
    normalized = character_class.casefold().strip()
    level = max(1, min(20, int(level)))
    if normalized == "warlock":
        return _WARLOCK_SLOTS[level]
    if normalized == "artificer":
        return _ARTIFICER_SLOTS[level]
    if normalized in {"paladin", "ranger", "warden"}:
        return _HALF_CASTER_SLOTS[level]
    if normalized in CASTER_CLASSES:
        return _FULL_CASTER_SLOTS[level]
    return 0


def scaled_definition(
    definition: CombatAbilityDefinition, level: int
) -> CombatAbilityDefinition:
    if not definition.is_cantrip:
        return definition
    extra = sum(level >= threshold for threshold in (5, 11, 17))
    return replace(definition, dice_count=definition.dice_count + extra)


def sync_character_combat_catalog(
    connection: sqlite3.Connection,
    character_id: str,
    *,
    character_class: str,
    level: int,
) -> None:
    """Synchronize resource maximums and class unlocks for one character."""

    normalized = character_class.casefold().strip()
    if normalized in CASTER_CLASSES:
        mana_maximum = 12 + (4 * max(1, min(20, int(level))))
        slots_maximum = spell_slot_maximum(character_class, level)
        for order, (kind, name, maximum) in enumerate(
            (("mana", "Mana", mana_maximum), ("spell_slots", "Spell Slots", slots_maximum)),
            start=10,
        ):
            row = connection.execute(
                "SELECT id, current_value, maximum_value FROM character_resources "
                "WHERE character_id = ? AND resource_type = ?",
                (character_id, kind),
            ).fetchone()
            if row is None and maximum > 0:
                connection.execute(
                    "INSERT INTO character_resources(id, character_id, name, current_value, "
                    "maximum_value, resource_type, tooltip, sidebar_tooltip, display_order, "
                    "show_in_summary, show_in_sidebar) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
                    (f"{character_id}-resource-{kind}", character_id, name, maximum,
                     maximum, kind, f"Current and maximum {name.lower()}",
                     "Used by combat spells", order),
                )
            elif row is not None:
                adjusted_maximum = max(1, maximum)
                increase = max(0, adjusted_maximum - int(row["maximum_value"]))
                current = min(
                    adjusted_maximum, int(row["current_value"]) + increase
                )
                connection.execute(
                    "UPDATE character_resources SET current_value = ?, maximum_value = ? "
                    "WHERE id = ?",
                    (current, adjusted_maximum, row["id"]),
                )

    for order, definition in enumerate(class_catalog(character_class)):
        unlocked = int(int(level) >= definition.unlock_level)
        connection.execute(
            """
            INSERT INTO abilities(
                id, character_id, name, description, resource_type,
                resource_cost, cooldown_turns, unlocked, action_key,
                action_kind, spell_slot_cost, current_uses, maximum_uses,
                cooldown_remaining, display_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT(character_id, name) DO UPDATE SET
                description = excluded.description,
                resource_type = excluded.resource_type,
                resource_cost = excluded.resource_cost,
                cooldown_turns = excluded.cooldown_turns,
                unlocked = excluded.unlocked,
                action_key = excluded.action_key,
                action_kind = excluded.action_kind,
                spell_slot_cost = excluded.spell_slot_cost,
                maximum_uses = excluded.maximum_uses,
                display_order = excluded.display_order
            """,
            (
                f"ability-{character_id}-{definition.key}", character_id,
                definition.name, definition.description, definition.resource_type,
                definition.resource_cost, definition.cooldown_rounds, unlocked,
                definition.key, definition.kind, definition.spell_slot_cost,
                definition.max_uses, definition.max_uses, order,
            ),
        )
