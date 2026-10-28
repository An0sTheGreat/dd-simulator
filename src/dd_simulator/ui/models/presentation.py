"""Typed, read-only presentation models used by the desktop UI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VisualAssetView:
    id: str
    asset_kind: str
    path: str
    status: str
    version: int
    state_signature: str
    canonical: bool = False
    prompt_summary: str = ""


@dataclass(frozen=True, slots=True)
class ResourceView:
    name: str
    current: int
    maximum: int
    resource_type: str
    tooltip: str = ""


@dataclass(frozen=True, slots=True)
class AttributeView:
    name: str
    value: int
    modifier: int


@dataclass(frozen=True, slots=True)
class PlayerSummaryView:
    name: str
    level: int
    character_class: str
    portrait_initials: str
    resources: tuple[ResourceView, ...]
    experience: ResourceView
    currency: int
    carry_weight: int
    carry_capacity: int
    visual: VisualAssetView | None = None
    species: str = ""
    background: str = ""
    attributes: tuple[AttributeView, ...] = ()
    armor_class: int = 10
    initiative_modifier: int = 0
    movement_feet: int = 15
    age: int = 0
    gender_identity: str = ""
    pronouns: str = ""
    body_description: str = ""
    face_description: str = ""
    clothing_style: str = ""
    personalities: tuple[str, ...] = ()
    primary_strength: str = ""
    meaningful_flaw: str = ""
    motivation: str = ""
    biography: str = ""
    backstory: str = ""
    proficiency_bonus: int = 2
    pending_ability_points: int = 0


@dataclass(frozen=True, slots=True)
class LocationSummaryView:
    name: str
    region: str
    time_label: str
    weather: str
    danger: str
    route_status: str
    visual: VisualAssetView | None = None
    biome: str = "road"


@dataclass(frozen=True, slots=True)
class MapLocationView:
    id: str
    name: str
    region: str
    description: str
    biome: str
    danger: str
    current: bool
    visited: bool
    can_camp: bool
    map_x: int
    map_y: int


@dataclass(frozen=True, slots=True)
class TravelRouteView:
    id: str
    origin_id: str
    origin_name: str
    destination_id: str
    destination_name: str
    target_location_id: str
    distance_miles: int
    travel_minutes: int
    stamina_cost: int
    danger_rating: int
    status: str
    requirement: str
    description: str
    reachable: bool


@dataclass(frozen=True, slots=True)
class WorldMapView:
    current_location_id: str
    locations: tuple[MapLocationView, ...]
    routes: tuple[TravelRouteView, ...]
    can_camp: bool = False
    last_journey: str = ""


@dataclass(frozen=True, slots=True)
class NarrativeSegmentView:
    kind: str
    text: str


@dataclass(frozen=True, slots=True)
class TurnNoteView:
    kind: str  # xp, item, quest, relationship, travel, resource, other
    text: str


@dataclass(frozen=True, slots=True)
class NarrativeMessageView:
    kind: str
    text: str
    turn_number: int = 0
    speaker_id: str | None = None
    speaker_name: str = ""
    speaker_portrait: str = ""
    notes: tuple[TurnNoteView, ...] = ()


@dataclass(frozen=True, slots=True)
class NarrativeView:
    title: str
    paragraphs: tuple[str, ...]
    dialogue: str
    prompt: str
    suggested_actions: tuple[str, ...]
    player_action: str = ""
    response_segments: tuple[NarrativeSegmentView, ...] = ()
    messages: tuple[NarrativeMessageView, ...] = ()
    has_older_messages: bool = False


@dataclass(frozen=True, slots=True)
class ObjectiveView:
    text: str
    completed: bool = False
    optional: bool = False


@dataclass(frozen=True, slots=True)
class QuestView:
    title: str
    status: str
    summary: str
    objectives: tuple[ObjectiveView, ...]


@dataclass(frozen=True, slots=True)
class EventView:
    time_label: str
    category: str
    summary: str


@dataclass(frozen=True, slots=True)
class SkillView:
    name: str
    level: int
    current_xp: int = 0
    next_level_xp: int = 0
    bonus: int = 0
    locked: bool = False
    recently_increased: bool = False


@dataclass(frozen=True, slots=True)
class InventorySlotView:
    name: str | None
    quantity: int = 0
    rarity: str = "common"
    durability: int | None = None
    maximum_durability: int | None = None
    quest_item: bool = False
    selected: bool = False
    description: str = ""
    item_type: str = "misc"
    consumable: bool = False
    charges: int | None = None
    maximum_charges: int | None = None
    equip_slot: str = ""
    usable: bool = False
    id: str | None = None
    damage: str = ""
    armor: str = ""
    effects: str = ""
    status: str = ""
    category: str = "misc"
    weight: float = 0.0
    value_gp: int = 0
    identified: bool = True
    healing: int = 0
    compatible_slots: tuple[str, ...] = ()
    requirements: str = ""
    bonuses: str = ""
    penalties: str = ""
    generated_difficulty: str = "Adventurer"

    @property
    def is_empty(self) -> bool:
        return self.name is None

    @property
    def can_equip(self) -> bool:
        return not self.is_empty and bool(self.equip_slot)

    @property
    def can_drop(self) -> bool:
        return not self.is_empty and not self.quest_item


@dataclass(frozen=True, slots=True)
class EquipmentSlotView:
    slot_name: str
    item_name: str | None = None
    condition: str = ""
    selected: bool = False
    item: InventorySlotView | None = None


@dataclass(frozen=True, slots=True)
class CombatantView:
    id: str
    name: str
    side: str
    status: str
    current_health: int
    maximum_health: int
    armor_class: int
    initiative: int
    distance_feet: int
    weapon_name: str
    morale: int
    conditions: tuple[str, ...] = ()
    declared_intent: str = ""
    active_turn: bool = False
    archetype_key: str = ""
    abilities: tuple[str, ...] = ()
    resistances: tuple[str, ...] = ()
    vulnerabilities: tuple[str, ...] = ()
    behavior_profile: str = ""


@dataclass(frozen=True, slots=True)
class CombatLogEntryView:
    round_number: int
    actor_name: str
    action_type: str
    summary: str


@dataclass(frozen=True, slots=True)
class CombatActionOptionView:
    key: str
    name: str
    kind: str
    description: str
    resource_label: str
    available: bool
    unavailable_reason: str = ""
    stats: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class NpcView:
    id: str
    name: str
    title: str
    portrait_initials: str
    status: str
    disposition: str
    relationship_score: int
    available: bool
    personality: str = ""


@dataclass(frozen=True, slots=True)
class DialogueMessageView:
    kind: str
    text: str


@dataclass(frozen=True, slots=True)
class CommerceItemView:
    id: str
    name: str
    quantity: int
    rarity: str
    description: str
    durability: int | None = None
    maximum_durability: int | None = None
    damage: str = ""
    healing: int = 0
    category: str = "misc"
    item_type: str = "misc"
    equip_slot: str = ""
    compatible_slots: tuple[str, ...] = ()
    weight: float = 0.0
    value_gp: int = 0
    identified: bool = True
    buy_price: int = 0
    barter_price: int = 0
    sell_price: int = 0


@dataclass(frozen=True, slots=True)
class MerchantView:
    npc_id: str
    player_currency: int
    stock: tuple[CommerceItemView, ...]
    sellable_items: tuple[CommerceItemView, ...]
    equipment: tuple[EquipmentSlotView, ...] = ()


@dataclass(frozen=True, slots=True)
class CraftingIngredientView:
    name: str
    required: int
    owned: int


@dataclass(frozen=True, slots=True)
class CraftingRecipeView:
    id: str
    name: str
    description: str
    skill_name: str
    skill_level: int
    difficulty: int
    output_name: str
    output_quantity: int
    output_rarity: str
    crafting_xp: int
    ingredients: tuple[CraftingIngredientView, ...]
    required_tool: str = ""
    tool_use_cost: int = 0
    tool_available: bool = True
    available: bool = True
    unavailable_reason: str = ""


@dataclass(frozen=True, slots=True)
class CraftingResultView:
    id: str
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
    acknowledged: bool = False


@dataclass(frozen=True, slots=True)
class ConversationView:
    npc: NpcView
    messages: tuple[DialogueMessageView, ...]
    suggested_responses: tuple[str, ...]
    last_check: str = ""
    merchant: MerchantView | None = None


@dataclass(frozen=True, slots=True)
class CombatRewardItemView:
    id: str
    name: str
    quantity: int
    rarity: str
    description: str
    claimed: bool = False


@dataclass(frozen=True, slots=True)
class CombatRewardView:
    id: str
    outcome: str
    experience: int
    skill_experience: int
    currency: int
    items: tuple[CombatRewardItemView, ...]
    acknowledged: bool = False


@dataclass(frozen=True, slots=True)
class CombatEncounterView:
    id: str
    status: str
    round_number: int
    environment: str
    hazard: str
    starting_distance: int
    end_reason: str
    combatants: tuple[CombatantView, ...]
    recent_turns: tuple[CombatLogEntryView, ...]
    action_options: tuple[CombatActionOptionView, ...] = ()
    generated: bool = False
    intro_complete: bool = True
    introduction: str = ""
    terrain: str = ""
    awareness_state: str = "aware"
    difficulty_rating: int = 1
    preparation_choice: str = ""
    reward: CombatRewardView | None = None


@dataclass(frozen=True, slots=True)
class QuestListItemView:
    title: str
    status: str
    progress_current: int
    progress_maximum: int
    selected: bool = False
    deadline: str = ""
    id: str = ""
    summary: str = ""
    quest_type: str = "main"
    objectives: tuple[ObjectiveView, ...] = ()
    reward_summary: str = ""


@dataclass(frozen=True, slots=True)
class QuestRewardItemView:
    id: str
    name: str
    quantity: int
    rarity: str
    description: str
    claimed: bool = False


@dataclass(frozen=True, slots=True)
class QuestRewardView:
    id: str
    quest_id: str
    quest_title: str
    experience: int
    currency: int
    reputation: int
    faction: str
    items: tuple[QuestRewardItemView, ...]
    acknowledged: bool = False


@dataclass(frozen=True, slots=True)
class DashboardView:
    player: PlayerSummaryView
    location: LocationSummaryView
    narrative: NarrativeView
    quest: QuestView
    event_log: tuple[EventView, ...]
    recent_events: tuple[EventView, ...]
    sidebar_resources: tuple[ResourceView, ...]
    skills: tuple[SkillView, ...]
    inventory_preview: tuple[InventorySlotView, ...]
    equipment: tuple[EquipmentSlotView, ...]
    quest_list: tuple[QuestListItemView, ...]
    combat: CombatEncounterView | None = None
    pending_quest_reward: QuestRewardView | None = None
    world_map: WorldMapView | None = None
    combat_skills: tuple[CombatActionOptionView, ...] = ()
    present_npcs: tuple[NpcView, ...] = ()
    npc_conversations: tuple[ConversationView, ...] = ()
    crafting_recipes: tuple[CraftingRecipeView, ...] = ()
    pending_crafting_result: CraftingResultView | None = None
    campaign_name: str = "D&D SIMULATOR"
    is_preset_campaign: bool = False
