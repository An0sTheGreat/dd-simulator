"""Typed character-creation values and deterministic validation."""

from __future__ import annotations

from dataclasses import dataclass

from dd_simulator.state.turns import sanitize_model_text


def plain_name(value: str) -> str:
    """Return a single-line name without model-added Markdown emphasis."""

    return " ".join(sanitize_model_text(value).strip("\"' ").split())


ANCESTRIES = (
    "Human", "Elf", "Dwarf", "Halfling", "Orc", "Half-orc", "Tiefling",
    "Dragonborn", "Goblin", "Beastfolk", "Construct", "Custom ancestry",
)
BACKGROUNDS = (
    "Exiled noble", "Traveling scholar", "Former soldier", "Street thief",
    "Village healer", "Monster hunter", "Escaped prisoner", "Apprentice mage",
    "Wandering mercenary", "Temple initiate", "Unknown past", "Custom background",
)
CLASSES = (
    "Barbarian", "Bard", "Cleric", "Druid", "Fighter", "Monk", "Paladin",
    "Ranger", "Rogue", "Sorcerer", "Warlock", "Wizard", "Artificer",
)
CLASS_DETAILS: dict[str, dict[str, object]] = {
    "Barbarian": {"hit_die": 12, "role": "Durable melee combatant", "primary": "Strength, Constitution", "saves": "Strength, Constitution", "armor": "Light armor, medium armor, shields", "weapons": "Simple and martial weapons"},
    "Bard": {"hit_die": 8, "role": "Versatile support spellcaster", "primary": "Charisma, Dexterity", "saves": "Dexterity, Charisma", "armor": "Light armor", "weapons": "Simple weapons, hand crossbows, longswords, rapiers, shortswords"},
    "Cleric": {"hit_die": 8, "role": "Divine spellcaster and healer", "primary": "Wisdom", "saves": "Wisdom, Charisma", "armor": "Light armor, medium armor, shields", "weapons": "Simple weapons"},
    "Druid": {"hit_die": 8, "role": "Nature spellcaster and shapeshifter", "primary": "Wisdom", "saves": "Intelligence, Wisdom", "armor": "Light armor, medium armor, shields (nonmetal)", "weapons": "Druid weapons"},
    "Fighter": {"hit_die": 10, "role": "Highly trained martial combatant", "primary": "Strength or Dexterity, Constitution", "saves": "Strength, Constitution", "armor": "All armor and shields", "weapons": "Simple and martial weapons"},
    "Monk": {"hit_die": 8, "role": "Mobile unarmed martial artist", "primary": "Dexterity, Wisdom", "saves": "Strength, Dexterity", "armor": "None", "weapons": "Simple weapons, shortswords"},
    "Paladin": {"hit_die": 10, "role": "Armored divine warrior", "primary": "Strength, Charisma", "saves": "Wisdom, Charisma", "armor": "All armor and shields", "weapons": "Simple and martial weapons"},
    "Ranger": {"hit_die": 10, "role": "Wilderness warrior and hunter", "primary": "Dexterity or Strength, Wisdom", "saves": "Strength, Dexterity", "armor": "Light armor, medium armor, shields", "weapons": "Simple and martial weapons"},
    "Rogue": {"hit_die": 8, "role": "Skilled and precise combatant", "primary": "Dexterity", "saves": "Dexterity, Intelligence", "armor": "Light armor", "weapons": "Simple weapons, hand crossbows, longswords, rapiers, shortswords"},
    "Sorcerer": {"hit_die": 6, "role": "Innate arcane spellcaster", "primary": "Charisma", "saves": "Constitution, Charisma", "armor": "None", "weapons": "Daggers, darts, slings, quarterstaffs, light crossbows"},
    "Warlock": {"hit_die": 8, "role": "Pact-powered spellcaster", "primary": "Charisma", "saves": "Wisdom, Charisma", "armor": "Light armor", "weapons": "Simple weapons"},
    "Wizard": {"hit_die": 6, "role": "Scholarly arcane spellcaster", "primary": "Intelligence", "saves": "Intelligence, Wisdom", "armor": "None", "weapons": "Daggers, darts, slings, quarterstaffs, light crossbows"},
    "Artificer": {"hit_die": 8, "role": "Magical inventor and support specialist", "primary": "Intelligence, Constitution", "saves": "Constitution, Intelligence", "armor": "Light armor, medium armor, shields", "weapons": "Simple weapons"},
}
# Preserve rule-equivalent support for older saved campaigns.
CLASS_DETAILS["Warrior"] = CLASS_DETAILS["Fighter"]
CLASS_DETAILS["Mage"] = CLASS_DETAILS["Wizard"]
CLASS_DETAILS["Warden"] = CLASS_DETAILS["Ranger"]
CLASS_DETAILS["Custom hybrid class"] = {
    "hit_die": 8, "role": "Balanced hybrid adventurer", "primary": "Choose two abilities",
    "saves": "Choose two saving throws", "armor": "Light armor", "weapons": "Simple weapons",
}
PERSONALITIES = (
    "Brave", "Cautious", "Charming", "Suspicious", "Curious", "Honorable",
    "Ruthless", "Compassionate", "Sarcastic", "Ambitious", "Quiet", "Reckless",
)
STRENGTHS = (
    "Courage", "Intelligence", "Loyalty", "Discipline", "Creativity",
    "Persuasion", "Survival instinct", "Magical talent",
)
FLAWS = (
    "Pride", "Greed", "Impulsiveness", "Distrust", "Short temper",
    "Recklessness", "Obsession", "Excessive loyalty",
)
MOTIVATIONS = (
    "Revenge", "Wealth", "Knowledge", "Redemption", "Adventure",
    "Protecting someone", "Finding a missing person", "Recovering an artifact",
    "Escaping the past", "Gaining power", "Saving a homeland",
)
WORLD_TYPES = (
    "Classic high fantasy", "Dark fantasy", "Low-magic medieval fantasy",
    "Mythological fantasy", "Steampunk fantasy", "Post-apocalyptic fantasy",
    "Gothic horror", "Sword and sorcery", "Pirate fantasy", "Magical western",
    "Science fantasy", "Custom world",
)
TONES = (
    "Heroic", "Hopeful", "Gritty", "Mysterious", "Dark", "Comedic",
    "Horror-focused", "Political", "Exploration-focused", "Balanced",
)
REGIONS = (
    "Mountain kingdom", "Forest village", "Coastal city", "Desert empire",
    "Frozen frontier", "Underground settlement", "Island chain",
    "War-torn borderland", "Magical capital", "Remote farming community",
)
LOCATIONS = (
    "Tavern", "Prison cell", "Caravan", "Battlefield", "Forest road",
    "Royal court", "Abandoned temple", "Ship", "Marketplace", "Academy",
    "Festival", "Monster's lair",
)
DIFFICULTIES = ("Story", "Adventurer", "Veteran", "Deadly")
VISUAL_STYLES = (
    "Photorealistic cinematic fantasy", "Realistic digital painting",
    "Classic fantasy illustration", "Graphic novel", "Anime", "Watercolor",
    "Gothic painting", "Pixel art", "Custom style",
)
CAMERA_STYLES = (
    "Cinematic wide-angle", "First-person", "Third-person over-the-shoulder",
    "Illustrated scene", "Dynamic action framing", "Balanced mixed framing",
)
SKILLS = (
    "Attack", "Strength", "Defense", "Ranged", "Survival", "Magic",
    "Herblore", "Crafting",
)
SKILL_DESCRIPTIONS = {
    "Attack": "Melee hit chance",
    "Strength": "Melee force, heavy lifting",
    "Defense": "Blocking, armor use",
    "Ranged": "Bows, thrown weapons",
    "Survival": "Tracking, foraging, escape",
    "Magic": "Spell power, arcane lore",
    "Herblore": "Herbs, potions, remedies",
    "Crafting": "Making, repairing gear",
}
ABILITY_NAMES = (
    "Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma",
)
POINT_BUY_COSTS = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}
DEFAULT_ABILITY_SCORES = tuple((name, 8) for name in ABILITY_NAMES)


