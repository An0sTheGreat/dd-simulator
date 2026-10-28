"""Application-facing orchestration for campaign persistence and projection."""

from __future__ import annotations

from dataclasses import asdict, replace
from decimal import Decimal, InvalidOperation
import json
import re
import sqlite3
from collections.abc import Callable
from uuid import uuid4

from dd_simulator.state.character_creation import (
    SKILLS,
    DEFAULT_CONTENT_PREFERENCES,
    CharacterCreationDraft,
    CharacterCreationValidator,
    ability_modifier,
    level_one_hit_points,
    plain_name,
)
from dd_simulator.state.combat import (
    CombatActionResult,
    CombatCommand,
    CombatNarrationProvider,
    CombatService,
    EnemySpec,
)
from dd_simulator.state.commerce import CommerceQuote, CommerceResult, CommerceService
from dd_simulator.state.crafting import CraftingResult, CraftingService, seed_crafting_recipes
from dd_simulator.state.database import GameStateDatabase
from dd_simulator.state.dialogue import DialogueNarrationProvider, DialogueResult, DialogueService
from dd_simulator.state.errors import (
    ActionCancelledError,
    ActionResolutionError,
    ActionValidationError,
    CombatError,
    GameStateError,
    IncompleteGameStateError,
    ItemActionError,
)
from dd_simulator.state.item_actions import (
    ItemAction,
    ItemCommand,
    ItemMutationResult,
    decode_effects,
    item_definition,
    materialize_item_metadata,
    recalculate_character_item_totals,
)
from dd_simulator.state.item_catalog import catalog_item, loot_shortlist, select_loot
from dd_simulator.state.models import CampaignRecord
from dd_simulator.state.projection import DashboardProjection
from dd_simulator.state.presets import active_preset_context, seed_preset_campaign
from dd_simulator.state.progression import allocate_ability_points
from dd_simulator.state.quests import (
    QuestService,
    check_deadlines,
    complete_objective,
    progress_quests,
)
from dd_simulator.state.repositories import CampaignRepository
from dd_simulator.state.reliability import (
    CampaignCheckpoint,
    ReliabilityService,
    RepairIssue,
    RepairResult,
    ReplayResult,
)
from dd_simulator.state.seed import DEMO_CAMPAIGN_ID, seed_demo_campaign
from dd_simulator.state.turns import (
    ActionOutcome,
    ActionOutcomeProvider,
    ActionResolutionResult,
    NarrativeSegment,
    ProposedStateChange,
    claim_turn_notes,
    record_turn_note,
)
from dd_simulator.state.travel import (
    CampResult,
    TravelNarrationProvider,
    TravelResult,
    TravelService,
)
from dd_simulator.state.visuals import VisualRegistryService
from dd_simulator.ui.models.presentation import DashboardView, NarrativeMessageView


