"""Code-owned d20 checks for free-text story actions (investigate, climb, sneak...).

The roll is made before the model narrates and is passed to it as fact, so the model
never decides success. Like dialogue checks, the roll is seeded by campaign, turn and
action text: resubmitting the same action on the same turn gives the same result.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3

from dd_simulator.state.turns import SkillCheckResult

# (check name, attribute, game skill or None, pattern); first match wins.
STORY_CHECKS: tuple[tuple[str, str, str | None, str], ...] = (
    ("Thievery", "Dexterity", "Crafting", r"\b(?:pick(?:ing)? (?:the |a )?lock|lockpick\w*|disarm\w*)\b"),
    ("Athletics", "Strength", "Strength",
     r"\b(?:climb\w*|swim\w*|jump\w*|leap\w*|lift\w*|shove\w*|pry\w*|bash\w*|"
     r"force (?:it |the \w+ )?open|break (?:down|open)|push (?:the|it))\b"),
    ("Stealth", "Dexterity", None, r"\b(?:sneak\w*|hide|hiding|creep\w*|slip past|stealth\w*)\b"),
    ("Survival", "Wisdom", "Survival",
     r"\b(?:track\w*|forag\w*|hunt\w*|navigate\w*|follow (?:the )?(?:trail|tracks|path))\b"),
    ("Investigation", "Intelligence", None,
     r"\b(?:investigat\w*|search\w*|inspect\w*|scour\w*|rummag\w*|look for|"
     r"examine (?:the )?(?:area|room|scene|ground|cart|wreck\w*|body|bodies|tracks))\b"),
    ("Perception", "Wisdom", "Survival",
     r"\b(?:listen\w*|eavesdrop\w*|look around|scan\w* the|keep watch|watch for|spot\w*)\b"),
    ("Arcana", "Intelligence", "Magic",
     r"\b(?:arcane|runes?|enchant\w*|sense (?:for )?magic|detect magic|ward\w*)\b"),
    ("Medicine", "Wisdom", "Herblore",
     r"\b(?:treat\w* (?:the |his |her |their )?wound\w*|bandag\w*|tend\w* (?:to )?\w*|"
     r"herbs?|poison\w*|remed\w*)\b"),
    ("Intimidation", "Strength", None, r"\b(?:intimidat\w*|threaten\w*)\b"),
    ("Deception", "Charisma", None, r"\b(?:deceiv\w*|bluff\w*|lie to)\b"),
    ("Persuasion", "Charisma", None, r"\b(?:persuad\w*|convinc\w*|haggl\w*)\b"),
)
DIFFICULTY_OFFSET = {"story": -2, "adventurer": 0, "veteran": 2, "deadly": 4}  # as dialogue checks
BASE_DC = 12


def story_check_kind(action: str) -> tuple[str, str, str | None] | None:
    for name, attribute, skill, pattern in STORY_CHECKS:
        if re.search(pattern, action, flags=re.IGNORECASE):
            return name, attribute, skill
    return None


def roll_story_check(
    connection: sqlite3.Connection,
    campaign_id: str,
    character_id: str,
    turn_number: int,
    action: str,
) -> SkillCheckResult | None:
    kind = story_check_kind(action)
    if kind is None:
        return None
    name, attribute, skill = kind
    row = connection.execute(
        "SELECT modifier FROM character_attributes WHERE character_id = ? AND lower(name) = lower(?)",
        (character_id, attribute),
    ).fetchone()
    modifier = 0 if row is None else int(row["modifier"])
    if skill is not None:
        skill_row = connection.execute(
            "SELECT bonus, level FROM skills WHERE character_id = ? AND lower(name) = lower(?)",
            (character_id, skill),
        ).fetchone()
        if skill_row is not None:
            modifier += int(skill_row["bonus"]) + int(skill_row["level"]) // 20
    preferences = connection.execute(
        "SELECT difficulty FROM campaign_preferences WHERE campaign_id = ?", (campaign_id,)
    ).fetchone()
    difficulty = "adventurer" if preferences is None else str(preferences["difficulty"]).casefold()
    target = BASE_DC + DIFFICULTY_OFFSET.get(difficulty, 0)
    seed = hashlib.sha256(f"{campaign_id}:story:{turn_number}:{action.casefold()}".encode()).digest()
    roll = seed[0] % 20 + 1
    total = roll + modifier
    return SkillCheckResult(name, roll, modifier, total, target, total >= target)
