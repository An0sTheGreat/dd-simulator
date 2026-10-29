"""Read-only projections from authoritative rows to UI presentation models."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from dd_simulator.state.abilities import (
    CATALOG,
    CombatAbilityDefinition,
    scaled_definition,
)
from dd_simulator.state.character_creation import SKILL_DESCRIPTIONS, plain_name
from dd_simulator.state.combat import player_attack_bonus
from dd_simulator.state.database import GameStateDatabase
from dd_simulator.state.commerce import merchant_price
from dd_simulator.state.dialogue import SUGGESTED_RESPONSES
from dd_simulator.state.errors import IncompleteGameStateError
from dd_simulator.state.item_actions import item_definition
from dd_simulator.state.progression import proficiency_bonus
from dd_simulator.ui.models.presentation import (
    CombatActionOptionView,
    AttributeView,
    ConversationView,
    DialogueMessageView,
    CombatRewardItemView,
    CombatRewardView,
    CombatantView,
    CombatEncounterView,
    CombatLogEntryView,
    CommerceItemView,
    CraftingIngredientView,
    CraftingRecipeView,
    CraftingResultView,
    DashboardView,
    EquipmentSlotView,
    EventView,
    InventorySlotView,
    LocationSummaryView,
    MapLocationView,
    MerchantView,
    NpcView,
    NarrativeMessageView,
    NarrativeSegmentView,
    NarrativeView,
    TurnNoteView,
    ObjectiveView,
    PlayerSummaryView,
    QuestListItemView,
    QuestRewardItemView,
    QuestRewardView,
    QuestView,
    ResourceView,
    SkillView,
    TravelRouteView,
    VisualAssetView,
    WorldMapView,
)
from dd_simulator.state.visuals import (
    VisualAssetRecord,
    character_state_signature,
    location_state_signature,
    resolve_visual_record,
)


CODEX_PORTRAIT_ROOT = Path(__file__).parents[1] / "ui" / "assets" / "codex" / "portraits"
_PORTRAIT_PACKS = (
    ("dwarf", ("dwarf",)),
    ("goblin", ("goblin",)),
    ("fairy", ("fairy", "fey")),
    ("demon", ("tiefling", "infernal", "demon", "devil")),
    ("undead", ("undead",)),
)


def fallback_portrait(character_id: str, ancestry: str) -> str:
    """Pick a codex portrait from the ancestry's pack, stable per character id."""

    lowered = ancestry.casefold()
    pack = next(
        (name for name, words in _PORTRAIT_PACKS if any(word in lowered for word in words)),
        "fantasy",
    )
    count = len(list((CODEX_PORTRAIT_ROOT / pack).glob("*.png")))
    if not count:
        return ""
    number = int(hashlib.sha256(character_id.encode()).hexdigest(), 16) % count + 1
    path = CODEX_PORTRAIT_ROOT / pack / f"{number}.png"
    return str(path) if path.is_file() else ""


def _required(row: sqlite3.Row | None, label: str) -> sqlite3.Row:
    if row is None:
        raise IncompleteGameStateError(f"Campaign is missing required {label} data")
    return row


def _resource(row: sqlite3.Row, *, sidebar: bool = False) -> ResourceView:
    tooltip = str(row["sidebar_tooltip"]) if sidebar else str(row["tooltip"])
    return ResourceView(
        name=str(row["name"]),
        current=int(row["current_value"]),
        maximum=int(row["maximum_value"]),
        resource_type=str(row["resource_type"]),
        tooltip=tooltip,
    )


def _visual_view(record: VisualAssetRecord | None) -> VisualAssetView | None:
    if record is None:
        return None
    return VisualAssetView(
        id=record.id,
        asset_kind=record.asset_kind,
        path=(
            str(record.absolute_path)
            if record.status == "confirmed" and record.absolute_path is not None
            else ""
        ),
        status=record.status,
        version=record.version,
        state_signature=record.state_signature,
        canonical=record.canonical,
        prompt_summary=record.prompt_summary,
    )


def _ability_stats(
    definition: CombatAbilityDefinition,
    row: sqlite3.Row,
) -> tuple[tuple[str, str], ...]:
    cost = "No resource cost"
    costs: list[str] = []
    if definition.resource_cost:
        costs.append(
            f"{definition.resource_cost} {definition.resource_type.replace('_', ' ').title()}"
        )
    if definition.spell_slot_cost:
        costs.append(f"{definition.spell_slot_cost} spell slot")
    if definition.is_cantrip:
        costs.append("Cantrip; no spell slot")
    if costs:
        cost = " + ".join(costs)

    if definition.effect == "heal":
        effect = f"{definition.dice_count}d{definition.die_size}"
        if definition.bonus:
            effect += f" + {definition.bonus}"
        effect += " healing"
    elif definition.effect in {
        "weapon_attack", "spell_attack", "direct_damage", "area_damage", "damage_condition"
    }:
        effect = f"{definition.dice_count}d{definition.die_size}"
        if definition.bonus:
            effect += f" + {definition.bonus}"
        effect += f" {definition.damage_type} damage"
    elif definition.armor_modifier or definition.attack_modifier:
        values = []
        if definition.armor_modifier:
            values.append(f"Armor {definition.armor_modifier:+d}")
        if definition.attack_modifier:
            values.append(f"Attack {definition.attack_modifier:+d}")
        effect = ", ".join(values)
    else:
        effect = definition.effect.replace("_", " ").title()

    uses = "Unlimited"
    if row["current_uses"] is not None:
        uses = f"{row['current_uses']} / {row['maximum_uses']}"
    cooldown = f"{row['cooldown_remaining']} remaining / {definition.cooldown_rounds} rounds"
    duration = (
        f"{definition.condition_rounds} rounds"
        if definition.condition_rounds else "Immediate"
    )
    save = (
        f"{definition.save_type} DC {definition.save_dc}"
        if definition.save_type else "None"
    )
    stats = (
        ("Type", definition.kind.title()),
        ("Level", "Cantrip" if definition.is_cantrip else str(definition.unlock_level)),
        ("Cost", cost),
        ("Effect", effect),
        ("Range", f"{definition.range_feet} ft"),
        ("Target", definition.target.replace("_", " ").title()),
        ("Uses", uses),
        ("Cooldown", cooldown),
        ("Duration", duration),
        ("Save", save),
    )
    # a power on yourself has no distance to show
    if definition.target == "self":
        stats = tuple(stat for stat in stats if stat[0] != "Range")
    return stats


def _narrative_segments(row: sqlite3.Row) -> tuple[NarrativeSegmentView, ...]:
    try:
        raw_segments = json.loads(str(row["response_segments_json"]))
    except (json.JSONDecodeError, TypeError):
        raw_segments = []
    segments: list[NarrativeSegmentView] = []
    if isinstance(raw_segments, list):
        for raw in raw_segments:
            if not isinstance(raw, dict):
                continue
            kind = raw.get("kind")
            text = raw.get("text")
            if kind in {"narrative", "monologue", "spoken"} and isinstance(text, str) and text.strip():
                segments.append(NarrativeSegmentView(kind, text.strip()))
    if segments:
        return tuple(segments)
    try:
        paragraphs = json.loads(str(row["paragraphs_json"]))
    except (json.JSONDecodeError, TypeError):
        paragraphs = []
    if isinstance(paragraphs, list):
        segments.extend(
            NarrativeSegmentView("narrative", paragraph.strip())
            for paragraph in paragraphs
            if isinstance(paragraph, str) and paragraph.strip()
        )
    dialogue = str(row["dialogue"]).strip()
    if dialogue:
        segments.append(NarrativeSegmentView("spoken", dialogue))
    return tuple(segments)


