"""Representative Phase 3 data, isolated from future production services."""

from dd_simulator.ui.models.presentation import (
    AttributeView,
    DashboardView,
    EquipmentSlotView,
    EventView,
    InventorySlotView,
    LocationSummaryView,
    MapLocationView,
    NarrativeMessageView,
    NarrativeSegmentView,
    NarrativeView,
    ObjectiveView,
    PlayerSummaryView,
    QuestView,
    QuestListItemView,
    ResourceView,
    SkillView,
    TravelRouteView,
    WorldMapView,
)


def build_phase_three_dashboard() -> DashboardView:
    """Return deterministic content for the data-driven Version 1 layout."""

    return DashboardView(
        player=PlayerSummaryView(
            name="Kaelen Stormborne",
            level=7,
            character_class="Warden",
            portrait_initials="KS",
            resources=(
                ResourceView("Health", 42, 42, "health", "Current and maximum health"),
                ResourceView("Stamina", 28, 28, "stamina", "Physical exertion resource"),
            ),
            experience=ResourceView(
                "Experience",
                2450,
                11000,
                "experience",
                "8550 experience needed for level 8",
            ),
            currency=1245,
            carry_weight=82,
            carry_capacity=120,
            attributes=(
                AttributeView("Strength", 16, 3),
                AttributeView("Dexterity", 14, 2),
                AttributeView("Constitution", 15, 2),
                AttributeView("Intelligence", 11, 0),
                AttributeView("Wisdom", 17, 3),
                AttributeView("Charisma", 10, 0),
            ),
            armor_class=15,
            initiative_modifier=2,
            movement_feet=15,
            proficiency_bonus=3,
        ),
        location=LocationSummaryView(
            name="Greystone Road",
            region="Silvermarch",
            time_label="Morning, Day 17",
            weather="Clear skies, 68 F",
            danger="Low danger",
            route_status="Road open toward Greystone Keep",
        ),
        narrative=NarrativeView(
            title="Greystone Road",
            paragraphs=(
                "The road winds through rolling green hills, with the distant "
                "walls of Greystone Keep visible on the horizon. A merchant's "
                "cart rests beneath a canvas awning beside the road.",
                "A weathered signpost points toward the keep and the shadowed "
                "trails of the Whispering Woods.",
            ),
            dialogue="The merchant looks up as you approach.",
            prompt="What would you like to do?",
            suggested_actions=(
                "Speak with the merchant",
                "Inspect the damaged cart",
                "Continue toward Greystone Keep",
                "Examine the weathered signpost",
                "Ask about the Whispering Woods",
                "Search the road for tracks",
            ),
            response_segments=(
                NarrativeSegmentView(
                    "narrative",
                    "The road winds through rolling green hills, with the distant "
                    "walls of Greystone Keep visible on the horizon. A merchant's "
                    "cart rests beneath a canvas awning beside the road.",
                ),
                NarrativeSegmentView(
                    "narrative",
                    "A weathered signpost points toward the keep and the shadowed "
                    "trails of the Whispering Woods.",
                ),
                NarrativeSegmentView(
                    "spoken",
                    "The merchant looks up as you approach.",
                ),
            ),
            messages=(
                NarrativeMessageView(
                    "narrative",
                    "The road winds through rolling green hills, with the distant "
                    "walls of Greystone Keep visible on the horizon. A merchant's "
                    "cart rests beneath a canvas awning beside the road.",
                ),
                NarrativeMessageView(
                    "narrative",
                    "A weathered signpost points toward the keep and the shadowed "
                    "trails of the Whispering Woods.",
                ),
                NarrativeMessageView(
                    "spoken",
                    "The merchant looks up as you approach.",
                ),
            ),
        ),
        quest=QuestView(
            title="The Lost Heirloom",
            status="Active quest",
            summary="Recover Lord Aric's heirloom from the Whispering Woods.",
            objectives=(
                ObjectiveView("Travel to the bandit camp"),
                ObjectiveView("Recover the heirloom"),
                ObjectiveView("Return to Lord Aric in Greystone Keep"),
                ObjectiveView("Help the roadside merchant", completed=True, optional=True),
            ),
        ),
        event_log=(
            EventView("Now", "experience", "You receive 50 experience."),
            EventView("Now", "loot", "You pick up an Iron Dagger."),
            EventView("Now", "system", "Iron Dagger added to inventory."),
            EventView("Now", "quest", "Quest updated: The Lost Heirloom."),
        ),
        recent_events=(
            EventView("Day 17, Morning", "travel", "Arrived at Greystone Road"),
            EventView("Day 17, Morning", "dialogue", "Spoke with a roadside merchant"),
            EventView("Day 16, Night", "rest", "Camped at Northern Ridge"),
            EventView("Day 16, Evening", "combat", "Defeated six goblins"),
        ),
        sidebar_resources=(
            ResourceView("Health", 42, 42, "health", "Current and maximum health"),
            ResourceView("Stamina", 28, 28, "stamina", "Used by physical abilities"),
            ResourceView("Focus", 61, 100, "focus", "Used by Warden techniques"),
            ResourceView("Resolve", 100, 100, "resolve", "Resistance to fear and coercion"),
        ),
        skills=(
            SkillView("Attack", 52, 380, 600, bonus=2),
            SkillView("Strength", 58, 510, 700, bonus=3),
            SkillView("Defense", 48, 120, 500),
            SkillView("Ranged", 45, 260, 480),
            SkillView("Survival", 43, 410, 460, bonus=4, recently_increased=True),
            SkillView("Magic", 50, 90, 550),
            SkillView("Herblore", 30, 180, 320),
            SkillView("Crafting", 33, 220, 350),
        ),
        inventory_preview=(
            InventorySlotView(
                "Iron Dagger",
                1,
                "uncommon",
                82,
                100,
                selected=True,
                description="A balanced dagger recovered on Greystone Road.",
                item_type="equipment",
                equip_slot="Main Hand",
                usable=True,
            ),
            InventorySlotView(
                "Oak Shield", 1, "common", 64, 100,
                item_type="equipment", equip_slot="Off Hand", usable=True,
            ),
            InventorySlotView(
                "Health Potion", 3, "common", description="Restores health.",
                item_type="consumable", consumable=True, usable=True,
            ),
            InventorySlotView("Map Fragment", 1, "rare", quest_item=True, item_type="quest"),
            InventorySlotView("Rope", 1, "common"),
            InventorySlotView("Gold", 1245, "currency", item_type="currency"),
            InventorySlotView("Lockpick", 5, "common"),
            InventorySlotView("Torch", 4, "common", item_type="consumable", consumable=True, usable=True),
            InventorySlotView("Travel Rations", 6, "common", item_type="consumable", consumable=True, usable=True),
            InventorySlotView("Antidote", 2, "uncommon", item_type="consumable", consumable=True, usable=True),
            InventorySlotView("Moonstone", 1, "epic"),
            InventorySlotView("Bandages", 3, "common", item_type="consumable", consumable=True, usable=True),
            InventorySlotView(
                "Flint & Steel", 1, "common", item_type="charged",
                charges=20, maximum_charges=20, usable=True,
            ),
            InventorySlotView(
                "Merchant Letter", 1, "rare", quest_item=True,
                description="A sealed letter bearing the roadside merchant's wax mark.",
                item_type="quest",
            ),
            InventorySlotView("Silver Ring", 1, "uncommon", item_type="equipment", equip_slot="Ring"),
            InventorySlotView("Water Flask", 2, "common", item_type="consumable", consumable=True, usable=True),
            InventorySlotView(
                "Arrows", 20, "common", description="A bundle of field arrows.",
                item_type="equipment", equip_slot="Ammunition",
            ),
            InventorySlotView(None),
            InventorySlotView(None),
            InventorySlotView(None),
        ),
        equipment=(
            EquipmentSlotView("Main Hand", "Iron Dagger", "82%"),
            EquipmentSlotView("Off Hand", "Oak Shield", "64%"),
            EquipmentSlotView("Head"),
            EquipmentSlotView("Body", "Warden Coat", "91%"),
            EquipmentSlotView("Hands", "Leather Gloves", "77%"),
            EquipmentSlotView("Feet", "Trail Boots", "70%"),
            EquipmentSlotView("Neck", "Greenstone Charm"),
            EquipmentSlotView("Ring", "Silver Ring"),
            EquipmentSlotView("Ammunition", "Arrows", "20"),
        ),
        quest_list=(
            QuestListItemView(
                "The Lost Heirloom", "active", 1, 3, selected=True,
                id="quest-heirloom",
                summary="Recover Lord Aric's heirloom from the Whispering Woods.",
                objectives=(
                    ObjectiveView("Travel to the bandit camp"),
                    ObjectiveView("Recover the heirloom"),
                    ObjectiveView("Return to Lord Aric in Greystone Keep"),
                    ObjectiveView("Help the roadside merchant", completed=True, optional=True),
                ),
                reward_summary="150 XP, 50 gold",
            ),
            QuestListItemView(
                "A Favor for the Merchant", "optional", 1, 2,
                id="quest-merchant", summary="Help the roadside merchant repair the damaged cart.",
                quest_type="optional", reward_summary="75 XP, 30 gold",
            ),
            QuestListItemView(
                "Whispers in the Woods", "rumored", 0, 1,
                deadline="Before dusk", id="quest-whispers",
                summary="Investigate the voices carried from the Whispering Woods.",
                reward_summary="125 XP, 40 gold",
            ),
        ),
        world_map=WorldMapView(
            current_location_id="location-greystone-road",
            locations=(
                MapLocationView("location-northern-ridge", "Northern Ridge", "Silvermarch", "A rocky ridge overlooking the northern valleys.", "mountain", "High danger", False, False, True, 2, 0),
                MapLocationView("location-whispering-woods", "Whispering Woods", "Silvermarch", "Ancient trees crowd a winding hunter's trail.", "forest", "Moderate danger", False, False, True, 0, 1),
                MapLocationView("location-greystone-keep", "Greystone Keep", "Silvermarch", "A fortified hill town built around an old stone keep.", "settlement", "Guarded", False, False, False, 4, 1),
                MapLocationView("location-greystone-road", "Greystone Road", "Silvermarch", "A broad trade road crossing the green hills of Silvermarch.", "road", "Low danger", True, True, True, 2, 2),
            ),
            routes=(
                TravelRouteView("route-road-keep", "location-greystone-road", "Greystone Road", "location-greystone-keep", "Greystone Keep", "location-greystone-keep", 8, 120, 2, 2, "open", "", "The maintained road climbs steadily toward the keep.", True),
                TravelRouteView("route-road-ridge", "location-greystone-road", "Greystone Road", "location-northern-ridge", "Northern Ridge", "location-northern-ridge", 11, 180, 3, 7, "open", "", "A steep northern path follows exposed stone and scrub.", True),
                TravelRouteView("route-road-woods", "location-greystone-road", "Greystone Road", "location-whispering-woods", "Whispering Woods", "location-whispering-woods", 5, 90, 2, 5, "open", "", "A narrow trail branches west beneath the old trees.", True),
                TravelRouteView("route-woods-ridge", "location-whispering-woods", "Whispering Woods", "location-northern-ridge", "Northern Ridge", "", 7, 150, 3, 6, "blocked", "A fallen bridge blocks the ravine crossing.", "The forest trail rises toward a broken ravine bridge.", False),
            ),
            can_camp=True,
        ),
    )