def ability_modifier(score: int) -> int:
    return (score - 10) // 2


def point_buy_spent(scores: tuple[tuple[str, int], ...]) -> int:
    return sum(POINT_BUY_COSTS.get(score, 28) for _name, score in scores)


def level_one_hit_points(character_class: str, constitution: int) -> int:
    details = CLASS_DETAILS.get(character_class, CLASS_DETAILS["Fighter"])
    return max(1, int(details["hit_die"]) + ability_modifier(constitution))
PRIMARY_WEAPONS = (
    "Longsword", "Shortsword", "Battleaxe", "Warhammer", "Spear", "Quarterstaff",
    "Dagger", "Mace", "Rapier", "Greatsword", "Handaxe", "Wand",
)
SECONDARY_WEAPONS = (
    "None", "Dagger", "Shortsword", "Handaxe", "Mace", "Wand", "Parrying blade",
)
RANGED_WEAPONS = (
    "None", "Shortbow", "Longbow", "Light crossbow", "Heavy crossbow",
    "Throwing knives", "Sling",
)
ARMOR_CHOICES = (
    "Traveling clothes", "Padded armor", "Leather armor", "Studded leather",
    "Chain shirt", "Scale mail", "Chain mail", "Mage robes", "Druidic leathers",
)
SHIELD_CHOICES = ("None", "Wooden shield", "Round shield", "Kite shield", "Buckler")
TOOL_CHOICES = (
    "None", "Thieves' tools", "Healer's kit", "Herbalism kit", "Smith's tools",
    "Navigator's tools", "Spellbook", "Musical instrument", "Hunting trap",
)
KEEPSAKE_CHOICES = (
    "None", "Family locket", "Signet ring", "Weathered letter", "Carved token",
    "Old coin", "Prayer beads", "Broken compass", "Pressed flower",
)
DEFAULT_CONTENT_PREFERENCES = (
    "Balanced adventure; moderate combat and suspense; exploration and mystery "
    "encouraged; romance optional; no explicit sexual content or graphic injury; "
    "character death requires clear warning."
)
MINIMUM_ADULT_AGE = {
    "Human": 18, "Elf": 100, "Dwarf": 50, "Halfling": 20, "Orc": 16,
    "Half-orc": 18, "Tiefling": 18, "Dragonborn": 15, "Goblin": 16,
    "Beastfolk": 18, "Construct": 1, "Custom ancestry": 18,
}