MESSAGE_PAGE_SIZE = 40


def message_page(
    connection: sqlite3.Connection,
    assets_root: Path | None,
    campaign_id: str,
    *,
    before_turn: int = 2**62,
    limit: int = MESSAGE_PAGE_SIZE,
) -> tuple[tuple[NarrativeMessageView, ...], bool]:
    """Return the newest whole turns before ``before_turn`` (at most ``limit``
    messages, but always at least one turn) and whether older turns exist.

    Pages never split a turn, so ``before_turn`` paging loses nothing and each
    turn's notes stay on its last message.
    """

    counts = connection.execute(
        "SELECT turn_number, COUNT(*) AS total FROM narrative_messages "
        "WHERE campaign_id = ? AND turn_number < ? "
        "GROUP BY turn_number ORDER BY turn_number DESC",
        (campaign_id, before_turn),
    ).fetchall()
    first_turn: int | None = None
    taken = 0
    has_older = False
    for count in counts:
        if first_turn is not None and taken + int(count["total"]) > limit:
            has_older = True
            break
        first_turn = int(count["turn_number"])
        taken += int(count["total"])
    if first_turn is None:
        return (), False
    rows = connection.execute(
        """
        SELECT narrative_messages.*, npcs.name AS speaker_name
        FROM narrative_messages
        LEFT JOIN npcs ON npcs.id = narrative_messages.speaker_npc_id
        WHERE narrative_messages.campaign_id = ?
          AND narrative_messages.turn_number >= ? AND narrative_messages.turn_number < ?
        ORDER BY narrative_messages.turn_number, narrative_messages.sequence
        """,
        (campaign_id, first_turn, before_turn),
    ).fetchall()
    portraits: dict[str, str] = {}
    for speaker_id in {
        str(row["speaker_npc_id"]) for row in rows if row["speaker_npc_id"] is not None
    }:
        # NPC portraits are keyed like character portraits; only a confirmed
        # canonical record (signature "" never matches exactly) yields a path.
        speaker_view = _visual_view(resolve_visual_record(
            connection,
            assets_root,
            campaign_id=campaign_id,
            asset_kind="portrait",
            subject_type="character",
            subject_id=speaker_id,
            signature="",
        ))
        if speaker_view is not None and speaker_view.path:
            portraits[speaker_id] = speaker_view.path
    last_of_turn = {int(row["turn_number"]): index for index, row in enumerate(rows)}
    index_of = {
        (int(row["turn_number"]), int(row["sequence"])): index for index, row in enumerate(rows)
    }
    # A note sits on the message it was claimed with; notes from before schema 24
    # (NULL sequence) fall back to the last message of their turn.
    notes: dict[int, list[TurnNoteView]] = {}
    for note in connection.execute(
        "SELECT turn_number, sequence, kind, text FROM turn_notes WHERE campaign_id = ? "
        "AND turn_number >= ? AND turn_number < ? ORDER BY turn_number, id",
        (campaign_id, first_turn, before_turn),
    ):
        turn = int(note["turn_number"])
        target = index_of.get((turn, note["sequence"]), last_of_turn.get(turn))
        if target is not None:
            notes.setdefault(target, []).append(TurnNoteView(str(note["kind"]), str(note["text"])))
    messages = tuple(
        NarrativeMessageView(
            str(row["kind"]),
            str(row["text"]),
            turn_number=int(row["turn_number"]),
            speaker_id=None if row["speaker_npc_id"] is None else str(row["speaker_npc_id"]),
            speaker_name=str(row["speaker_name"] or ""),
            speaker_portrait=portraits.get(str(row["speaker_npc_id"]), ""),
            notes=tuple(notes.get(index, ())),
        )
        for index, row in enumerate(rows)
    )
    return messages, has_older


def _narrative_messages(
    narrative: sqlite3.Row,
    messages: tuple[NarrativeMessageView, ...],
) -> tuple[NarrativeMessageView, ...]:
    if messages:
        return messages
    fallback: list[NarrativeMessageView] = []
    player_action = str(narrative["player_action"]).strip()
    if player_action:
        fallback.append(NarrativeMessageView("player", player_action))
    fallback.extend(
        NarrativeMessageView(segment.kind, segment.text)
        for segment in _narrative_segments(narrative)
    )
    return tuple(fallback[-20:])