class GameStateService:
    def __init__(self, database: GameStateDatabase) -> None:
        self.database = database
        self.campaigns = CampaignRepository(database)
        self.dashboard_projection = DashboardProjection(database)
        self.combat = CombatService(database)
        self.commerce = CommerceService(database)
        self.crafting = CraftingService(database)
        self.quests = QuestService(database)
        self.travel = TravelService(database)
        self.dialogue = DialogueService(database)
        self.visuals = VisualRegistryService(database)
        self.reliability = ReliabilityService(database)

    def initialize(self) -> int:
        version = self.database.initialize()
        self.visuals.initialize_storage()
        self.combat.sync_character_catalogs()
        return version

    def ensure_demo_campaign(self) -> str:
        active = self.campaigns.active_campaign_id()
        active_record = self.campaigns.get(active) if active else None
        if active_record is not None and active_record.creation_complete:
            return active
        replacement = next(
            (campaign for campaign in self.campaigns.list_campaigns()
             if campaign.creation_complete),
            None,
        )
        if replacement is not None:
            self.campaigns.select(replacement.campaign_id)
            return replacement.campaign_id
        demo = self.campaigns.get(DEMO_CAMPAIGN_ID)
        if demo is None:
            campaign_id = seed_demo_campaign(self.database)
            self.combat.sync_character_catalogs()
            return campaign_id
        self.campaigns.select(DEMO_CAMPAIGN_ID)
        return DEMO_CAMPAIGN_ID

    def list_campaigns(self) -> tuple[CampaignRecord, ...]:
        return self.campaigns.list_campaigns()

    def create_campaign(self, name: str) -> CampaignRecord:
        return self.campaigns.create(name)

    def delete_campaign(self, campaign_id: str) -> str:
        replacement = self.campaigns.delete(campaign_id)
        return replacement or self.ensure_demo_campaign()

    def complete_character_creation(
        self,
        draft: CharacterCreationDraft,
        *,
        opening_text: str | None = None,
    ) -> str:
        """Validate and atomically create a dashboard-ready campaign."""

        errors = CharacterCreationValidator.validate(draft)
        if errors:
            first_field = next(iter(errors))
            raise ValueError(f"{first_field}: {errors[first_field]}")

        campaign_id = f"campaign-{uuid4().hex}"
        character_id = f"character-{uuid4().hex}"
        quest_id = f"quest-{uuid4().hex}"
        location_id = f"location-{uuid4().hex}"
        campaign_name = plain_name(draft.campaign_name)
        character_name = plain_name(draft.name)
        campaign_premise = draft.campaign_description.strip()
        initial_narrative = (opening_text or campaign_premise).strip()
        initial_narrative = initial_narrative.replace(draft.name, character_name)
        opening_paragraphs = tuple(
            line.strip() for line in initial_narrative.splitlines() if line.strip()
        )
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO campaigns(id, name, creation_complete, premise) VALUES (?, ?, 1, ?)",
                (campaign_id, campaign_name, campaign_premise),
            )
            connection.execute(
                "INSERT INTO campaign_clock(campaign_id, day, period, time_label) "
                "VALUES (?, 1, 'Morning', 'Morning, Day 1')",
                (campaign_id,),
            )
            connection.execute(
                """
                INSERT INTO campaign_preferences(
                    campaign_id, world_type, tone, difficulty, content_preferences,
                    visual_style, camera_style
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_id, draft.world_type.strip(), draft.tone.strip(),
                    draft.difficulty.strip(),
                    draft.content_preferences.strip() or DEFAULT_CONTENT_PREFERENCES,
                    draft.visual_style.strip(), draft.camera_style.strip(),
                ),
            )
            connection.execute(
                """
                INSERT INTO locations(
                    id, campaign_id, name, region, weather, danger, route_status,
                    is_current, description, biome, discovered, visit_count,
                    first_discovered_at, last_visited_at, can_camp, map_x, map_y
                ) VALUES (?, ?, ?, ?, 'Clear skies', 'Unknown danger',
                          'The road ahead is uncharted', 1, ?, 'road', 1, 1,
                          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, 0, 0)
                """,
                (
                    location_id, campaign_id, draft.starting_location.strip(),
                    draft.starting_region.strip(),
                    campaign_premise,
                ),
            )
            connection.execute(
                """
                INSERT INTO characters(
                    id, campaign_id, name, level, character_class, portrait_initials,
                    currency, carry_weight, carry_capacity, inventory_capacity, is_player,
                    species, age, gender_identity, pronouns, body_description,
                    face_description, clothing_style, background, personality_json,
                    primary_strength, meaningful_flaw, motivation, biography, backstory
                ) VALUES (?, ?, ?, 1, ?, ?, 100, 0, 100, 320, 1, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    character_id, campaign_id, character_name,
                    draft.character_class.strip(), _initials(character_name),
                    draft.ancestry.strip(), draft.age, draft.gender_identity.strip(),
                    draft.pronouns.strip(), draft.body_description.strip(),
                    draft.face_description.strip(), draft.clothing_style.strip(),
                    draft.background.strip(), json.dumps(draft.personalities),
                    draft.primary_strength.strip(), draft.meaningful_flaw.strip(),
                    draft.motivation.strip(), draft.biography.strip(),
                    draft.backstory.strip(),
                ),
            )
            attributes = draft.ability_scores
            connection.executemany(
                """
                INSERT INTO character_attributes(
                    id, character_id, name, value, modifier, display_order
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        f"{character_id}-attribute-{index}", character_id, name,
                        value, ability_modifier(value), index,
                    )
                    for index, (name, value) in enumerate(attributes)
                ),
            )
            constitution = dict(attributes)["Constitution"]
            hit_points = level_one_hit_points(draft.character_class, constitution)
            resources = (
                ("health", "Health", hit_points, hit_points, 1, 1),
                ("stamina", "Stamina", 10, 10, 1, 1),
                ("focus", "Focus", 10, 10, 0, 1),
                ("resolve", "Resolve", 10, 10, 0, 1),
                ("experience", "Experience", 0, 300, 0, 0),
            )
            connection.executemany(
                """
                INSERT INTO character_resources(
                    id, character_id, name, current_value, maximum_value,
                    resource_type, tooltip, sidebar_tooltip, display_order,
                    show_in_summary, show_in_sidebar
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        f"{character_id}-resource-{kind}", character_id, name,
                        current, maximum, kind, f"Current and maximum {name.lower()}",
                        f"Current and maximum {name.lower()}", index, summary, sidebar,
                    )
                    for index, (kind, name, current, maximum, summary, sidebar)
                    in enumerate(resources)
                ),
            )
            selected_skills = set(draft.skills)
            connection.executemany(
                """
                INSERT INTO skills(
                    id, character_id, name, level, current_xp, next_level_xp,
                    bonus, locked, recently_increased, display_order
                ) VALUES (?, ?, ?, ?, 0, 100, ?, 0, 0, ?)
                """,
                (
                    (
                        f"{character_id}-skill-{index}", character_id, name,
                        10 if name in selected_skills else 1,
                        2 if name in selected_skills else 0,
                        index,
                    )
                    for index, name in enumerate(SKILLS)
                ),
            )

            item_names = [
                (value.strip(), 1)
                for value in (
                    draft.primary_weapon, draft.secondary_weapon, draft.ranged_weapon,
                    draft.armor, draft.shield, draft.important_tool, draft.keepsake,
                )
                if value.strip()
            ]
            ranged_name = draft.ranged_weapon.strip().casefold()
            ammunition_name = (
                "Bolts"
                if "crossbow" in ranged_name
                else "Arrows"
                if "bow" in ranged_name
                else "Sling Stones"
                if "sling" in ranged_name
                else ""
            )
            if ammunition_name:
                item_names.append((ammunition_name, 20))
            item_records = []
            for index, (name, quantity) in enumerate(item_names):
                definition = item_definition(name)
                item_records.append(
                    (
                        f"{character_id}-item-{index}", character_id, index, index, name, quantity,
                        definition.item_type, int(definition.consumable),
                        definition.charges, definition.maximum_charges,
                        definition.equip_slot, definition.effect_json(),
                    )
                )
            connection.executemany(
                """
                INSERT INTO inventory_items(
                    id, character_id, slot_index, inventory_position, name, quantity, rarity, description,
                    item_type, consumable, charges, maximum_charges, equip_slot,
                    use_effect_json
                ) VALUES (?, ?, ?, ?, ?, ?, 'common', 'Starting equipment', ?, ?, ?, ?, ?, ?)
                """,
                item_records,
            )
            for item_id, *_rest in item_records:
                materialize_item_metadata(
                    connection, item_id, difficulty=draft.difficulty
                )
            equipment = (
                ("Main Hand", draft.primary_weapon),
                ("Off Hand", draft.shield or draft.secondary_weapon),
                ("Head", ""), ("Body", draft.armor), ("Hands", ""),
                ("Feet", ""), ("Neck", ""), ("Ring", ""),
                ("Ammunition", ammunition_name),
            )
            available_item_ids: dict[str, list[str]] = {}
            for item_id, _character_id, _legacy_index, _position, name, _quantity, *_metadata in item_records:
                available_item_ids.setdefault(name, []).append(item_id)
            equipment_records = []
            for index, (slot, item) in enumerate(equipment):
                matching_ids = available_item_ids.get(item, [])
                inventory_item_id = matching_ids.pop(0) if item and matching_ids else None
                equipment_records.append(
                    (
                        f"{character_id}-equipment-{index}", character_id, index,
                        slot, item or None, "100%" if item else "", inventory_item_id,
                    )
                )
            connection.executemany(
                """
                INSERT INTO equipment_slots(
                    id, character_id, slot_index, slot_name, item_name, condition,
                    inventory_item_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                equipment_records,
            )
            connection.execute(
                "UPDATE inventory_items SET inventory_position = NULL WHERE id IN "
                "(SELECT inventory_item_id FROM equipment_slots WHERE character_id = ? "
                "AND inventory_item_id IS NOT NULL)",
                (character_id,),
            )
            recalculate_character_item_totals(connection, character_id)
            connection.execute(
                """
                INSERT INTO quests(
                    id, campaign_id, title, status, summary, progress_current,
                    progress_maximum, selected, display_order
                ) VALUES (?, ?, 'A New Beginning', 'active',
                          'Discover what awaits at your starting location.', 0, 1, 1, 0)
                """,
                (quest_id, campaign_id),
            )
            connection.execute(
                """
                INSERT INTO quest_objectives(
                    id, quest_id, text, completed, optional, display_order,
                    trigger_type, trigger_target
                ) VALUES (?, ?, 'Take stock of your surroundings', 0, 0, 0,
                          'custom_action', 'look')
                """,
                (f"{quest_id}-objective-0", quest_id),
            )
            connection.execute(
                """
                INSERT INTO narratives(
                    campaign_id, title, paragraphs_json, dialogue, prompt,
                    suggested_actions_json
                ) VALUES (?, ?, ?, '', 'What would you like to do?', ?)
                """,
                (
                    campaign_id,
                    draft.starting_location.strip(),
                    json.dumps(opening_paragraphs),
                    json.dumps((
                        "Look around",
                        "Review equipment",
                        "Move forward",
                        "Listen for nearby activity",
                        "Study the surrounding terrain",
                        "Recall what you know of this region",
                    )),
                ),
            )
            opening_messages = tuple(
                (
                    f"{campaign_id}-message-{index}", campaign_id, 0, index,
                    "narrative", paragraph,
                )
                for index, paragraph in enumerate(opening_paragraphs)
            )
            connection.executemany(
                "INSERT INTO narrative_messages("
                "id, campaign_id, turn_number, sequence, kind, text"
                ") VALUES (?, ?, ?, ?, ?, ?)",
                opening_messages,
            )
            connection.execute(
                """
                INSERT INTO events(
                    id, campaign_id, time_label, category, summary, sequence, is_recent
                ) VALUES (?, ?, 'Day 1, Morning', 'system', ?, 0, 1)
                """,
                (
                    f"{campaign_id}-event-0", campaign_id,
                    f"{character_name}'s adventure began.",
                ),
            )
            if draft.preset_id:
                seed_preset_campaign(
                    connection, campaign_id, character_id, draft.preset_id
                )
            connection.execute(
                """
                INSERT INTO app_settings(key, value) VALUES ('active_campaign_id', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (campaign_id,),
            )
            self.combat.ensure_character_combat_catalog(connection, campaign_id)
            seed_crafting_recipes(connection, campaign_id)
        return campaign_id

    def replace_campaign_introduction(self, campaign_id: str, introduction: str) -> None:
        """Atomically replace the temporary opening message and persist immediately."""

        normalized = " ".join(introduction.split())
        if not normalized:
            raise ValueError("Campaign introduction cannot be empty.")
        if len(normalized) > 1800:
            normalized = normalized[:1800].rsplit(" ", 1)[0].rstrip() + "…"
        with self.database.transaction() as connection:
            exists = connection.execute(
                "SELECT 1 FROM campaigns WHERE id = ?", (campaign_id,)
            ).fetchone()
            if exists is None:
                raise KeyError(campaign_id)
            connection.execute(
                "UPDATE narratives SET paragraphs_json = ? WHERE campaign_id = ?",
                (json.dumps((normalized,)), campaign_id),
            )
            connection.execute(
                "DELETE FROM narrative_messages WHERE campaign_id = ? AND turn_number = 0",
                (campaign_id,),
            )
            connection.execute(
                "INSERT INTO narrative_messages("
                "id, campaign_id, turn_number, sequence, kind, text"
                ") VALUES (?, ?, 0, 0, 'narrative', ?)",
                (f"{campaign_id}-message-0", campaign_id, normalized),
            )

    def execute_item_command(self, command: ItemCommand) -> ItemMutationResult:
        """Validate and atomically apply one inventory or equipment mutation."""

        if command.slot_index < 0:
            raise ItemActionError("Item slots cannot be negative.")
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise ItemActionError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        with self.database.transaction() as connection:
            character = connection.execute(
                "SELECT characters.id, COALESCE(campaign_preferences.difficulty, 'Adventurer') "
                "AS difficulty FROM characters LEFT JOIN campaign_preferences "
                "ON campaign_preferences.campaign_id = characters.campaign_id "
                "WHERE characters.campaign_id = ? AND characters.is_player = 1",
                (campaign_id,),
            ).fetchone()
            if character is None:
                raise ItemActionError("The active campaign has no player character.")
            character_id = str(character["id"])
            if command.action is ItemAction.UNEQUIP:
                result = self._unequip(
                    connection,
                    character_id,
                    command.slot_index,
                    command.destination_index,
                )
            else:
                item = connection.execute(
                    "SELECT * FROM inventory_items WHERE character_id = ? AND inventory_position = ?",
                    (character_id, command.slot_index),
                ).fetchone()
                if item is None:
                    raise ItemActionError("That inventory slot is empty.")
                materialize_item_metadata(
                    connection, str(item["id"]), difficulty=str(character["difficulty"])
                )
                item = connection.execute(
                    "SELECT * FROM inventory_items WHERE id = ?", (item["id"],)
                ).fetchone()
                if command.action is ItemAction.USE:
                    result = self._use_item(connection, character_id, item)
                elif command.action is ItemAction.EQUIP:
                    result = self._equip(
                        connection, character_id, item, command.destination_index
                    )
                elif command.action is ItemAction.DROP:
                    result = self._drop(connection, character_id, item)
                else:  # pragma: no cover - enum keeps public callers inside the contract
                    raise ItemActionError(f"Unsupported item action: {command.action}")
            recalculate_character_item_totals(connection, character_id)
            self._record_inventory_event(connection, campaign_id, result.summary)
            trigger = {
                ItemAction.USE: "item_use",
                ItemAction.EQUIP: "custom_action",
                ItemAction.UNEQUIP: "custom_action",
                ItemAction.DROP: "custom_action",
            }.get(command.action, "custom_action")
            progress_quests(
                connection, campaign_id, trigger, result.item_name,
                detail=result.summary,
            )
            connection.execute(
                "UPDATE campaigns SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (campaign_id,),
            )
        self.reliability.record_audit(
            campaign_id,
            "inventory",
            result.summary,
            {
                "action": command.action.value,
                "slot_index": command.slot_index,
                "destination_index": command.destination_index,
            },
            before_checksum=before_checksum,
        )
        return result

    def move_inventory_item(self, source: int, destination: int) -> str:
        """Atomically move or swap two visible inventory positions."""

        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise ItemActionError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        with self.database.transaction() as connection:
            character = connection.execute(
                "SELECT id, inventory_capacity FROM characters "
                "WHERE campaign_id = ? AND is_player = 1", (campaign_id,),
            ).fetchone()
            if character is None:
                raise ItemActionError("The active campaign has no player character.")
            capacity = int(character["inventory_capacity"])
            if not (0 <= source < capacity and 0 <= destination < capacity):
                raise ItemActionError("That inventory destination is outside the bag.")
            if source == destination:
                return "Item is already in that slot."
            character_id = str(character["id"])
            source_item = connection.execute(
                "SELECT id, name FROM inventory_items WHERE character_id = ? "
                "AND inventory_position = ?", (character_id, source),
            ).fetchone()
            if source_item is None:
                raise ItemActionError("The source inventory slot is empty.")
            destination_item = connection.execute(
                "SELECT id FROM inventory_items WHERE character_id = ? "
                "AND inventory_position = ?", (character_id, destination),
            ).fetchone()
            connection.execute(
                "UPDATE inventory_items SET inventory_position = NULL WHERE id = ?",
                (source_item["id"],),
            )
            if destination_item is not None:
                connection.execute(
                    "UPDATE inventory_items SET inventory_position = ? WHERE id = ?",
                    (source, destination_item["id"]),
                )
            connection.execute(
                "UPDATE inventory_items SET inventory_position = ? WHERE id = ?",
                (destination, source_item["id"]),
            )
        summary = f"Moved {source_item['name']} to slot {destination + 1}."
        self.reliability.record_audit(
            campaign_id, "inventory_move", summary,
            {"source": source, "destination": destination},
            before_checksum=before_checksum,
        )
        return summary

    def auto_sort_inventory(self, sort_mode: str = "default") -> str:
        """Consolidate safe stacks and apply the documented deterministic ordering."""

        sort_mode = sort_mode.casefold()
        if sort_mode not in {"default", "rarity", "type", "value"}:
            raise ItemActionError(f"Unknown inventory sort mode: {sort_mode}.")

        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise ItemActionError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        with self.database.transaction() as connection:
            character = connection.execute(
                "SELECT id FROM characters WHERE campaign_id = ? AND is_player = 1",
                (campaign_id,),
            ).fetchone()
            if character is None:
                raise ItemActionError("The active campaign has no player character.")
            character_id = str(character["id"])
            rows = list(connection.execute(
                "SELECT * FROM inventory_items WHERE character_id = ? "
                "AND inventory_position IS NOT NULL ORDER BY inventory_position",
                (character_id,),
            ).fetchall())
            stack_owner: dict[tuple[object, ...], sqlite3.Row] = {}
            retained: list[sqlite3.Row] = []
            for row in rows:
                stackable = (
                    not bool(row["quest_item"]) and not str(row["equip_slot"])
                    and row["durability"] is None and row["charges"] is None
                    and str(row["item_type"]) not in {"weapon", "armor", "equipment"}
                )
                key = (str(row["name"]).casefold(), str(row["rarity"]), str(row["item_type"]))
                owner = stack_owner.get(key) if stackable else None
                if owner is None:
                    if stackable:
                        stack_owner[key] = row
                    retained.append(row)
                else:
                    connection.execute(
                        "UPDATE inventory_items SET quantity = quantity + ? WHERE id = ?",
                        (int(row["quantity"]), owner["id"]),
                    )
                    connection.execute("DELETE FROM inventory_items WHERE id = ?", (row["id"],))
            category_order = {
                "weapon": 1, "armor": 2, "equipment": 2, "potion": 3,
                "consumable": 3, "ammunition": 4, "tool": 4, "travel": 4,
                "currency": 5, "valuable": 5, "crafting": 5,
            }
            rarity_order = {"legendary": 0, "epic": 1, "rare": 2, "uncommon": 3, "common": 4}
            if sort_mode == "rarity":
                retained.sort(key=lambda row: (
                    rarity_order.get(str(row["rarity"]).casefold(), 5),
                    str(row["name"]).casefold(),
                    int(row["inventory_position"]),
                ))
            elif sort_mode == "type":
                retained.sort(key=lambda row: (
                    str(row["item_type"]).casefold(),
                    str(row["name"]).casefold(),
                    rarity_order.get(str(row["rarity"]).casefold(), 5),
                    int(row["inventory_position"]),
                ))
            elif sort_mode == "value":
                retained.sort(key=lambda row: (
                    -int(row["value_gp"]),
                    str(row["name"]).casefold(),
                    int(row["inventory_position"]),
                ))
            else:
                retained.sort(key=lambda row: (
                    0 if bool(row["quest_item"]) else category_order.get(str(row["item_type"]).casefold(), 6),
                    rarity_order.get(str(row["rarity"]).casefold(), 5),
                    str(row["name"]).casefold(),
                    -(int(row["durability"]) if row["durability"] is not None else 101),
                ))
            connection.execute(
                "UPDATE inventory_items SET inventory_position = NULL "
                "WHERE character_id = ? AND inventory_position IS NOT NULL", (character_id,),
            )
            for index, row in enumerate(retained):
                connection.execute(
                    "UPDATE inventory_items SET inventory_position = ? WHERE id = ?",
                    (index, row["id"]),
                )
        summary = f"Auto-sorted {len(retained)} inventory stacks by {sort_mode}."
        self.reliability.record_audit(
            campaign_id, "inventory_sort", summary, {"sort_mode": sort_mode},
            before_checksum=before_checksum,
        )
        return summary

    def resolve_npc_dialogue(
        self,
        npc_id: str,
        player_text: str,
        *,
        narrator: DialogueNarrationProvider | None = None,
    ) -> DialogueResult:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise GameStateError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        result = self.dialogue.resolve(campaign_id, npc_id, player_text, narrator=narrator)
        self.reliability.record_audit(
            campaign_id, "dialogue", f"Spoke with {npc_id}.",
            {"npc_id": npc_id, "player_text": result.player_text},
            before_checksum=before_checksum,
        )
        return result

    def ensure_local_interaction_npc(self, player_text: str, *, merchant: bool = False) -> str | None:
        """Resolve a known local person without creating one from player-authored text."""

        role = self.addressed_npc_role(player_text)
        if not role:
            return None
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            return None
        with self.database.transaction() as connection:
            location = connection.execute(
                "SELECT id FROM locations WHERE campaign_id = ? AND is_current = 1",
                (campaign_id,),
            ).fetchone()
            if location is None:
                return None
            candidates = connection.execute(
                "SELECT id, name, title FROM npcs WHERE campaign_id = ? AND location_id = ? "
                "AND available = 1 AND known = 1",
                (campaign_id, location["id"]),
            ).fetchall()
            normalized_role = role.casefold()
            npc = next(
                (
                    row for row in candidates
                    if normalized_role in f"{row['name']} {row['title']}".casefold()
                    or str(row["name"]).casefold() in normalized_role
                    or self._npc_role_alias_matches(
                        normalized_role,
                        f"{row['name']} {row['title']}".casefold(),
                    )
                ),
                None,
            )
            if npc is None:
                return None
            npc_id = str(npc["id"])
            if merchant:
                self._ensure_local_merchant_stock(connection, npc_id, campaign_id)
        return npc_id

    @staticmethod
    def _npc_role_alias_matches(role: str, candidate: str) -> bool:
        """Match common occupations without treating arbitrary phrases as people."""

        alias_groups = (
            {"barmaid", "barkeep", "bartender", "innkeeper", "tavernkeeper"},
            {"merchant", "trader", "shopkeeper", "vendor"},
            {"guard", "watchman", "watchwoman", "soldier"},
            {"healer", "medic", "physician", "doctor"},
        )
        role_words = set(re.findall(r"[a-z]+", role))
        candidate_words = set(re.findall(r"[a-z]+", candidate))
        return any(
            role_words.intersection(group) and candidate_words.intersection(group)
            for group in alias_groups
        )

    @staticmethod
    def addressed_npc_role(player_text: str) -> str:
        text = " ".join(player_text.split())
        patterns = (
            r"\b(?:ask|tell|question|greet)\s+(?:the|a|an)\s+"
            r"([a-z][a-z' /-]{1,60}?)(?=\s+(?:if|whether|about|for|to|that|what|where|why|how)\b|[,.?!]|$)",
            r"\b(?:speak|talk|trade|barter)\s+(?:to|with)\s+(?:the|a|an)?\s*"
            r"([a-z][a-z' /-]{1,60}?)(?=\s+(?:if|whether|about|for|to|that|what|where|why|how)\b|[,.?!]|$)",
            r"\b(?:buy|purchase)\s+.+?\s+from\s+(?:the|a|an)?\s*"
            r"([a-z][a-z' /-]{1,60}?)(?=[,.?!]|$)",
        )
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match is None:
                continue
            role = re.sub(r"\s*/\s*", " or ", match.group(1)).strip(" -")
            if role.casefold() not in {"him", "her", "them", "it", "someone", "anyone"}:
                return role[:80]
        return ""

    @staticmethod
    def _ensure_local_merchant_stock(
        connection: sqlite3.Connection,
        npc_id: str,
        campaign_id: str,
    ) -> None:
        if connection.execute(
            "SELECT 1 FROM merchant_stock WHERE npc_id = ? LIMIT 1", (npc_id,)
        ).fetchone() is not None:
            return
        for index, item in enumerate(select_loot(f"merchant:{campaign_id}:{npc_id}", count=6)):
            durable = item.category in {"armor", "weapon", "tool", "magic_item"}
            connection.execute(
                "INSERT INTO merchant_stock(id, npc_id, name, quantity, rarity, durability, "
                "maximum_durability, base_value, description, display_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"stock-{npc_id}-{item.id}", npc_id, item.name,
                    1 if item.tier > 1 else 2, item.rarity,
                    100 if durable else None, 100 if durable else None,
                    max(1, 5 * (item.tier + 1)), item.description, index,
                ),
            )

    def quote_trade(self, npc_id: str, action: str, item_id: str) -> CommerceQuote:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise GameStateError("No active campaign is available.")
        return self.commerce.quote(campaign_id, npc_id, action, item_id)

    def complete_trade(self, npc_id: str, action: str, item_id: str) -> CommerceResult:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise GameStateError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        result = self.commerce.transact(campaign_id, npc_id, action, item_id)
        self.reliability.record_audit(
            campaign_id,
            "commerce",
            result.summary,
            {
                "action": action,
                "npc_id": npc_id,
                "item_id": item_id,
                "total_price": result.quote.total_price,
            },
            before_checksum=before_checksum,
        )
        return result

    def craft_recipe(self, recipe_id: str) -> CraftingResult:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise GameStateError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        result = self.crafting.craft(campaign_id, recipe_id)
        self.reliability.record_audit(
            campaign_id,
            "crafting",
            result.summary,
            {
                "recipe_id": recipe_id,
                "result_id": result.id,
                "success": result.success,
                "output_name": result.output_name,
                "output_quantity": result.output_quantity,
            },
            before_checksum=before_checksum,
        )
        return result

    def acknowledge_crafting_result(self, result_id: str) -> None:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise GameStateError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        self.crafting.acknowledge(campaign_id, result_id)
        self.reliability.record_audit(
            campaign_id,
            "crafting",
            "Acknowledged crafting result.",
            {"result_id": result_id},
            before_checksum=before_checksum,
        )

    def start_combat(
        self,
        *,
        enemies: tuple[EnemySpec, ...] | None = None,
        narrator: CombatNarrationProvider | None = None,
    ) -> CombatActionResult:
        """Start and persist an encounter for the active campaign."""

        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise CombatError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        if enemies is None:
            result = self.combat.start_generated_encounter(
                campaign_id, narrator=narrator
            )
        else:
            result = self.combat.start_encounter(
                campaign_id, enemies=enemies, narrator=narrator
            )
        self.reliability.record_audit(
            campaign_id, "combat_start", "Started a combat encounter.",
            {"encounter_id": result.encounter_id}, before_checksum=before_checksum,
        )
        return result

    def execute_combat_command(
        self,
        command: CombatCommand,
        *,
        narrator: CombatNarrationProvider | None = None,
    ) -> CombatActionResult:
        """Resolve one player action and all intervening enemy turns atomically."""

        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise CombatError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        result = self.combat.perform_action(campaign_id, command, narrator=narrator)
        summary = " ".join(result.summaries)
        self.reliability.record_audit(
            campaign_id, "combat_action", summary,
            {"action": command.action.value, "target_id": command.target_id},
            before_checksum=before_checksum,
        )
        return result

    def claim_combat_reward_item(self, reward_item_id: str) -> str:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise CombatError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        summary = self.combat.claim_reward_item(campaign_id, reward_item_id)
        self.reliability.record_audit(
            campaign_id, "combat_reward", summary, {"reward_item_id": reward_item_id},
            before_checksum=before_checksum,
        )
        return summary

    def claim_all_combat_rewards(
        self, reward_id: str
    ) -> tuple[tuple[str, ...], int]:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise CombatError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        result = self.combat.claim_all_reward_items(campaign_id, reward_id)
        self.reliability.record_audit(
            campaign_id, "combat_reward", "Claimed available combat rewards.",
            {"reward_id": reward_id}, before_checksum=before_checksum,
        )
        return result

    def acknowledge_combat_reward(self, reward_id: str) -> None:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise CombatError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        self.combat.acknowledge_reward(campaign_id, reward_id)
        self.reliability.record_audit(
            campaign_id, "combat_reward", "Acknowledged combat rewards.",
            {"reward_id": reward_id}, before_checksum=before_checksum,
        )

    def abandon_quest(self, quest_id: str) -> str:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise IncompleteGameStateError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        summary = self.quests.abandon(campaign_id, quest_id)
        self.reliability.record_audit(
            campaign_id, "quest", summary, {"quest_id": quest_id, "action": "abandon"},
            before_checksum=before_checksum,
        )
        return summary

    def claim_quest_reward_item(self, item_id: str) -> str:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise IncompleteGameStateError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        summary = self.quests.claim_item(campaign_id, item_id)
        self.reliability.record_audit(
            campaign_id, "quest_reward", summary, {"reward_item_id": item_id},
            before_checksum=before_checksum,
        )
        return summary

    def acknowledge_quest_reward(self, reward_id: str) -> None:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise IncompleteGameStateError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        self.quests.acknowledge(campaign_id, reward_id)
        self.reliability.record_audit(
            campaign_id, "quest_reward", "Acknowledged quest rewards.",
            {"reward_id": reward_id}, before_checksum=before_checksum,
        )

    def travel_to(
        self,
        route_id: str,
        *,
        narrator: TravelNarrationProvider | None = None,
    ) -> TravelResult:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise IncompleteGameStateError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        result = self.travel.travel(campaign_id, route_id, narrator=narrator)
        if result.encounter_required:
            encounter = self.combat.start_generated_encounter(campaign_id)
            with self.database.transaction() as connection:
                self.travel.attach_encounter(
                    connection, campaign_id, result.history_id, encounter.encounter_id
                )
        self.reliability.record_audit(
            campaign_id, "travel", result.summary,
            {"route_id": route_id, "history_id": result.history_id},
            before_checksum=before_checksum,
        )
        return result

    def make_camp(
        self,
        *,
        duration_minutes: int = 480,
        narrator: TravelNarrationProvider | None = None,
    ) -> CampResult:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise IncompleteGameStateError("No active campaign is available.")
        before_checksum = self.reliability.checksum(campaign_id)
        result = self.travel.camp(
            campaign_id, duration_minutes=duration_minutes, narrator=narrator
        )
        self.reliability.record_audit(
            campaign_id, "camp", result.summary,
            {"duration_minutes": duration_minutes}, before_checksum=before_checksum,
        )
        return result

    def build_action_context(self) -> dict[str, object]:
        """Build a fresh, bounded, ID-bearing snapshot for one non-combat turn."""

        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise ActionResolutionError("No active campaign is available.")
        with self.database.connect() as connection:
            character = connection.execute(
                "SELECT * FROM characters WHERE campaign_id = ? AND is_player = 1",
                (campaign_id,),
            ).fetchone()
            if character is None:
                raise ActionResolutionError("The active campaign has no player character.")
            character_id = str(character["id"])
            clock = connection.execute(
                "SELECT * FROM campaign_clock WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            location = connection.execute(
                "SELECT * FROM locations WHERE campaign_id = ? AND is_current = 1",
                (campaign_id,),
            ).fetchone()
            narrative = connection.execute(
                "SELECT * FROM narratives WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            preferences = connection.execute(
                "SELECT world_type, content_preferences, tone, difficulty, visual_style, "
                "camera_style FROM campaign_preferences "
                "WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            campaign = connection.execute(
                "SELECT name, premise FROM campaigns WHERE id = ?", (campaign_id,)
            ).fetchone()
            resources = connection.execute(
                "SELECT id, name, resource_type, current_value, maximum_value "
                "FROM character_resources WHERE character_id = ? ORDER BY display_order",
                (character_id,),
            ).fetchall()
            inventory = connection.execute(
                "SELECT id, name, quantity, item_type, charges, maximum_charges, "
                "durability, maximum_durability, quest_item, equip_slot, description, "
                "item_category, weight, value_gp, identified, damage_text, armor_value, "
                "healing_value, compatible_slots_json, requirements_json, bonuses_json "
                "FROM inventory_items WHERE character_id = ? AND inventory_position IS NOT NULL "
                "ORDER BY inventory_position LIMIT 28",
                (character_id,),
            ).fetchall()
            equipment = connection.execute(
                "SELECT id, slot_name, item_name, inventory_item_id FROM equipment_slots "
                "WHERE character_id = ? ORDER BY slot_index",
                (character_id,),
            ).fetchall()
            attributes = connection.execute(
                "SELECT name, value FROM character_attributes WHERE character_id = ? "
                "ORDER BY display_order",
                (character_id,),
            ).fetchall()
            objectives = connection.execute(
                """
                SELECT quest_objectives.id, quest_objectives.text,
                       quest_objectives.completed, quest_objectives.optional,
                       quests.id AS quest_id, quests.title AS quest_title
                FROM quest_objectives
                JOIN quests ON quests.id = quest_objectives.quest_id
                WHERE quests.campaign_id = ? AND quests.status = 'active'
                ORDER BY quests.display_order, quest_objectives.display_order
                LIMIT 12
                """,
                (campaign_id,),
            ).fetchall()
            locations = connection.execute(
                "SELECT id, name, region, danger, route_status, is_current FROM locations "
                "WHERE campaign_id = ? AND discovered = 1 "
                "ORDER BY is_current DESC, name LIMIT 12",
                (campaign_id,),
            ).fetchall()
            events = connection.execute(
                "SELECT time_label, category, summary FROM events WHERE campaign_id = ? "
                "ORDER BY sequence DESC LIMIT 8",
                (campaign_id,),
            ).fetchall()
            people = connection.execute(
                "SELECT id, name, title, disposition, status, known FROM npcs "
                "WHERE campaign_id = ? AND location_id = ? AND available = 1 "
                "ORDER BY known DESC, name LIMIT 12",
                (campaign_id, None if location is None else location["id"]),
            ).fetchall()
            preset_context = active_preset_context(connection, campaign_id)

        loot_seed = (
            f"{campaign_id}:{0 if clock is None else int(clock['turn_number'])}:"
            f"{'' if location is None else location['id']}"
        )
        available_loot = loot_shortlist(loot_seed)
        player_context: dict[str, object] = {
            "id": character_id,
            "name": str(character["name"])[:120],
            "class": str(character["character_class"])[:120],
            "level": int(character["level"]),
            "ability_scores": {
                str(row["name"]): int(row["value"]) for row in attributes
            },
        }
        optional_player_context: dict[str, object] = {
            "ancestry": str(character["species"] or "")[:120],
            "age": int(character["age"] or 0),
            "gender_identity": str(character["gender_identity"] or "")[:120],
            "pronouns": str(character["pronouns"] or "")[:120],
            "background": str(character["background"] or "")[:160],
            "personality_traits": json.loads(
                str(character["personality_json"] or "[]")
            ),
            "primary_strength": str(character["primary_strength"] or "")[:300],
            "meaningful_flaw": str(character["meaningful_flaw"] or "")[:300],
            "motivation": str(character["motivation"] or "")[:500],
            "biography": str(character["biography"] or "")[:1600],
            "backstory": str(character["backstory"] or "")[:2000],
        }
        player_context.update(
            (key, value)
            for key, value in optional_player_context.items()
            if value not in ("", 0, [])
        )
        appearance = {
            "body": str(character["body_description"] or "")[:1000],
            "face": str(character["face_description"] or "")[:1000],
            "clothing": str(character["clothing_style"] or "")[:1000],
        }
        if any(appearance.values()):
            player_context["appearance"] = appearance
        context: dict[str, object] = {
            "campaign": {
                "id": campaign_id,
                "turn_number": int(clock["turn_number"]) if clock is not None else 0,
                "time": str(clock["time_label"]) if clock is not None else "",
                "tone": "" if preferences is None else str(preferences["tone"])[:120],
                "difficulty": "" if preferences is None else str(preferences["difficulty"])[:80],
                "content_preferences": (
                    "" if preferences is None else str(preferences["content_preferences"])[:1000]
                ),
                "world_type": (
                    "" if preferences is None else str(preferences["world_type"])[:160]
                ),
                "visual_style": (
                    "" if preferences is None else str(preferences["visual_style"])[:160]
                ),
                "camera_style": (
                    "" if preferences is None else str(preferences["camera_style"])[:160]
                ),
                "name": "" if campaign is None else str(campaign["name"])[:160],
                "premise": "" if campaign is None else str(campaign["premise"])[:4000],
            },
            "player": player_context,
            "current_scene": {
                "location_id": "" if location is None else str(location["id"]),
                "location": "" if location is None else str(location["name"])[:160],
                "region": "" if location is None else str(location["region"])[:160],
                "narrative_title": "" if narrative is None else str(narrative["title"])[:160],
                "narrative": (
                    []
                    if narrative is None
                    else [str(value)[:1000] for value in json.loads(str(narrative["paragraphs_json"]))[-3:]]
                ),
            },
            "resources": [
                {
                    "id": str(row["id"]),
                    "name": str(row["name"]),
                    "type": str(row["resource_type"]),
                    "current": int(row["current_value"]),
                    "maximum": int(row["maximum_value"]),
                }
                for row in resources
            ],
            "inventory": [
                {
                    "id": str(row["id"]),
                    "name": str(row["name"])[:160],
                    "quantity": int(row["quantity"]),
                    "type": str(row["item_type"]),
                    "charges": row["charges"],
                    "maximum_charges": row["maximum_charges"],
                    "durability": row["durability"],
                    "maximum_durability": row["maximum_durability"],
                    "quest_item": bool(row["quest_item"]),
                    "equip_slot": str(row["equip_slot"]),
                    "description": str(row["description"])[:500],
                    "category": str(row["item_category"]),
                    "weight": float(row["weight"]),
                    "value_gp": int(row["value_gp"]),
                    "identified": bool(row["identified"]),
                    "damage": str(row["damage_text"]),
                    "armor": int(row["armor_value"]),
                    "healing": int(row["healing_value"]),
                    "compatible_slots": json.loads(str(row["compatible_slots_json"])),
                    "requirements": decode_effects(str(row["requirements_json"])),
                    "bonuses": decode_effects(str(row["bonuses_json"])),
                }
                for row in inventory
            ],
            "equipment": [
                {
                    "id": str(row["id"]),
                    "slot": str(row["slot_name"]),
                    "item": None if row["item_name"] is None else str(row["item_name"]),
                    "inventory_item_id": row["inventory_item_id"],
                }
                for row in equipment
            ],
            "active_objectives": [
                {
                    "id": str(row["id"]),
                    "quest_id": str(row["quest_id"]),
                    "quest": str(row["quest_title"])[:200],
                    "text": str(row["text"])[:300],
                    "completed": bool(row["completed"]),
                    "optional": bool(row["optional"]),
                }
                for row in objectives
            ],
            "known_locations": [
                {
                    "id": str(row["id"]),
                    "name": str(row["name"])[:160],
                    "region": str(row["region"])[:160],
                    "danger": str(row["danger"])[:160],
                    "route_status": str(row["route_status"])[:240],
                    "current": bool(row["is_current"]),
                }
                for row in locations
            ],
            "recent_events": [
                {
                    "time": str(row["time_label"])[:100],
                    "category": str(row["category"])[:60],
                    "summary": str(row["summary"])[:420],
                }
                for row in reversed(events)
            ],
            "people_at_location": [
                {
                    "id": str(row["id"]),
                    "name": str(row["name"])[:160],
                    "title": str(row["title"])[:160],
                    "disposition": str(row["disposition"])[:80],
                    "status": str(row["status"])[:80],
                    "known": bool(row["known"]),
                }
                for row in people
            ],
            "available_loot": list(available_loot),
            "allowed_targets": {
                "resource_ids": [str(row["id"]) for row in resources],
                "inventory_item_ids": [str(row["id"]) for row in inventory],
                "examinable_inventory_item_ids": [str(row["id"]) for row in inventory],
                "equippable_inventory_item_ids": [
                    str(row["id"])
                    for row in inventory
                    if str(row["equip_slot"]).strip()
                    and str(row["id"])
                    not in {
                        str(slot["inventory_item_id"])
                        for slot in equipment
                        if slot["inventory_item_id"] is not None
                    }
                ],
                "equipment_slot_ids": [str(row["id"]) for row in equipment],
                "objective_ids": [str(row["id"]) for row in objectives],
                "loot_item_ids": [str(item["id"]) for item in available_loot],
                "location_ids": [],
                "campaign_clock_id": campaign_id,
            },
        }
        if preset_context is not None:
            context["preset_campaign"] = preset_context
        return context

    def resolve_player_action(
        self,
        action: str,
        provider: ActionOutcomeProvider,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> ActionResolutionResult:
        """Generate, validate, and atomically commit one non-combat turn."""

        normalized = " ".join(action.split())
        if not normalized:
            raise ActionValidationError("Enter an action before sending.")
        if len(normalized) > 2000:
            raise ActionValidationError("Actions are limited to 2,000 characters.")
        campaign_id = self.campaigns.active_campaign_id()
        if campaign_id:
            with self.database.connect() as connection:
                active_combat = connection.execute(
                    "SELECT 1 FROM combat_encounters "
                    "WHERE campaign_id = ? AND status = 'active'",
                    (campaign_id,),
                ).fetchone()
            if active_combat is not None:
                raise ActionValidationError(
                    "Combat is active. Use the Combat tab to choose and validate an action."
                )
        if self.action_requests_combat(normalized):
            raise ActionValidationError(
                "Start or continue combat from the Combat tab."
            )
        is_cancelled = cancelled or (lambda: False)
        if is_cancelled():
            raise ActionCancelledError("Action cancelled; no state was changed.")
        context = self.build_action_context()
        campaign_id = str(context["campaign"]["id"])  # type: ignore[index]
        before_checksum = self.reliability.checksum(campaign_id)
        outcome = provider.resolve_action(action=normalized, context=context)
        self._validate_action_outcome(outcome)
        if is_cancelled():
            raise ActionCancelledError("Action cancelled; no state was changed.")

        turn_id = f"turn-{uuid4().hex}"
        summaries: list[str] = []
        with self.database.transaction() as connection:
            active_row = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'active_campaign_id'"
            ).fetchone()
            active = None if active_row is None else str(active_row["value"])
            if active != campaign_id:
                raise ActionValidationError("The active campaign changed while resolving the action.")
            character = connection.execute(
                "SELECT id FROM characters WHERE campaign_id = ? AND is_player = 1",
                (campaign_id,),
            ).fetchone()
            if character is None:
                raise ActionValidationError("The active campaign has no player character.")
            character_id = str(character["id"])
            for change in outcome.state_changes:
                summaries.append(
                    self._apply_turn_change(
                        connection,
                        campaign_id,
                        character_id,
                        change,
                        player_action=normalized,
                    )
                )
            summaries.extend(
                progress_quests(
                    connection,
                    campaign_id,
                    "dialogue" if re.search(r"\b(speak|talk|ask|tell|greet)\b", normalized, re.I) else "custom_action",
                    detail=normalized,
                )
            )
            summaries.extend(check_deadlines(connection, campaign_id))
            if is_cancelled():
                raise ActionCancelledError("Action cancelled; no state was changed.")
            clock = connection.execute(
                "SELECT turn_number FROM campaign_clock WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            turn_number = int(clock["turn_number"]) + 1
            connection.execute(
                "UPDATE campaign_clock SET turn_number = ? WHERE campaign_id = ?",
                (turn_number, campaign_id),
            )
            location = connection.execute(
                "SELECT name FROM locations WHERE campaign_id = ? AND is_current = 1",
                (campaign_id,),
            ).fetchone()
            present_npc_ids = {
                str(row["id"])
                for row in connection.execute(
                    "SELECT npcs.id FROM npcs JOIN locations ON locations.id = npcs.location_id "
                    "WHERE npcs.campaign_id = ? AND locations.is_current = 1 AND npcs.available = 1",
                    (campaign_id,),
                )
            }
            # Model-proposed speakers are untrusted: keep only NPCs present here.
            response_segments = tuple(
                replace(
                    segment,
                    speaker_id=(
                        segment.speaker_id
                        if segment.kind == "spoken"
                        and isinstance(segment.speaker_id, str)
                        and segment.speaker_id in present_npc_ids
                        else None
                    ),
                )
                for segment in outcome.narrative_segments
            ) or (
                NarrativeSegment("narrative", outcome.narration.strip()),
            )
            serialized_segments = json.dumps(
                [asdict(segment) for segment in response_segments],
                ensure_ascii=False,
            )
            narrative_text = "\n\n".join(
                segment.text for segment in response_segments if segment.kind == "narrative"
            ) or outcome.narration
            dialogue_text = "\n\n".join(
                segment.text for segment in response_segments if segment.kind == "spoken"
            )
            paragraphs = tuple(
                paragraph.strip()
                for paragraph in narrative_text.split("\n\n")
                if paragraph.strip()
            ) or (outcome.narration.strip(),)
            connection.execute(
                """
                UPDATE narratives
                SET title = ?, paragraphs_json = ?, dialogue = ?,
                    prompt = 'What do you do next?', suggested_actions_json = ?,
                    player_action = ?, response_segments_json = ?
                WHERE campaign_id = ?
                """,
                (
                    "Current Scene" if location is None else str(location["name"]),
                    json.dumps(paragraphs),
                    dialogue_text,
                    json.dumps(outcome.suggested_actions),
                    normalized,
                    serialized_segments,
                    campaign_id,
                ),
            )
            serialized_changes = json.dumps(
                [asdict(change) for change in outcome.state_changes],
                ensure_ascii=False,
            )
            connection.execute(
                """
                INSERT INTO action_turns(
                    id, campaign_id, turn_number, player_action, narration,
                    state_changes_json, quest_notes_json, suggested_actions_json,
                    response_segments_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn_id,
                    campaign_id,
                    turn_number,
                    normalized,
                    outcome.narration,
                    serialized_changes,
                    json.dumps(outcome.quest_notes, ensure_ascii=False),
                    json.dumps(outcome.suggested_actions, ensure_ascii=False),
                    serialized_segments,
                ),
            )
            transcript_messages = [
                (
                    f"{turn_id}-message-0",
                    campaign_id,
                    turn_number,
                    0,
                    "player",
                    normalized,
                    None,
                )
            ]
            transcript_messages.extend(
                (
                    f"{turn_id}-message-{index}",
                    campaign_id,
                    turn_number,
                    index,
                    segment.kind,
                    segment.text,
                    segment.speaker_id,
                )
                for index, segment in enumerate(response_segments, start=1)
            )
            connection.executemany(
                "INSERT INTO narrative_messages("
                "id, campaign_id, turn_number, sequence, kind, text, speaker_npc_id"
                ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                transcript_messages,
            )
            claim_turn_notes(connection, campaign_id, turn_number)
            event_summary = " ".join(outcome.narration.split())[:500]
            self._record_turn_event(
                connection,
                campaign_id,
                player_action=normalized,
                summary=event_summary,
            )
            connection.execute(
                "UPDATE campaigns SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (campaign_id,),
            )
        result = ActionResolutionResult(
            turn_id=turn_id,
            narration=outcome.narration,
            state_summaries=tuple(summaries),
        )
        self.reliability.record_audit(
            campaign_id, "player_action", normalized,
            {"turn_id": turn_id, "state_changes": json.loads(serialized_changes)},
            before_checksum=before_checksum,
        )
        return result

    @staticmethod
    def action_requests_combat(action: str) -> bool:
        """Recognize explicit player combat intent before prose generation."""

        normalized = " ".join(action.casefold().split())
        if re.search(r"\b(?:avoid|prevent|stop|end|flee|escape)\s+(?:the\s+)?combat\b", normalized):
            return False
        return bool(re.search(
            r"\b(?:attack|fight|strike|stab|shoot|kill|engage)\b"
            r"|\bcharge\s+(?:at|toward|into)\b"
            r"|\bcast\s+(?:fireball|eldritch blast|magic missile)\b"
            r"|\bprepare\s+for\s+(?:battle|combat)\b"
            r"|\b(?:adopt|take)\s+(?:a\s+)?defensive stance\b"
            r"|\bready\s+(?:my|the|a)\s+(?:weapon|wand|blade|bow|spell)\b",
            normalized,
        ))

    @staticmethod
    def _validate_action_outcome(outcome: ActionOutcome) -> None:
        if not isinstance(outcome, ActionOutcome):
            raise ActionValidationError("The action provider returned an invalid outcome object.")
        if (
            not isinstance(outcome.narration, str)
            or not outcome.narration.strip()
            or len(outcome.narration) > 6000
        ):
            raise ActionValidationError("Turn narration was empty or oversized.")
        if len(outcome.state_changes) > 12 or any(
            not isinstance(change, ProposedStateChange)
            for change in outcome.state_changes
        ):
            raise ActionValidationError("Turn state changes exceeded the validated contract.")
        if outcome.narrative_segments:
            if len(outcome.narrative_segments) > 12 or any(
                not isinstance(segment, NarrativeSegment)
                or segment.kind not in {"narrative", "monologue", "spoken"}
                or not isinstance(segment.text, str)
                or not segment.text.strip()
                or len(segment.text) > 2000
                for segment in outcome.narrative_segments
            ):
                raise ActionValidationError(
                    "Turn narrative segments exceeded the validated contract."
                )
            if sum(len(segment.text) for segment in outcome.narrative_segments) > 6000:
                raise ActionValidationError(
                    "Turn narrative segments exceeded the validated contract."
                )
        for label, values, minimum, maximum in (
            ("quest notes", outcome.quest_notes, 0, 5),
            ("suggested actions", outcome.suggested_actions, 6, 6),
        ):
            if not minimum <= len(values) <= maximum or any(
                not isinstance(value, str) or not value.strip() or len(value) > 500
                for value in values
            ):
                raise ActionValidationError(f"Turn {label} exceeded the validated contract.")

    def _apply_turn_change(
        self,
        connection: sqlite3.Connection,
        campaign_id: str,
        character_id: str,
        change: ProposedStateChange,
        *,
        player_action: str,
    ) -> str:
        operation = change.operation
        if operation in {"spend_resource", "restore_resource"}:
            return self._apply_resource_change(
                connection,
                character_id,
                change,
                player_action=player_action,
            )
        if operation == "examine_item":
            self._require_change_shape(
                change,
                target_type="inventory_item",
                fields={None, ""},
            )
            if change.value is not None and change.value is not True:
                raise ActionValidationError("examine_item requires a null or true value.")
            item = connection.execute(
                "SELECT * FROM inventory_items WHERE id = ? AND character_id = ?",
                (change.target_id, character_id),
            ).fetchone()
            if item is None:
                raise ActionValidationError(
                    "The proposed inventory item is not owned by the player."
                )
            details = str(item["description"]).strip() or "No additional details are known."
            summary = f"Examined {item['name']}: {details}"
            updates = progress_quests(
                connection, campaign_id, "item_examine", str(item["name"]),
                detail=summary,
            )
            return " ".join((summary, *updates))
        if operation in {"use_item", "equip_item", "drop_item"}:
            self._require_change_shape(change, target_type="inventory_item", fields={None, ""})
            if change.value is not None and change.value is not True:
                raise ActionValidationError(f"{operation} requires a null or true value.")
            item = connection.execute(
                "SELECT * FROM inventory_items WHERE id = ? AND character_id = ?",
                (change.target_id, character_id),
            ).fetchone()
            if item is None:
                raise ActionValidationError("The proposed inventory item is not owned by the player.")
            try:
                if operation == "use_item":
                    summary = self._use_item(connection, character_id, item).summary
                elif operation == "equip_item":
                    summary = self._equip(connection, character_id, item).summary
                else:
                    summary = self._drop(connection, character_id, item).summary
                if operation != "equip_item":
                    verb = "used" if operation == "use_item" else "dropped"
                    record_turn_note(connection, campaign_id, "item", f"{item['name']} {verb}")
                updates = progress_quests(
                    connection,
                    campaign_id,
                    "item_use" if operation == "use_item" else "custom_action",
                    str(item["name"]),
                    detail=summary,
                )
                return " ".join((summary, *updates))
            except ItemActionError as exc:
                raise ActionValidationError(str(exc)) from exc
        if operation == "discover_item":
            self._require_change_shape(change, target_type="loot_item", fields={None, ""})
            if not re.search(
                r"\b(search|open|loot|investigate|explore)\b",
                player_action,
                flags=re.IGNORECASE,
            ):
                raise ActionValidationError(
                    "Finding loot requires an explicit search, open, or loot action."
                )
            return self._discover_catalog_item(
                connection, campaign_id, character_id, change.target_id
            )
        if operation == "acquire_item":
            self._require_change_shape(
                change, target_type="generated_item", fields={None, ""}
            )
            return self._acquire_generated_item(
                connection, campaign_id, character_id, change
            )
        if operation == "unequip_item":
            self._require_change_shape(change, target_type="equipment_slot", fields={None, ""})
            slot = connection.execute(
                "SELECT slot_index FROM equipment_slots WHERE id = ? AND character_id = ?",
                (change.target_id, character_id),
            ).fetchone()
            if slot is None:
                raise ActionValidationError("The proposed equipment slot is not owned by the player.")
            try:
                return self._unequip(connection, character_id, int(slot["slot_index"])).summary
            except ItemActionError as exc:
                raise ActionValidationError(str(exc)) from exc
        if operation == "complete_objective":
            return self._complete_objective(
                connection, campaign_id, change, evidence=player_action
            )
        if operation == "move_character":
            summary = self._move_character(connection, campaign_id, change)
            updates = progress_quests(
                connection, campaign_id, "travel", change.target_id, detail=summary
            )
            return " ".join((summary, *updates))
        if operation == "advance_time":
            summary = self._advance_time(connection, campaign_id, change)
            return " ".join((summary, *check_deadlines(connection, campaign_id)))
        raise ActionValidationError(f"Unsupported state operation: {operation}")

    @staticmethod
    def _discover_catalog_item(
        connection: sqlite3.Connection,
        campaign_id: str,
        character_id: str,
        catalog_id: str,
    ) -> str:
        clock = connection.execute(
            "SELECT turn_number FROM campaign_clock WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()
        location = connection.execute(
            "SELECT id FROM locations WHERE campaign_id = ? AND is_current = 1",
            (campaign_id,),
        ).fetchone()
        seed = (
            f"{campaign_id}:{0 if clock is None else int(clock['turn_number'])}:"
            f"{'' if location is None else location['id']}"
        )
        allowed = {str(item["id"]) for item in loot_shortlist(seed)}
        item = catalog_item(catalog_id)
        if item is None or catalog_id not in allowed:
            raise ActionValidationError("The proposed loot item is unavailable in this scene.")
        character = connection.execute(
            "SELECT inventory_capacity FROM characters WHERE id = ?", (character_id,)
        ).fetchone()
        occupied = {
            int(row[0])
            for row in connection.execute(
                "SELECT inventory_position FROM inventory_items WHERE character_id = ? "
                "AND inventory_position IS NOT NULL",
                (character_id,),
            )
        }
        position = next(
            (index for index in range(int(character["inventory_capacity"])) if index not in occupied),
            None,
        )
        if position is None:
            raise ActionValidationError("The inventory is full; the discovered item remains here.")
        definition = item_definition(item.name)
        item_id = f"item-{uuid4().hex}"
        slot_index = int(connection.execute(
            "SELECT COALESCE(MAX(slot_index), -1) + 1 FROM inventory_items WHERE character_id = ?",
            (character_id,),
        ).fetchone()[0])
        connection.execute(
            "INSERT INTO inventory_items("
            "id, character_id, slot_index, inventory_position, name, quantity, rarity, "
            "description, item_type, consumable, charges, maximum_charges, equip_slot, use_effect_json"
            ") VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item_id, character_id, slot_index, position, item.name, item.rarity,
                item.description, definition.item_type, int(definition.consumable),
                definition.charges, definition.maximum_charges, definition.equip_slot,
                definition.effect_json(),
            ),
        )
        difficulty = connection.execute(
            "SELECT difficulty FROM campaign_preferences WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        materialize_item_metadata(
            connection,
            item_id,
            difficulty="Adventurer" if difficulty is None else str(difficulty[0]),
        )
        recalculate_character_item_totals(connection, character_id)
        record_turn_note(connection, campaign_id, "item", f"{item.name} added")
        updates = progress_quests(
            connection, campaign_id, "item_collect", item.name, detail=item.description
        )
        return " ".join((f"Found {item.name}.", *updates))

    @classmethod
    def _acquire_generated_item(
        cls,
        connection: sqlite3.Connection,
        campaign_id: str,
        character_id: str,
        change: ProposedStateChange,
    ) -> str:
        name = " ".join(change.target_id.split())
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 '&().,\-]{0,99}", name):
            raise ActionValidationError("The acquired item name was invalid.")
        quantity = cls._integer_amount(change.value, "Item quantity")
        if not 1 <= quantity <= 99:
            raise ActionValidationError("Item quantity must be between 1 and 99.")
        catalog = catalog_item(name)
        rarity = "common" if catalog is None else catalog.rarity
        existing = connection.execute(
            "SELECT id, quantity FROM inventory_items WHERE character_id = ? "
            "AND inventory_position IS NOT NULL AND lower(name) = lower(?) "
            "AND lower(rarity) = lower(?) ORDER BY slot_index LIMIT 1",
            (character_id, name, rarity),
        ).fetchone()
        if existing is not None:
            connection.execute(
                "UPDATE inventory_items SET quantity = quantity + ? WHERE id = ?",
                (quantity, existing["id"]),
            )
        else:
            capacity = int(connection.execute(
                "SELECT inventory_capacity FROM characters WHERE id = ?",
                (character_id,),
            ).fetchone()[0])
            occupied = {
                int(row[0]) for row in connection.execute(
                    "SELECT inventory_position FROM inventory_items WHERE character_id = ? "
                    "AND inventory_position IS NOT NULL",
                    (character_id,),
                )
            }
            position = next((index for index in range(capacity) if index not in occupied), None)
            if position is None:
                raise ActionValidationError("The inventory is full; the item remains here.")
            definition = item_definition(name)
            item_id = f"item-{uuid4().hex}"
            slot_index = int(connection.execute(
                "SELECT COALESCE(MAX(slot_index), -1) + 1 FROM inventory_items "
                "WHERE character_id = ?", (character_id,),
            ).fetchone()[0])
            description = (
                catalog.description if catalog is not None else definition.description
            ) or f"A {name} acquired during the adventure."
            connection.execute(
                "INSERT INTO inventory_items("
                "id, character_id, slot_index, inventory_position, name, quantity, rarity, "
                "description, item_type, consumable, charges, maximum_charges, equip_slot, "
                "use_effect_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item_id, character_id, slot_index, position, name, quantity, rarity,
                    description, definition.item_type, int(definition.consumable),
                    definition.charges, definition.maximum_charges, definition.equip_slot,
                    definition.effect_json(),
                ),
            )
            difficulty = connection.execute(
                "SELECT difficulty FROM campaign_preferences WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            materialize_item_metadata(
                connection, item_id,
                difficulty="Adventurer" if difficulty is None else str(difficulty[0]),
            )
        recalculate_character_item_totals(connection, character_id)
        prefix = f"x{quantity} " if quantity > 1 else ""
        summary = f"Added {prefix}{name} to inventory."
        record_turn_note(connection, campaign_id, "item", f"{prefix}{name} added")
        cls._record_inventory_event(connection, campaign_id, summary)
        updates = progress_quests(
            connection, campaign_id, "item_collect", name, detail=summary
        )
        return " ".join((summary, *updates))

    @staticmethod
    def _require_change_shape(
        change: ProposedStateChange,
        *,
        target_type: str,
        fields: set[str | None],
    ) -> None:
        if change.target_type != target_type or change.field not in fields:
            raise ActionValidationError(
                f"{change.operation} used an invalid target type or field."
            )

    @classmethod
    def _apply_resource_change(
        cls,
        connection: sqlite3.Connection,
        character_id: str,
        change: ProposedStateChange,
        *,
        player_action: str,
    ) -> str:
        cls._require_change_shape(
            change,
            target_type="resource",
            fields={None, "", "current_value"},
        )
        amount = cls._integer_amount(change.value, "Resource changes")
        if not 1 <= amount <= 10:
            raise ActionValidationError("Non-combat resource changes must be between 1 and 10.")
        resource = connection.execute(
            "SELECT * FROM character_resources WHERE id = ? AND character_id = ?",
            (change.target_id, character_id),
        ).fetchone()
        if resource is None:
            raise ActionValidationError("The proposed resource is not owned by the player.")
        current = int(resource["current_value"])
        maximum = int(resource["maximum_value"])
        resource_type = str(resource["resource_type"])
        if resource_type in {"health", "experience"}:
            raise ActionValidationError(
                f"Direct {resource['name']} changes are outside non-combat action resolution."
            )
        if change.operation == "spend_resource":
            if current < amount:
                raise ActionValidationError(f"Not enough {resource['name']} for that action.")
            updated = current - amount
        else:
            if not re.search(
                r"\b(rest|breathe|breath|meditate|recover|pause)\b",
                player_action,
                flags=re.IGNORECASE,
            ):
                raise ActionValidationError(
                    "Resource restoration requires an explicit rest or recovery action."
                )
            updated = min(maximum, current + amount)
            if updated == current:
                raise ActionValidationError(f"{resource['name']} is already full.")
        connection.execute(
            "UPDATE character_resources SET current_value = ? WHERE id = ?",
            (updated, resource["id"]),
        )
        sign = "\u2212" if updated < current else "+"
        record_turn_note(
            connection,
            str(connection.execute(
                "SELECT campaign_id FROM characters WHERE id = ?", (character_id,)
            ).fetchone()[0]),
            "resource",
            f"{sign}{abs(updated - current)} {str(resource['name']).lower()}",
        )
        verb = "Spent" if change.operation == "spend_resource" else "Restored"
        return f"{verb} {amount} {resource['name']} ({current} to {updated})."

    @staticmethod
    def _integer_amount(value: object, label: str) -> int:
        if isinstance(value, bool):
            raise ActionValidationError(f"{label} require an integer amount.")
        try:
            number = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            raise ActionValidationError(f"{label} require an integer amount.") from None
        if not number.is_finite() or number != number.to_integral_value():
            raise ActionValidationError(f"{label} require an integer amount.")
        return int(number)

    @classmethod
    def _complete_objective(
        cls,
        connection: sqlite3.Connection,
        campaign_id: str,
        change: ProposedStateChange,
        *,
        evidence: str = "",
    ) -> str:
        cls._require_change_shape(
            change,
            target_type="quest_objective",
            fields={None, "", "completed"},
        )
        if change.value is not True:
            raise ActionValidationError("Objective completion requires a true value.")
        try:
            return complete_objective(
                connection, campaign_id, change.target_id, evidence=evidence
            )
        except GameStateError as exc:
            raise ActionValidationError(str(exc)) from exc

    @classmethod
    def _move_character(
        cls,
        connection: sqlite3.Connection,
        campaign_id: str,
        change: ProposedStateChange,
    ) -> str:
        raise ActionValidationError(
            "Destination travel must be confirmed through the Map so route, time, "
            "stamina, danger, and encounter rules can be applied together."
        )

    @classmethod
    def _advance_time(
        cls,
        connection: sqlite3.Connection,
        campaign_id: str,
        change: ProposedStateChange,
    ) -> str:
        cls._require_change_shape(
            change,
            target_type="campaign_clock",
            fields={None, "", "minute_of_day"},
        )
        if change.target_id != campaign_id:
            raise ActionValidationError("The proposed clock does not belong to the active campaign.")
        if isinstance(change.value, bool) or not isinstance(change.value, int):
            raise ActionValidationError("Time advancement requires an integer number of minutes.")
        minutes = change.value
        if not 1 <= minutes <= 480:
            raise ActionValidationError("A non-combat turn may advance time by 1 to 480 minutes.")
        clock = connection.execute(
            "SELECT day, minute_of_day FROM campaign_clock WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        total = int(clock["minute_of_day"]) + minutes
        day = int(clock["day"]) + total // 1440
        minute_of_day = total % 1440
        period = cls._period_for_minute(minute_of_day)
        time_label = f"{period}, Day {day}"
        connection.execute(
            "UPDATE campaign_clock SET day = ?, minute_of_day = ?, period = ?, time_label = ? "
            "WHERE campaign_id = ?",
            (day, minute_of_day, period, time_label, campaign_id),
        )
        return f"Advanced time by {minutes} minutes to {time_label}."

    @staticmethod
    def _period_for_minute(minute_of_day: int) -> str:
        hour = minute_of_day // 60
        if 5 <= hour < 12:
            return "Morning"
        if 12 <= hour < 17:
            return "Afternoon"
        if 17 <= hour < 21:
            return "Evening"
        return "Night"

    @staticmethod
    def _record_turn_event(
        connection: sqlite3.Connection,
        campaign_id: str,
        *,
        player_action: str,
        summary: str,
    ) -> None:
        sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence), -1) + 1 FROM events WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()[0]
        )
        clock = connection.execute(
            "SELECT time_label FROM campaign_clock WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        time_label = str(clock["time_label"]) if clock is not None else "Current time"
        connection.execute(
            "INSERT INTO events(id, campaign_id, time_label, category, summary, sequence, is_recent) "
            "VALUES (?, ?, ?, 'action', ?, ?, 1)",
            (
                f"event-{uuid4().hex}",
                campaign_id,
                time_label,
                f"{player_action}: {summary}"[:700],
                sequence,
            ),
        )
        connection.execute(
            "UPDATE events SET is_recent = 0 WHERE campaign_id = ? AND sequence <= ?",
            (campaign_id, sequence - 5),
        )

    @staticmethod
    def _use_item(
        connection: sqlite3.Connection,
        character_id: str,
        item: sqlite3.Row,
    ) -> ItemMutationResult:
        name = str(item["name"])
        effects = decode_effects(str(item["use_effect_json"]))
        resource_effects = effects.get("resources", {})
        remove_statuses = effects.get("remove_statuses", ())
        use_summary = str(effects.get("use_summary", "")).strip()
        if not isinstance(resource_effects, dict):
            resource_effects = {}
        if not isinstance(remove_statuses, (list, tuple)):
            remove_statuses = ()

        target_effect = bool(resource_effects or remove_statuses)
        applied: list[str] = []
        for resource_type, amount in resource_effects.items():
            if not isinstance(resource_type, str) or not isinstance(amount, int):
                continue
            resource = connection.execute(
                "SELECT id, name, current_value, maximum_value FROM character_resources "
                "WHERE character_id = ? AND resource_type = ?",
                (character_id, resource_type),
            ).fetchone()
            if resource is None:
                continue
            current = int(resource["current_value"])
            maximum = int(resource["maximum_value"])
            updated = max(0, min(maximum, current + amount))
            if updated == current:
                continue
            connection.execute(
                "UPDATE character_resources SET current_value = ? WHERE id = ?",
                (updated, resource["id"]),
            )
            applied.append(f"{resource['name']} {current} to {updated}")

        removed_statuses: list[str] = []
        for status in remove_statuses:
            if not isinstance(status, str) or not status.strip():
                continue
            rows = connection.execute(
                "SELECT id, name FROM status_effects WHERE character_id = ? "
                "AND lower(name) = lower(?)",
                (character_id, status.strip()),
            ).fetchall()
            for row in rows:
                connection.execute("DELETE FROM status_effects WHERE id = ?", (row["id"],))
                removed_statuses.append(str(row["name"]))

        durability = item["durability"]
        if durability is not None:
            durability = int(durability)
            if durability <= 0:
                raise ItemActionError(f"{name} is broken and cannot be used.")
            durability -= 1
            connection.execute(
                "UPDATE inventory_items SET durability = ? WHERE id = ?",
                (durability, item["id"]),
            )
            maximum_durability = int(item["maximum_durability"] or 1)
            condition = f"{round(durability * 100 / maximum_durability)}%"
            connection.execute(
                "UPDATE equipment_slots SET condition = ? WHERE character_id = ? "
                "AND inventory_item_id = ?",
                (condition, character_id, item["id"]),
            )
            applied.append(f"durability {durability}")

        charges = item["charges"]
        if charges is not None:
            charges = int(charges)
            if charges <= 0:
                raise ItemActionError(f"{name} has no charges remaining.")
            charges -= 1
            connection.execute(
                "UPDATE inventory_items SET charges = ? WHERE id = ?",
                (charges, item["id"]),
            )
            applied.append(f"{charges} charges remaining")

        if target_effect and not applied and not removed_statuses:
            raise ItemActionError(f"{name} would have no effect right now.")
        if not target_effect and durability is None and charges is None and not use_summary:
            raise ItemActionError(f"{name} cannot be used directly.")

        remaining: int | None = None
        if bool(item["consumable"]):
            quantity = int(item["quantity"])
            if quantity == 1:
                connection.execute("DELETE FROM inventory_items WHERE id = ?", (item["id"],))
                remaining = 0
            else:
                remaining = quantity - 1
                connection.execute(
                    "UPDATE inventory_items SET quantity = ? WHERE id = ?",
                    (remaining, item["id"]),
                )
            applied.append(f"{remaining} remaining")

        details = [*applied, *(f"removed {status}" for status in removed_statuses)]
        summary = use_summary or f"Used {name}."
        if details:
            summary = f"{summary} ({'; '.join(details)})"
        return ItemMutationResult(ItemAction.USE, name, summary)

    @staticmethod
    def _equip(
        connection: sqlite3.Connection,
        character_id: str,
        item: sqlite3.Row,
        destination_index: int | None = None,
    ) -> ItemMutationResult:
        name = str(item["name"])
        equip_slot = str(item["equip_slot"]).strip()
        if not equip_slot:
            raise ItemActionError(f"{name} is not equippable.")
        try:
            compatible = json.loads(str(item["compatible_slots_json"]))
        except json.JSONDecodeError:
            compatible = []
        if not isinstance(compatible, list):
            compatible = []
        if not compatible:
            compatible = list(item_definition(name).compatible_slots or (equip_slot,))
        if destination_index is None:
            target = connection.execute(
                "SELECT * FROM equipment_slots WHERE character_id = ? AND slot_name = ?",
                (character_id, equip_slot),
            ).fetchone()
        else:
            target = connection.execute(
                "SELECT * FROM equipment_slots WHERE character_id = ? AND slot_index = ?",
                (character_id, destination_index),
            ).fetchone()
            if target is None:
                raise ItemActionError("That equipment slot does not exist.")
            if str(target["slot_name"]) not in compatible:
                allowed = ", ".join(str(value) for value in compatible)
                raise ItemActionError(
                    f"{name} can only be equipped to: {allowed}."
                )
        if target is None:
            raise ItemActionError(f"No {equip_slot} equipment slot is configured.")
        if str(target["inventory_item_id"] or "") == str(item["id"]):
            raise ItemActionError(f"{name} is already equipped.")
        replaced = None if target["item_name"] is None else str(target["item_name"])
        source_position = item["inventory_position"]
        replaced_item_id = target["inventory_item_id"]
        connection.execute(
            "UPDATE equipment_slots SET item_name = NULL, condition = '', "
            "inventory_item_id = NULL WHERE character_id = ? AND inventory_item_id = ?",
            (character_id, item["id"]),
        )
        condition = ""
        if item["durability"] is not None and item["maximum_durability"] is not None:
            maximum = int(item["maximum_durability"])
            percent = round(int(item["durability"]) * 100 / maximum)
            condition = f"{percent}%"
        connection.execute(
            "UPDATE equipment_slots SET item_name = ?, condition = ?, inventory_item_id = ? "
            "WHERE id = ?",
            (name, condition, item["id"], target["id"]),
        )
        connection.execute(
            "UPDATE inventory_items SET inventory_position = NULL WHERE id = ?",
            (item["id"],),
        )
        if replaced_item_id is not None:
            connection.execute(
                "UPDATE inventory_items SET inventory_position = ? WHERE id = ?",
                (source_position, replaced_item_id),
            )
        summary = f"Equipped {name} to {equip_slot}."
        if replaced and replaced != name:
            summary = f"Equipped {name} to {equip_slot}, replacing {replaced}."
        return ItemMutationResult(ItemAction.EQUIP, name, summary)

    @staticmethod
    def _unequip(
        connection: sqlite3.Connection,
        character_id: str,
        slot_index: int,
        destination_index: int | None = None,
    ) -> ItemMutationResult:
        slot = connection.execute(
            "SELECT * FROM equipment_slots WHERE character_id = ? AND slot_index = ?",
            (character_id, slot_index),
        ).fetchone()
        if slot is None:
            raise ItemActionError("That equipment slot does not exist.")
        if slot["item_name"] is None:
            raise ItemActionError(f"{slot['slot_name']} is already empty.")
        name = str(slot["item_name"])
        capacity_row = connection.execute(
                "SELECT inventory_capacity FROM characters WHERE id = ?",
                (character_id,),
            ).fetchone()
        capacity = int(capacity_row["inventory_capacity"])
        occupied = {
            int(row[0])
            for row in connection.execute(
                "SELECT inventory_position FROM inventory_items WHERE character_id = ? "
                "AND inventory_position IS NOT NULL",
                (character_id,),
            )
        }
        if destination_index is not None:
            if not 0 <= destination_index < capacity:
                raise ItemActionError("That inventory destination is outside the bag.")
            if destination_index in occupied:
                raise ItemActionError("Unequip items into an empty inventory slot.")
            free_slot = destination_index
        else:
            free_slot = next((index for index in range(capacity) if index not in occupied), None)
        if free_slot is None:
            raise ItemActionError(f"Inventory is full; {name} cannot be unequipped.")
        if slot["inventory_item_id"] is None:
            definition = item_definition(name)
            condition = str(slot["condition"])
            durability = None
            maximum_durability = None
            if condition.endswith("%") and condition[:-1].isdigit():
                durability = int(condition[:-1])
                maximum_durability = 100
            item_id = f"item-{uuid4().hex}"
            legacy_slot = int(connection.execute(
                "SELECT COALESCE(MAX(slot_index), -1) + 1 FROM inventory_items WHERE character_id = ?",
                (character_id,),
            ).fetchone()[0])
            connection.execute(
                """
                INSERT INTO inventory_items(
                    id, character_id, slot_index, inventory_position, name, quantity, rarity, durability,
                    maximum_durability, description, item_type, consumable, charges,
                    maximum_charges, equip_slot, use_effect_json
                ) VALUES (?, ?, ?, ?, ?, 1, 'common', ?, ?, 'Unequipped equipment',
                          ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id, character_id, legacy_slot, free_slot, name, durability,
                    maximum_durability, definition.item_type,
                    int(definition.consumable), definition.charges,
                    definition.maximum_charges,
                    definition.equip_slot or str(slot["slot_name"]),
                    definition.effect_json(),
                ),
            )
            materialize_item_metadata(connection, item_id)
        else:
            connection.execute(
                "UPDATE inventory_items SET inventory_position = ? WHERE id = ?",
                (free_slot, slot["inventory_item_id"]),
            )
        connection.execute(
            "UPDATE equipment_slots SET item_name = NULL, condition = '', "
            "inventory_item_id = NULL WHERE id = ?",
            (slot["id"],),
        )
        return ItemMutationResult(
            ItemAction.UNEQUIP,
            name,
            f"Unequipped {name} from {slot['slot_name']}.",
        )

    @staticmethod
    def _drop(
        connection: sqlite3.Connection,
        character_id: str,
        item: sqlite3.Row,
    ) -> ItemMutationResult:
        name = str(item["name"])
        if bool(item["quest_item"]):
            raise ItemActionError(f"{name} is a quest item and cannot be dropped.")
        equipped = connection.execute(
            "SELECT 1 FROM equipment_slots WHERE character_id = ? AND "
            "(inventory_item_id = ? OR (inventory_item_id IS NULL AND item_name = ?)) LIMIT 1",
            (character_id, item["id"], name),
        ).fetchone()
        if equipped is not None:
            raise ItemActionError(f"Unequip {name} before dropping it.")
        quantity = int(item["quantity"])
        connection.execute("DELETE FROM inventory_items WHERE id = ?", (item["id"],))
        prefix = f"x{quantity} " if quantity > 1 else ""
        return ItemMutationResult(ItemAction.DROP, name, f"Dropped {prefix}{name}.")

    @staticmethod
    def _record_inventory_event(
        connection: sqlite3.Connection,
        campaign_id: str,
        summary: str,
    ) -> None:
        sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence), -1) + 1 FROM events WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()[0]
        )
        clock = connection.execute(
            "SELECT time_label FROM campaign_clock WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        time_label = str(clock["time_label"]) if clock is not None else "Current time"
        connection.execute(
            "INSERT INTO events(id, campaign_id, time_label, category, summary, sequence, is_recent) "
            "VALUES (?, ?, ?, 'inventory', ?, ?, 1)",
            (f"event-{uuid4().hex}", campaign_id, time_label, summary, sequence),
        )
        connection.execute(
            "UPDATE events SET is_recent = 0 WHERE campaign_id = ? AND sequence <= ?",
            (campaign_id, sequence - 5),
        )

    def select_campaign(self, campaign_id: str) -> None:
        campaign = self.campaigns.get(campaign_id)
        if campaign is None:
            raise KeyError(f"Unknown campaign: {campaign_id}")
        if not campaign.creation_complete:
            raise IncompleteGameStateError(
                f"Campaign creation is incomplete: {campaign.name}"
            )
        self.campaigns.select(campaign_id)

    def load_campaign(self, campaign_id: str) -> DashboardView:
        self._synchronize_current_location(campaign_id)
        return self.dashboard_projection.load(campaign_id)

    def older_messages(
        self, campaign_id: str, before_turn: int, limit: int = 40
    ) -> tuple[NarrativeMessageView, ...]:
        """Earlier transcript turns (with their notes) for scroll-back, oldest first."""

        return self.dashboard_projection.older_messages(campaign_id, before_turn, limit)

    def load_active_dashboard(self) -> DashboardView:
        campaign_id = self.ensure_demo_campaign()
        return self.load_campaign(campaign_id)

    def allocate_level_up_points(
        self, allocations: dict[str, int]
    ) -> DashboardView:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise GameStateError("No active campaign is available.")
        with self.database.transaction() as connection:
            character = connection.execute(
                "SELECT id FROM characters WHERE campaign_id = ? AND is_player = 1",
                (campaign_id,),
            ).fetchone()
            if character is None:
                raise GameStateError("The active campaign has no player character.")
            try:
                summaries = allocate_ability_points(
                    connection, str(character["id"]), allocations
                )
            except ValueError as exc:
                raise GameStateError(str(exc)) from exc
            self._record_inventory_event(
                connection, campaign_id, " ".join(summaries)
            )
        return self.load_campaign(campaign_id)

    def list_checkpoints(self) -> tuple[CampaignCheckpoint, ...]:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise GameStateError("No active campaign is available.")
        return self.reliability.list_checkpoints(campaign_id)

    def create_checkpoint(self, label: str) -> CampaignCheckpoint:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise GameStateError("No active campaign is available.")
        return self.reliability.create_checkpoint(campaign_id, label)

    def load_checkpoint(self, checkpoint_id: str) -> DashboardView:
        self.reliability.load_checkpoint(checkpoint_id)
        return self.load_active_dashboard()

    def inspect_campaign_repair(self) -> tuple[RepairIssue, ...]:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise GameStateError("No active campaign is available.")
        return self.reliability.inspect_repair(campaign_id)

    def repair_campaign(self) -> RepairResult:
        campaign_id = self.campaigns.active_campaign_id()
        if not campaign_id:
            raise GameStateError("No active campaign is available.")
        return self.reliability.apply_repair(campaign_id)

    def verify_checkpoint_replay(self, checkpoint_id: str) -> ReplayResult:
        return self.reliability.verify_replay(checkpoint_id)

    def _synchronize_current_location(self, campaign_id: str) -> None:
        """Keep story-selected locations visible on the deterministic map."""

        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE locations SET discovered = 1, visit_count = MAX(1, visit_count), "
                "first_discovered_at = COALESCE(first_discovered_at, CURRENT_TIMESTAMP), "
                "last_visited_at = COALESCE(last_visited_at, CURRENT_TIMESTAMP) "
                "WHERE campaign_id = ? AND is_current = 1", (campaign_id,),
            )


def _initials(name: str) -> str:
    parts = [part for part in name.strip().split() if part]
    return "".join(part[0].upper() for part in parts[:2]) or "?"