@dataclass(frozen=True, slots=True)
class CharacterCreationDraft:
    campaign_name: str
    name: str
    ancestry: str
    age: int
    gender_identity: str
    pronouns: str
    body_description: str
    face_description: str
    clothing_style: str
    background: str
    character_class: str
    primary_weapon: str
    secondary_weapon: str
    ranged_weapon: str
    armor: str
    shield: str
    important_tool: str
    keepsake: str
    personalities: tuple[str, ...]
    primary_strength: str
    meaningful_flaw: str
    motivation: str
    biography: str
    backstory: str
    skills: tuple[str, ...]
    world_type: str
    tone: str
    starting_region: str
    starting_location: str
    difficulty: str
    content_preferences: str
    visual_style: str
    camera_style: str
    campaign_description: str = ""
    ability_scores: tuple[tuple[str, int], ...] = DEFAULT_ABILITY_SCORES
    preset_id: str = ""


class CharacterCreationValidator:
    REQUIRED_TEXT_FIELDS = (
        "campaign_name", "name", "ancestry", "body_description",
        "face_description", "clothing_style", "background", "character_class",
        "primary_weapon", "personalities", "primary_strength", "meaningful_flaw",
        "motivation", "world_type", "tone", "starting_region",
        "starting_location", "difficulty", "visual_style",
        "camera_style", "campaign_description",
    )

    @classmethod
    def validate(cls, draft: CharacterCreationDraft) -> dict[str, str]:
        errors: dict[str, str] = {}
        for field in cls.REQUIRED_TEXT_FIELDS:
            value = getattr(draft, field)
            if not value or (isinstance(value, str) and not value.strip()):
                errors[field] = "This field is required."
        minimum_age = MINIMUM_ADULT_AGE.get(draft.ancestry, 18)
        if draft.age < minimum_age:
            errors["age"] = f"{draft.ancestry or 'This ancestry'} must be at least {minimum_age}."
        if len(draft.personalities) < 1:
            errors["personalities"] = "Select at least one personality trait."
        elif len(draft.personalities) > 2:
            errors["personalities"] = "Select no more than two personality traits."
        if len(draft.skills) != 3:
            errors["skills"] = "Select exactly three starting focus skills."
        if len(set(draft.skills)) != len(draft.skills):
            errors["skills"] = "Starting focus skills must be unique."
        scores = dict(draft.ability_scores)
        if len(draft.ability_scores) != len(ABILITY_NAMES) or set(scores) != set(ABILITY_NAMES) or any(
            score not in POINT_BUY_COSTS for score in scores.values()
        ):
            errors["ability_scores"] = "Every ability score must be between 8 and 15."
        elif point_buy_spent(draft.ability_scores) != 27:
            errors["ability_scores"] = "Spend all 27 ability points."
        for field in ("campaign_name", "name"):
            if len(getattr(draft, field).strip()) > 80:
                errors[field] = "Use 80 characters or fewer."
        for field in (
            "biography", "backstory", "content_preferences", "campaign_description",
        ):
            if len(getattr(draft, field)) > 4000:
                errors[field] = "Use 4,000 characters or fewer."
        return errors