class DashboardProjection:
    def __init__(self, database: GameStateDatabase) -> None:
        self.database = database
        self.assets_root = (
            database.path.parent / "visual_assets"
            if isinstance(database.path, Path)
            else None
        )

    def older_messages(
        self, campaign_id: str, before_turn: int, limit: int = MESSAGE_PAGE_SIZE
    ) -> tuple[NarrativeMessageView, ...]:
        with self.database.connect() as connection:
            messages, _has_older = message_page(
                connection, self.assets_root, campaign_id,
                before_turn=before_turn, limit=limit,
            )
        return messages

    def load(self, campaign_id: str) -> DashboardView:
        with self.database.connect() as connection:
            campaign = connection.execute(
                "SELECT id, name FROM campaigns WHERE id = ?",
                (campaign_id,),
            ).fetchone()
            _required(campaign, "campaign")
            preset_flag = connection.execute(
                "SELECT 1 FROM campaign_flags WHERE campaign_id = ? "
                "AND flag_key = 'preset_id'",
                (campaign_id,),
            ).fetchone()
            character = _required(
                connection.execute(
                    "SELECT * FROM characters WHERE campaign_id = ? AND is_player = 1",
                    (campaign_id,),
                ).fetchone(),
                "player character",
            )
            character_id = str(character["id"])
            resources = connection.execute(
                "SELECT * FROM character_resources WHERE character_id = ? "
                "ORDER BY display_order, id",
                (character_id,),
            ).fetchall()
            by_type = {str(row["resource_type"]): row for row in resources}
            experience_row = _required(by_type.get("experience"), "experience resource")
            summary_resources = tuple(
                _resource(row) for row in resources if bool(row["show_in_summary"])
            )
            sidebar_resources = tuple(
                _resource(row, sidebar=True)
                for row in resources
                if bool(row["show_in_sidebar"])
            )

            location = _required(
                connection.execute(
                    """
                    SELECT locations.*, campaign_clock.time_label, campaign_clock.day AS clock_day,
                        campaign_clock.turn_number AS clock_turn
                    FROM locations
                    JOIN campaign_clock ON campaign_clock.campaign_id = locations.campaign_id
                    WHERE locations.campaign_id = ? AND locations.is_current = 1
                    """,
                    (campaign_id,),
                ).fetchone(),
                "current location",
            )
            visual_preferences = connection.execute(
                "SELECT visual_style, camera_style, difficulty FROM campaign_preferences "
                "WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            visual_style = (
                "" if visual_preferences is None else str(visual_preferences["visual_style"])
            )
            camera_style = (
                "" if visual_preferences is None else str(visual_preferences["camera_style"])
            )
            difficulty = (
                "Adventurer"
                if visual_preferences is None
                else str(visual_preferences["difficulty"])
            )
            equipped_visual_items = tuple(
                str(row["name"])
                for row in connection.execute(
                    """
                    SELECT inventory_items.name
                    FROM equipment_slots
                    JOIN inventory_items
                      ON inventory_items.id = equipment_slots.inventory_item_id
                    WHERE equipment_slots.character_id = ?
                    ORDER BY equipment_slots.slot_index
                    """,
                    (character_id,),
                ).fetchall()
            )
            player_visual = resolve_visual_record(
                connection,
                self.assets_root,
                campaign_id=campaign_id,
                asset_kind="portrait",
                subject_type="character",
                subject_id=character_id,
                signature=character_state_signature(
                    character,
                    equipment=equipped_visual_items,
                    art_style=visual_style,
                    camera_style=camera_style,
                ),
            )
            player_portrait = _visual_view(player_visual)
            portrait_path = "" if player_portrait is None else player_portrait.path
            if not portrait_path:
                canonical_portrait = _visual_view(resolve_visual_record(
                    connection,
                    self.assets_root,
                    campaign_id=campaign_id,
                    asset_kind="portrait",
                    subject_type="character",
                    subject_id=character_id,
                    signature="",
                ))
                portrait_path = (
                    canonical_portrait.path if canonical_portrait is not None else ""
                ) or fallback_portrait(character_id, str(character["species"]))
            location_visual = resolve_visual_record(
                connection,
                self.assets_root,
                campaign_id=campaign_id,
                asset_kind="location",
                subject_type="location",
                subject_id=str(location["id"]),
                signature=location_state_signature(
                    location,
                    time_label=str(location["time_label"]),
                    art_style=visual_style,
                    camera_style=camera_style,
                ),
            )
            map_location_rows = connection.execute(
                "SELECT * FROM locations WHERE campaign_id = ? AND (discovered = 1 OR is_current = 1) "
                "ORDER BY map_y, map_x, name",
                (campaign_id,),
            ).fetchall()
            map_route_rows = connection.execute(
                """
                SELECT travel_routes.*,
                       origin.name AS origin_name,
                       destination.name AS destination_name
                FROM travel_routes
                JOIN locations origin ON origin.id = travel_routes.origin_location_id
                JOIN locations destination ON destination.id = travel_routes.destination_location_id
                WHERE travel_routes.campaign_id = ? AND travel_routes.discovered = 1
                  AND origin.discovered = 1 AND destination.discovered = 1
                ORDER BY travel_routes.id
                """,
                (campaign_id,),
            ).fetchall()
            last_journey_row = connection.execute(
                "SELECT summary FROM travel_history WHERE campaign_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (campaign_id,),
            ).fetchone()
            narrative = _required(
                connection.execute(
                    "SELECT * FROM narratives WHERE campaign_id = ?",
                    (campaign_id,),
                ).fetchone(),
                "narrative",
            )
            recent_messages, has_older_messages = message_page(
                connection, self.assets_root, campaign_id
            )
            selected_quest = _required(
                connection.execute(
                    "SELECT * FROM quests WHERE campaign_id = ? ORDER BY selected DESC, "
                    "CASE status WHEN 'active' THEN 0 WHEN 'rumored' THEN 1 ELSE 2 END, "
                    "display_order LIMIT 1",
                    (campaign_id,),
                ).fetchone(),
                "selected quest",
            )
            objective_rows = connection.execute(
                "SELECT * FROM quest_objectives WHERE quest_id = ? "
                "ORDER BY display_order, id",
                (selected_quest["id"],),
            ).fetchall()
            quest_rows = connection.execute(
                "SELECT * FROM quests WHERE campaign_id = ? ORDER BY display_order, id",
                (campaign_id,),
            ).fetchall()
            all_objective_rows = connection.execute(
                "SELECT * FROM quest_objectives WHERE quest_id IN "
                "(SELECT id FROM quests WHERE campaign_id = ?) "
                "ORDER BY quest_id, display_order, id",
                (campaign_id,),
            ).fetchall()
            pending_quest_reward = connection.execute(
                "SELECT quest_rewards.*, quests.title AS quest_title "
                "FROM quest_rewards JOIN quests ON quests.id = quest_rewards.quest_id "
                "WHERE quest_rewards.campaign_id = ? AND quest_rewards.acknowledged = 0 "
                "ORDER BY quest_rewards.created_at DESC LIMIT 1",
                (campaign_id,),
            ).fetchone()
            pending_quest_reward_items: list[sqlite3.Row] = []
            if pending_quest_reward is not None:
                pending_quest_reward_items = connection.execute(
                    "SELECT * FROM quest_reward_items WHERE reward_id = ? "
                    "ORDER BY claimed, name",
                    (pending_quest_reward["id"],),
                ).fetchall()
            event_rows = connection.execute(
                "SELECT * FROM events WHERE campaign_id = ? ORDER BY sequence",
                (campaign_id,),
            ).fetchall()
            skill_rows = connection.execute(
                "SELECT * FROM skills WHERE character_id = ? ORDER BY display_order, id",
                (character_id,),
            ).fetchall()
            attribute_rows = connection.execute(
                "SELECT * FROM character_attributes WHERE character_id = ? "
                "ORDER BY display_order, id",
                (character_id,),
            ).fetchall()
            inventory_rows = connection.execute(
                "SELECT * FROM inventory_items WHERE character_id = ? "
                "AND inventory_position IS NOT NULL ORDER BY inventory_position",
                (character_id,),
            ).fetchall()
            crafting_recipe_rows = connection.execute(
                "SELECT * FROM crafting_recipes WHERE campaign_id = ? "
                "ORDER BY unlocked DESC, display_order, name",
                (campaign_id,),
            ).fetchall()
            crafting_ingredient_rows = connection.execute(
                "SELECT crafting_recipe_ingredients.* FROM crafting_recipe_ingredients "
                "JOIN crafting_recipes ON crafting_recipes.id = crafting_recipe_ingredients.recipe_id "
                "WHERE crafting_recipes.campaign_id = ? "
                "ORDER BY crafting_recipe_ingredients.recipe_id, "
                "crafting_recipe_ingredients.display_order, crafting_recipe_ingredients.id",
                (campaign_id,),
            ).fetchall()
            pending_crafting_row = connection.execute(
                "SELECT * FROM crafting_results WHERE campaign_id = ? AND acknowledged = 0 "
                "ORDER BY created_at DESC, id DESC LIMIT 1",
                (campaign_id,),
            ).fetchone()
            equipment_rows = connection.execute(
                "SELECT equipment_slots.*, inventory_items.name AS linked_name, "
                "inventory_items.quantity AS linked_quantity, inventory_items.rarity AS linked_rarity, "
                "inventory_items.durability AS linked_durability, "
                "inventory_items.maximum_durability AS linked_maximum_durability, "
                "inventory_items.quest_item AS linked_quest_item, "
                "inventory_items.description AS linked_description, "
                "inventory_items.item_type AS linked_item_type, "
                "inventory_items.consumable AS linked_consumable, "
                "inventory_items.charges AS linked_charges, "
                "inventory_items.maximum_charges AS linked_maximum_charges, "
                "inventory_items.equip_slot AS linked_equip_slot, "
                "inventory_items.use_effect_json AS linked_effects, "
                "inventory_items.item_category AS linked_category, "
                "inventory_items.weight AS linked_weight, "
                "inventory_items.value_gp AS linked_value_gp, "
                "inventory_items.identified AS linked_identified, "
                "inventory_items.damage_text AS linked_damage, "
                "inventory_items.armor_value AS linked_armor, "
                "inventory_items.healing_value AS linked_healing, "
                "inventory_items.compatible_slots_json AS linked_compatible_slots, "
                "inventory_items.requirements_json AS linked_requirements, "
                "inventory_items.bonuses_json AS linked_bonuses, "
                "inventory_items.penalties_json AS linked_penalties, "
                "inventory_items.generated_difficulty AS linked_generated_difficulty "
                "FROM equipment_slots LEFT JOIN inventory_items "
                "ON inventory_items.id = equipment_slots.inventory_item_id "
                "WHERE equipment_slots.character_id = ? ORDER BY equipment_slots.slot_index",
                (character_id,),
            ).fetchall()
            npc_rows = connection.execute(
                "SELECT npcs.*, COALESCE(relationships.score, 0) AS relationship_score "
                "FROM npcs LEFT JOIN relationships ON relationships.campaign_id = npcs.campaign_id "
                "AND relationships.target_entity_id = npcs.id "
                "AND relationships.source_entity_id = ? "
                "WHERE npcs.campaign_id = ? AND npcs.location_id = ? AND npcs.known = 1 "
                "ORDER BY npcs.available DESC, npcs.name",
                (character_id, campaign_id, location["id"]),
            ).fetchall()
            conversation_rows = connection.execute(
                "SELECT npc_conversations.* FROM npc_conversations JOIN npcs ON npcs.id = npc_conversations.npc_id "
                "WHERE npc_conversations.campaign_id = ? AND npcs.location_id = ? "
                "ORDER BY npc_conversations.npc_id, npc_conversations.turn_number",
                (campaign_id, location["id"]),
            ).fetchall()
            merchant_stock_rows = connection.execute(
                "SELECT merchant_stock.* FROM merchant_stock JOIN npcs "
                "ON npcs.id = merchant_stock.npc_id "
                "WHERE npcs.campaign_id = ? AND npcs.location_id = ? "
                "AND merchant_stock.quantity > 0 "
                "ORDER BY merchant_stock.npc_id, merchant_stock.display_order, merchant_stock.name",
                (campaign_id, location["id"]),
            ).fetchall()
            ability_rows = connection.execute(
                "SELECT * FROM abilities WHERE character_id = ? AND action_key <> '' "
                "AND unlocked = 1 ORDER BY display_order, name",
                (character_id,),
            ).fetchall()
            combat_encounter = connection.execute(
                """
                SELECT * FROM combat_encounters
                WHERE campaign_id = ?
                ORDER BY CASE WHEN status = 'active' THEN 0 ELSE 1 END,
                         created_at DESC
                LIMIT 1
                """,
                (campaign_id,),
            ).fetchone()
            combatant_rows: list[sqlite3.Row] = []
            combat_condition_rows: list[sqlite3.Row] = []
            combat_turn_rows: list[sqlite3.Row] = []
            combat_reward = None
            combat_reward_items: list[sqlite3.Row] = []
            if combat_encounter is not None:
                encounter_id = str(combat_encounter["id"])
                combatant_rows = connection.execute(
                    "SELECT * FROM combatants WHERE encounter_id = ? "
                    "ORDER BY display_order",
                    (encounter_id,),
                ).fetchall()
                combat_condition_rows = connection.execute(
                    "SELECT combat_conditions.* FROM combat_conditions "
                    "JOIN combatants ON combatants.id = combat_conditions.combatant_id "
                    "WHERE combatants.encounter_id = ? ORDER BY combat_conditions.name",
                    (encounter_id,),
                ).fetchall()
                combat_turn_rows = connection.execute(
                    """
                    SELECT combat_turns.*, combatants.name AS actor_name
                    FROM combat_turns
                    JOIN combatants ON combatants.id = combat_turns.actor_id
                    WHERE combat_turns.encounter_id = ?
                    ORDER BY combat_turns.sequence DESC
                    LIMIT 8
                    """,
                    (encounter_id,),
                ).fetchall()
                combat_reward = connection.execute(
                    "SELECT * FROM combat_rewards WHERE encounter_id = ?",
                    (encounter_id,),
                ).fetchone()
                if combat_reward is not None:
                    combat_reward_items = connection.execute(
                        "SELECT * FROM combat_reward_items WHERE reward_id = ? "
                        "ORDER BY claimed, rarity DESC, name",
                        (combat_reward["id"],),
                    ).fetchall()

        objectives_by_quest: dict[str, list[ObjectiveView]] = {}
        for row in all_objective_rows:
            objectives_by_quest.setdefault(str(row["quest_id"]), []).append(
                ObjectiveView(
                    text=str(row["text"]),
                    completed=bool(row["completed"]),
                    optional=bool(row["optional"]),
                )
            )
        quest_reward_view = None
        if pending_quest_reward is not None:
            quest_reward_view = QuestRewardView(
                id=str(pending_quest_reward["id"]),
                quest_id=str(pending_quest_reward["quest_id"]),
                quest_title=str(pending_quest_reward["quest_title"]),
                experience=int(pending_quest_reward["experience"]),
                currency=int(pending_quest_reward["currency"]),
                reputation=int(pending_quest_reward["reputation"]),
                faction=str(pending_quest_reward["faction"]),
                items=tuple(
                    QuestRewardItemView(
                        id=str(row["id"]), name=str(row["name"]),
                        quantity=int(row["quantity"]), rarity=str(row["rarity"]),
                        description=str(row["description"]), claimed=bool(row["claimed"]),
                    )
                    for row in pending_quest_reward_items
                ),
                acknowledged=bool(pending_quest_reward["acknowledged"]),
            )

        inventory_by_slot = {int(row["inventory_position"]): row for row in inventory_rows}
        highest_position = max(inventory_by_slot, default=-1)
        capacity = max(36, ((highest_position + 36) // 36) * 36)
        inventory = tuple(
            InventorySlotView(None)
            if (row := inventory_by_slot.get(index)) is None
            else InventorySlotView(
                name=str(row["name"]),
                id=str(row["id"]),
                quantity=int(row["quantity"]),
                rarity=str(row["rarity"]),
                durability=None if row["durability"] is None else int(row["durability"]),
                maximum_durability=(
                    None
                    if row["maximum_durability"] is None
                    else int(row["maximum_durability"])
                ),
                quest_item=bool(row["quest_item"]),
                selected=bool(row["selected"]),
                description=str(row["description"]),
                item_type=str(row["item_type"]),
                consumable=bool(row["consumable"]),
                charges=None if row["charges"] is None else int(row["charges"]),
                maximum_charges=(
                    None
                    if row["maximum_charges"] is None
                    else int(row["maximum_charges"])
                ),
                equip_slot=str(row["equip_slot"]),
                usable=(
                    bool(row["consumable"])
                    or row["charges"] is not None
                    or row["durability"] is not None
                    or str(row["use_effect_json"]) not in {"", "{}"}
                ),
                effects=str(row["use_effect_json"]),
                damage=str(row["damage_text"]),
                armor=str(row["armor_value"]) if int(row["armor_value"]) else "",
                status=(
                    "Quest item" if bool(row["quest_item"])
                    else "Equippable" if str(row["equip_slot"]) else ""
                ),
                category=str(row["item_category"]),
                weight=float(row["weight"]),
                value_gp=int(row["value_gp"]),
                identified=bool(row["identified"]),
                healing=int(row["healing_value"]),
                compatible_slots=tuple(json.loads(str(row["compatible_slots_json"]))),
                requirements=str(row["requirements_json"]),
                bonuses=str(row["bonuses_json"]),
                penalties=str(row["penalties_json"]),
                generated_difficulty=str(row["generated_difficulty"]),
                position=index,
            )
            for index in range(capacity)
        )
        conditions_by_combatant: dict[str, list[str]] = {}
        for row in combat_condition_rows:
            conditions_by_combatant.setdefault(str(row["combatant_id"]), []).append(
                str(row["name"])
            )
        combat_skills: list[CombatActionOptionView] = []
        for row in ability_rows:
            definition = CATALOG.get(str(row["action_key"]))
            if definition is None:
                continue
            definition = scaled_definition(definition, int(character["level"]))
            reason = ""
            uses = (
                "" if row["current_uses"] is None
                else f"{row['current_uses']}/{row['maximum_uses']} uses"
            )
            status = uses or "Ready"
            if int(row["cooldown_remaining"]) > 0:
                reason = f"Cooldown: {row['cooldown_remaining']} round(s)"
                status = f"Cooldown {row['cooldown_remaining']}"
            elif row["current_uses"] is not None and int(row["current_uses"]) <= 0:
                reason = "No uses remaining before rest"
            elif definition.resource_cost and (
                definition.resource_type not in by_type
                or int(by_type[definition.resource_type]["current_value"]) < definition.resource_cost
            ):
                reason = f"Requires {definition.resource_cost} {definition.resource_type.replace('_', ' ')}"
                status = f"Needs {definition.resource_cost} {definition.resource_type.replace('_', ' ')}"
            costs: list[str] = []
            if definition.is_cantrip:
                costs.append("Cantrip; no spell slot")
            if definition.resource_cost:
                costs.append(f"{definition.resource_cost} {definition.resource_type.replace('_', ' ')}")
            if definition.spell_slot_cost:
                costs.append(f"{definition.spell_slot_cost} spell slot")
            if row["current_uses"] is not None:
                costs.append(f"{row['current_uses']}/{row['maximum_uses']} uses")
            if definition.target != "self":  # a power on yourself has no distance
                costs.append(f"Range {definition.range_feet} ft")
            combat_skills.append(CombatActionOptionView(
                key=definition.key, name=definition.name, kind=definition.kind,
                description=definition.description,
                resource_label=" | ".join(costs), available=not reason,
                unavailable_reason=reason,
                stats=_ability_stats(definition, row),
                status_label=status,
            ))
        combat_view = None
        if combat_encounter is not None:
            current_index = int(combat_encounter["current_index"])
            player_combatant = next(
                (row for row in combatant_rows if str(row["side"]) == "player"), None
            )
            active_enemies = tuple(
                row for row in combatant_rows
                if str(row["side"]) == "enemy" and str(row["status"]) == "active"
            )
            action_options: list[CombatActionOptionView] = []
            for row in ability_rows:
                definition = CATALOG.get(str(row["action_key"]))
                if definition is None:
                    continue
                definition = scaled_definition(definition, int(character["level"]))
                reason = ""
                if int(row["cooldown_remaining"]) > 0:
                    reason = f"Cooldown: {row['cooldown_remaining']} round(s)"
                elif definition.required_weapon == "ranged" and (
                    player_combatant is None
                    or int(player_combatant["attack_range_feet"]) <= 10
                ):
                    reason = "Requires an equipped ranged weapon"
                elif row["current_uses"] is not None and int(row["current_uses"]) <= 0:
                    reason = "No uses remaining before rest"
                elif definition.resource_cost and (
                    definition.resource_type not in by_type
                    or int(by_type[definition.resource_type]["current_value"])
                    < definition.resource_cost
                ):
                    reason = (
                        f"Requires {definition.resource_cost} "
                        f"{definition.resource_type.replace('_', ' ')}"
                    )
                elif definition.spell_slot_cost and (
                    "spell_slots" not in by_type
                    or int(by_type["spell_slots"]["current_value"])
                    < definition.spell_slot_cost
                ):
                    reason = "Requires a spell slot"
                elif definition.target in {"enemy", "all_enemies"} and not any(
                    int(enemy["distance_feet"]) <= definition.range_feet
                    for enemy in active_enemies
                ):
                    reason = f"No enemy within {definition.range_feet} ft"
                elif definition.effect == "heal" and player_combatant is not None and (
                    int(player_combatant["current_health"])
                    >= int(player_combatant["maximum_health"])
                ):
                    reason = "Health is already full"
                costs: list[str] = []
                if definition.is_cantrip:
                    costs.append("Cantrip; no spell slot")
                if definition.resource_cost:
                    costs.append(f"{definition.resource_cost} {definition.resource_type.replace('_', ' ')}")
                if definition.spell_slot_cost:
                    costs.append(f"{definition.spell_slot_cost} slot")
                if row["current_uses"] is not None:
                    costs.append(f"{row['current_uses']}/{row['maximum_uses']} uses")
                action_options.append(
                    CombatActionOptionView(
                        key=definition.key,
                        name=definition.name,
                        kind=definition.kind,
                        description=definition.description,
                        resource_label=" | ".join(costs) or "No cost",
                        available=not reason,
                        unavailable_reason=reason,
                        stats=_ability_stats(definition, row),
                    )
                )
            reward_view = None
            if combat_reward is not None:
                reward_view = CombatRewardView(
                    id=str(combat_reward["id"]),
                    outcome=str(combat_reward["outcome"]),
                    experience=int(combat_reward["experience"]),
                    skill_experience=int(combat_reward["skill_experience"]),
                    currency=int(combat_reward["currency"]),
                    items=tuple(
                        CombatRewardItemView(
                            id=str(row["id"]), name=str(row["name"]),
                            quantity=int(row["quantity"]), rarity=str(row["rarity"]),
                            description=str(row["description"]), claimed=bool(row["claimed"]),
                        )
                        for row in combat_reward_items
                    ),
                    acknowledged=bool(combat_reward["acknowledged"]),
                )
            combat_view = CombatEncounterView(
                id=str(combat_encounter["id"]),
                status=str(combat_encounter["status"]),
                round_number=int(combat_encounter["round_number"]),
                environment=str(combat_encounter["environment"]),
                hazard=str(combat_encounter["hazard"]),
                starting_distance=int(combat_encounter["starting_distance"]),
                end_reason=str(combat_encounter["end_reason"]),
                combatants=tuple(
                    CombatantView(
                        id=str(row["id"]),
                        name=str(row["name"]),
                        side=str(row["side"]),
                        status=str(row["status"]),
                        current_health=int(row["current_health"]),
                        maximum_health=int(row["maximum_health"]),
                        armor_class=int(row["armor_class"]),
                        initiative=int(row["initiative"]),
                        distance_feet=int(row["distance_feet"]),
                        weapon_name=str(row["weapon_name"]),
                        morale=int(row["morale"]),
                        conditions=tuple(conditions_by_combatant.get(str(row["id"]), [])),
                        declared_intent=str(row["declared_intent"]),
                        active_turn=(int(row["display_order"]) == current_index),
                        archetype_key=str(row["archetype_key"]),
                        abilities=tuple(json.loads(str(row["abilities_json"]))),
                        resistances=tuple(json.loads(str(row["resistances_json"]))),
                        vulnerabilities=tuple(json.loads(str(row["vulnerabilities_json"]))),
                        behavior_profile=str(row["behavior_profile"]),
                    )
                    for row in combatant_rows
                ),
                recent_turns=tuple(
                    CombatLogEntryView(
                        round_number=int(row["round_number"]),
                        actor_name=str(row["actor_name"]),
                        action_type=str(row["action_type"]),
                        summary=str(row["summary"]),
                    )
                    for row in reversed(combat_turn_rows)
                ),
                action_options=tuple(action_options),
                generated=bool(combat_encounter["generated"]),
                intro_complete=bool(combat_encounter["intro_complete"]),
                introduction=str(combat_encounter["introduction"]),
                terrain=str(combat_encounter["terrain"]),
                awareness_state=str(combat_encounter["awareness_state"]),
                difficulty_rating=int(combat_encounter["difficulty_rating"]),
                preparation_choice=str(combat_encounter["preparation_choice"]),
                reward=reward_view,
            )

        current_location_id = str(location["id"])
        discovered_location_ids = {str(row["id"]) for row in map_location_rows}
        world_map = WorldMapView(
            current_location_id=current_location_id,
            locations=tuple(
                MapLocationView(
                    id=str(row["id"]),
                    name=str(row["name"]),
                    region=str(row["region"]),
                    description=str(row["description"]),
                    biome=str(row["biome"]),
                    danger=str(row["danger"]),
                    current=bool(row["is_current"]),
                    visited=int(row["visit_count"]) > 0,
                    can_camp=bool(row["can_camp"]),
                    map_x=int(row["map_x"]),
                    map_y=int(row["map_y"]),
                )
                for row in map_location_rows
            ),
            routes=tuple(
                TravelRouteView(
                    id=str(row["id"]),
                    origin_id=str(row["origin_location_id"]),
                    origin_name=str(row["origin_name"]),
                    destination_id=str(row["destination_location_id"]),
                    destination_name=str(row["destination_name"]),
                    target_location_id=(
                        str(row["destination_location_id"])
                        if str(row["origin_location_id"]) == current_location_id
                        else str(row["origin_location_id"])
                        if bool(row["bidirectional"])
                        and str(row["destination_location_id"]) == current_location_id
                        else ""
                    ),
                    distance_miles=int(row["distance_miles"]),
                    travel_minutes=int(row["travel_minutes"]),
                    stamina_cost=int(row["stamina_cost"]),
                    danger_rating=int(row["danger_rating"]),
                    status=str(row["status"]),
                    requirement=str(row["requirement"]),
                    description=str(row["description"]),
                    reachable=(
                        str(row["status"]) == "open"
                        and (
                            str(row["origin_location_id"]) == current_location_id
                            or bool(row["bidirectional"])
                            and str(row["destination_location_id"]) == current_location_id
                        )
                        and (
                            str(row["destination_location_id"])
                            if str(row["origin_location_id"]) == current_location_id
                            else str(row["origin_location_id"])
                        ) in discovered_location_ids
                    ),
                )
                for row in map_route_rows
            ),
            can_camp=bool(location["can_camp"]),
            last_journey=(
                "" if last_journey_row is None else str(last_journey_row["summary"])
            ),
        )
        npc_views = tuple(
            NpcView(
                id=str(row["id"]), name=str(row["name"]), title=str(row["title"]),
                portrait_initials=str(row["portrait_initials"]), status=str(row["status"]),
                disposition=str(row["disposition"]), relationship_score=int(row["relationship_score"]),
                available=bool(row["available"]) and str(row["status"]) not in {"unavailable", "departed", "deceased"},
                personality=str(row["personality"]),
            )
            for row in npc_rows
        )
        conversation_by_npc: dict[str, list[DialogueMessageView]] = {}
        check_by_npc: dict[str, str] = {}
        for row in conversation_rows:
            npc_id = str(row["npc_id"])
            messages = conversation_by_npc.setdefault(npc_id, [])
            messages.append(DialogueMessageView("player", str(row["player_text"])))
            if str(row["monologue"]).strip():
                messages.append(DialogueMessageView("monologue", str(row["monologue"])))
            messages.append(DialogueMessageView("spoken", str(row["npc_text"])))
            if str(row["check_type"]):
                check_by_npc[npc_id] = (
                    f"{str(row['check_type']).title()}: d20 {row['d20_roll']} + {row['modifier']} "
                    f"= {row['total']} vs DC {row['difficulty']} — {row['outcome']}"
                )

        stock_by_npc: dict[str, list[sqlite3.Row]] = {}
        for row in merchant_stock_rows:
            stock_by_npc.setdefault(str(row["npc_id"]), []).append(row)

        def equipment_views() -> tuple[EquipmentSlotView, ...]:
            values: list[EquipmentSlotView] = []
            for row in equipment_rows:
                item = None
                if row["inventory_item_id"] is not None:
                    item = InventorySlotView(
                        name=str(row["linked_name"]), id=str(row["inventory_item_id"]),
                        quantity=int(row["linked_quantity"]), rarity=str(row["linked_rarity"]),
                        durability=None if row["linked_durability"] is None else int(row["linked_durability"]),
                        maximum_durability=None if row["linked_maximum_durability"] is None else int(row["linked_maximum_durability"]),
                        description=str(row["linked_description"]), item_type=str(row["linked_item_type"]),
                        equip_slot=str(row["linked_equip_slot"]), effects=str(row["linked_effects"]),
                        damage=str(row["linked_damage"]),
                        armor=str(row["linked_armor"]) if int(row["linked_armor"]) else "",
                        category=str(row["linked_category"]), weight=float(row["linked_weight"]),
                        value_gp=int(row["linked_value_gp"]), identified=bool(row["linked_identified"]),
                        healing=int(row["linked_healing"]),
                        compatible_slots=tuple(json.loads(str(row["linked_compatible_slots"]))),
                        status="Equipped",
                    )
                values.append(EquipmentSlotView(
                    slot_name=str(row["slot_name"]),
                    item_name=None if row["item_name"] is None else str(row["item_name"]),
                    condition=str(row["condition"]), selected=bool(row["selected"]), item=item,
                ))
            return tuple(values)

        def merchant_view(npc: NpcView) -> MerchantView | None:
            stock_rows = stock_by_npc.get(npc.id, [])
            if not stock_rows:
                return None
            stock: list[CommerceItemView] = []
            for row in stock_rows:
                definition = item_definition(str(row["name"]))
                stock.append(CommerceItemView(
                    id=str(row["id"]), name=str(row["name"]), quantity=int(row["quantity"]),
                    rarity=str(row["rarity"]), description=str(row["description"]),
                    durability=None if row["durability"] is None else int(row["durability"]),
                    maximum_durability=(
                        None if row["maximum_durability"] is None
                        else int(row["maximum_durability"])
                    ),
                    damage=definition.damage,
                    healing=dict(definition.resource_effects).get("health", 0),
                    category=definition.category, item_type=definition.item_type,
                    equip_slot=definition.equip_slot,
                    compatible_slots=definition.compatible_slots,
                    weight=definition.weight, value_gp=int(row["base_value"]),
                    buy_price=merchant_price(
                        int(row["base_value"]), str(row["rarity"]), row["durability"],
                        row["maximum_durability"], difficulty, npc.relationship_score,
                        action="buy",
                    ),
                    barter_price=merchant_price(
                        int(row["base_value"]), str(row["rarity"]), row["durability"],
                        row["maximum_durability"], difficulty, npc.relationship_score,
                        action="barter",
                    ),
                ))
            sellable: list[CommerceItemView] = []
            for row in inventory_rows:
                if bool(row["quest_item"]) or str(row["item_type"]) == "currency":
                    continue
                sellable.append(CommerceItemView(
                    id=str(row["id"]), name=str(row["name"]), quantity=int(row["quantity"]),
                    rarity=str(row["rarity"]), description=str(row["description"]),
                    durability=None if row["durability"] is None else int(row["durability"]),
                    maximum_durability=(
                        None if row["maximum_durability"] is None
                        else int(row["maximum_durability"])
                    ),
                    damage=str(row["damage_text"]), healing=int(row["healing_value"]),
                    category=str(row["item_category"]), item_type=str(row["item_type"]),
                    equip_slot=str(row["equip_slot"]),
                    compatible_slots=tuple(json.loads(str(row["compatible_slots_json"]))),
                    weight=float(row["weight"]), value_gp=int(row["value_gp"]),
                    identified=bool(row["identified"]),
                    sell_price=merchant_price(
                        int(row["value_gp"]), str(row["rarity"]), row["durability"],
                        row["maximum_durability"], difficulty, npc.relationship_score,
                        action="sell",
                    ),
                ))
            return MerchantView(
                npc_id=npc.id,
                player_currency=int(character["currency"]),
                stock=tuple(stock),
                sellable_items=tuple(sellable),
                equipment=equipment_views(),
            )

        owned_by_name: dict[str, int] = {}
        rows_by_name: dict[str, list[sqlite3.Row]] = {}
        for row in inventory_rows:
            key = str(row["name"]).casefold()
            owned_by_name[key] = owned_by_name.get(key, 0) + int(row["quantity"])
            rows_by_name.setdefault(key, []).append(row)
        ingredients_by_recipe: dict[str, list[sqlite3.Row]] = {}
        for row in crafting_ingredient_rows:
            ingredients_by_recipe.setdefault(str(row["recipe_id"]), []).append(row)
        crafting_skill = next(
            (row for row in skill_rows if str(row["name"]).casefold() == "crafting"), None
        )
        difficulty_modifier = {
            "story": -5, "adventurer": 0, "veteran": 5,
            "deadly": 10, "custom": 5,
        }.get(difficulty.casefold(), 0)
        crafting_recipes: list[CraftingRecipeView] = []
        for row in crafting_recipe_rows:
            recipe_ingredients = tuple(
                CraftingIngredientView(
                    name=str(ingredient["item_name"]),
                    required=int(ingredient["quantity"]),
                    owned=owned_by_name.get(str(ingredient["item_name"]).casefold(), 0),
                )
                for ingredient in ingredients_by_recipe.get(str(row["id"]), [])
            )
            tool_name = str(row["required_tool"])
            tool_cost = int(row["tool_use_cost"])
            tool_rows = rows_by_name.get(tool_name.casefold(), []) if tool_name else []
            tool_available = not tool_name
            if tool_rows:
                tool = tool_rows[0]
                tool_available = (
                    (tool["charges"] is None or int(tool["charges"]) >= tool_cost)
                    and (tool["durability"] is None or int(tool["durability"]) >= tool_cost)
                )
            missing = [
                value.name for value in recipe_ingredients if value.owned < value.required
            ]
            unavailable_reason = ""
            if pending_crafting_row is not None:
                unavailable_reason = "A crafting result is awaiting acknowledgement."
            elif not bool(row["unlocked"]):
                unavailable_reason = "Recipe is locked."
            elif crafting_skill is None or bool(crafting_skill["locked"]):
                unavailable_reason = "Crafting skill is unavailable."
            elif missing:
                unavailable_reason = f"Missing: {', '.join(missing)}."
            elif not tool_available:
                unavailable_reason = f"Requires {tool_name} with {tool_cost} use(s)."
            crafting_recipes.append(CraftingRecipeView(
                id=str(row["id"]), name=str(row["name"]),
                description=str(row["description"]), skill_name=str(row["skill_name"]),
                skill_level=0 if crafting_skill is None else int(crafting_skill["level"]),
                difficulty=int(row["difficulty"]) + difficulty_modifier,
                output_name=str(row["output_name"]),
                output_quantity=int(row["output_quantity"]),
                output_rarity=str(row["output_rarity"]),
                crafting_xp=int(row["crafting_xp"]), ingredients=recipe_ingredients,
                required_tool=tool_name, tool_use_cost=tool_cost,
                tool_available=tool_available,
                available=not unavailable_reason,
                unavailable_reason=unavailable_reason,
            ))
        crafting_result_view = None
        if pending_crafting_row is not None:
            crafting_result_view = CraftingResultView(
                id=str(pending_crafting_row["id"]),
                recipe_name=str(pending_crafting_row["recipe_name"]),
                success=str(pending_crafting_row["status"]) == "success",
                score=int(pending_crafting_row["score"]),
                difficulty=int(pending_crafting_row["difficulty"]),
                output_name=str(pending_crafting_row["output_name"]),
                output_quantity=int(pending_crafting_row["output_quantity"]),
                output_rarity=str(pending_crafting_row["output_rarity"]),
                quality=str(pending_crafting_row["quality"]),
                ingredients_consumed=tuple(
                    (str(value[0]), int(value[1]))
                    for value in json.loads(str(pending_crafting_row["ingredients_consumed_json"]))
                ),
                tool_uses=tuple(
                    (str(value[0]), int(value[1]))
                    for value in json.loads(str(pending_crafting_row["tool_uses_json"]))
                ),
                crafting_xp=int(pending_crafting_row["crafting_xp"]),
                summary=str(pending_crafting_row["summary"]),
                acknowledged=bool(pending_crafting_row["acknowledged"]),
            )

        player_name = plain_name(str(character["name"]))
        player_initials = "".join(
            part[0].upper() for part in player_name.split()[:2] if part
        ) or "?"
        return DashboardView(
            player=PlayerSummaryView(
                name=player_name,
                level=int(character["level"]),
                character_class=str(character["character_class"]),
                portrait_initials=player_initials,
                resources=summary_resources,
                experience=_resource(experience_row),
                currency=int(character["currency"]),
                carry_weight=int(character["carry_weight"]),
                carry_capacity=int(character["carry_capacity"]),
                visual=_visual_view(player_visual),
                species=str(character["species"]),
                background=str(character["background"]),
                attributes=tuple(
                    AttributeView(
                        name=str(row["name"]),
                        value=int(row["value"]),
                        modifier=int(row["modifier"]),
                    )
                    for row in attribute_rows
                ),
                armor_class=(
                    10
                    + next(
                        (
                            int(row["modifier"])
                            for row in attribute_rows
                            if str(row["name"]).casefold() == "dexterity"
                        ),
                        0,
                    )
                    + sum(int(row["linked_armor"] or 0) for row in equipment_rows)
                ),
                initiative_modifier=next(
                    (
                        int(row["modifier"])
                        for row in attribute_rows
                        if str(row["name"]).casefold() == "dexterity"
                    ),
                    0,
                ),
                movement_feet=15,
                age=int(character["age"] or 0),
                gender_identity=str(character["gender_identity"] or ""),
                pronouns=str(character["pronouns"] or ""),
                body_description=str(character["body_description"] or ""),
                face_description=str(character["face_description"] or ""),
                clothing_style=str(character["clothing_style"] or ""),
                personalities=tuple(json.loads(str(character["personality_json"] or "[]"))),
                primary_strength=str(character["primary_strength"] or ""),
                meaningful_flaw=str(character["meaningful_flaw"] or ""),
                motivation=str(character["motivation"] or ""),
                biography=str(character["biography"] or ""),
                backstory=str(character["backstory"] or ""),
                proficiency_bonus=proficiency_bonus(int(character["level"])),
                attack_bonus=player_attack_bonus(
                    next(
                        (
                            int(row["modifier"])
                            for row in attribute_rows
                            if str(row["name"]).casefold() == "strength"
                        ),
                        0,
                    ),
                    next(
                        (
                            int(row["bonus"])
                            for row in skill_rows
                            if str(row["name"]).casefold() == "attack"
                        ),
                        0,
                    ),
                    character,
                ),
                pending_ability_points=int(character["pending_ability_points"]),
                portrait_path=portrait_path,
            ),
            location=LocationSummaryView(
                name=str(location["name"]),
                region=str(location["region"]),
                time_label=str(location["time_label"]),
                weather=str(location["weather"]),
                danger=str(location["danger"]),
                route_status=str(location["route_status"]),
                visual=_visual_view(location_visual),
                biome=str(location["biome"]),
                day=int(location["clock_day"]),
                turn_number=int(location["clock_turn"]),
            ),
            narrative=NarrativeView(
                title=str(narrative["title"]),
                paragraphs=tuple(json.loads(str(narrative["paragraphs_json"]))),
                dialogue=str(narrative["dialogue"]),
                prompt=str(narrative["prompt"]),
                suggested_actions=tuple(
                    json.loads(str(narrative["suggested_actions_json"]))
                ),
                player_action=str(narrative["player_action"]),
                response_segments=_narrative_segments(narrative),
                messages=_narrative_messages(narrative, recent_messages),
                has_older_messages=has_older_messages,
            ),
            quest=QuestView(
                title=str(selected_quest["title"]),
                status=(
                    "Active quest"
                    if str(selected_quest["status"]) == "active"
                    else str(selected_quest["status"])
                ),
                summary=str(selected_quest["summary"]),
                objectives=tuple(
                    ObjectiveView(
                        text=str(row["text"]),
                        completed=bool(row["completed"]),
                        optional=bool(row["optional"]),
                    )
                    for row in objective_rows
                ),
            ),
            event_log=tuple(
                EventView(str(row["time_label"]), str(row["category"]), str(row["summary"]))
                for row in event_rows
                if not bool(row["is_recent"])
            ),
            recent_events=tuple(
                EventView(str(row["time_label"]), str(row["category"]), str(row["summary"]))
                for row in event_rows
                if bool(row["is_recent"])
            ),
            sidebar_resources=sidebar_resources,
            skills=tuple(
                SkillView(
                    name=str(row["name"]),
                    level=int(row["level"]),
                    current_xp=int(row["current_xp"]),
                    next_level_xp=int(row["next_level_xp"]),
                    bonus=int(row["bonus"]),
                    locked=bool(row["locked"]),
                    recently_increased=bool(row["recently_increased"]),
                    description=SKILL_DESCRIPTIONS.get(str(row["name"]), ""),
                )
                for row in skill_rows
            ),
            inventory_preview=inventory,
            equipment=tuple(
                EquipmentSlotView(
                    slot_name=str(row["slot_name"]),
                    item_name=None if row["item_name"] is None else str(row["item_name"]),
                    condition=str(row["condition"]),
                    selected=bool(row["selected"]),
                    item=(
                        None if row["inventory_item_id"] is None else InventorySlotView(
                            name=str(row["linked_name"]), id=str(row["inventory_item_id"]),
                            quantity=int(row["linked_quantity"]), rarity=str(row["linked_rarity"]),
                            durability=None if row["linked_durability"] is None else int(row["linked_durability"]),
                            maximum_durability=None if row["linked_maximum_durability"] is None else int(row["linked_maximum_durability"]),
                            quest_item=bool(row["linked_quest_item"]),
                            description=str(row["linked_description"]), item_type=str(row["linked_item_type"]),
                            consumable=bool(row["linked_consumable"]),
                            charges=None if row["linked_charges"] is None else int(row["linked_charges"]),
                            maximum_charges=None if row["linked_maximum_charges"] is None else int(row["linked_maximum_charges"]),
                            equip_slot=str(row["linked_equip_slot"]), effects=str(row["linked_effects"]),
                            damage=str(row["linked_damage"]),
                            armor=str(row["linked_armor"]) if int(row["linked_armor"]) else "",
                            category=str(row["linked_category"]), weight=float(row["linked_weight"]),
                            value_gp=int(row["linked_value_gp"]), identified=bool(row["linked_identified"]),
                            healing=int(row["linked_healing"]),
                            compatible_slots=tuple(json.loads(str(row["linked_compatible_slots"]))),
                            requirements=str(row["linked_requirements"]),
                            bonuses=str(row["linked_bonuses"]), penalties=str(row["linked_penalties"]),
                            generated_difficulty=str(row["linked_generated_difficulty"]),
                            status="Equipped",
                        )
                    ),
                )
                for row in equipment_rows
            ),
            quest_list=tuple(
                QuestListItemView(
                    id=str(row["id"]),
                    title=str(row["title"]),
                    status=(
                        "optional"
                        if str(row["status"]) == "active" and str(row["quest_type"]) == "optional"
                        else str(row["status"])
                    ),
                    progress_current=int(row["progress_current"]),
                    progress_maximum=int(row["progress_maximum"]),
                    selected=bool(row["selected"]),
                    deadline=str(row["deadline"]),
                    summary=str(row["summary"]),
                    quest_type=str(row["quest_type"]),
                    objectives=tuple(objectives_by_quest.get(str(row["id"]), ())),
                    reward_summary=(
                        f"{row['reward_experience']} XP, {row['reward_currency']} gold"
                        + (
                            f", {row['reward_faction']} {int(row['reward_reputation']):+d}"
                            if row["reward_faction"] and int(row["reward_reputation"])
                            else ""
                        )
                    ),
                )
                for row in quest_rows
            ),
            combat=combat_view,
            pending_quest_reward=quest_reward_view,
            world_map=world_map,
            combat_skills=tuple(combat_skills),
            present_npcs=npc_views,
            npc_conversations=tuple(
                ConversationView(
                    npc=npc, messages=tuple(conversation_by_npc.get(npc.id, ())[-20:]),
                    suggested_responses=SUGGESTED_RESPONSES,
                    last_check=check_by_npc.get(npc.id, ""),
                    merchant=merchant_view(npc),
                )
                for npc in npc_views
            ),
            crafting_recipes=tuple(crafting_recipes),
            pending_crafting_result=crafting_result_view,
            campaign_name=plain_name(str(campaign["name"])),
            is_preset_campaign=preset_flag is not None,
            abilities=tuple(skill for skill in combat_skills if skill.kind == "ability"),
            spells=tuple(skill for skill in combat_skills if skill.kind == "spell"),
            inventory=tuple(slot for slot in inventory if not slot.is_empty)[
                : int(character["inventory_capacity"])
            ],
            inventory_capacity=int(character["inventory_capacity"]),
        )
