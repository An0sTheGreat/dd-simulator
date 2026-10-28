"""Idempotent deterministic seed for the initial local campaign."""

from __future__ import annotations

import json

from dd_simulator.state.database import GameStateDatabase
from dd_simulator.state.item_actions import (
    backfill_item_metadata,
    item_definition,
    materialize_item_metadata,
    recalculate_character_item_totals,
)
from dd_simulator.state.crafting import seed_crafting_recipes


DEMO_CAMPAIGN_ID = "demo-greystone"
DEMO_CHARACTER_ID = "demo-kaelen"


def seed_demo_campaign(database: GameStateDatabase) -> str:
    with database.transaction() as connection:
        exists = connection.execute(
            "SELECT 1 FROM campaigns WHERE id = ?",
            (DEMO_CAMPAIGN_ID,),
        ).fetchone()
        if exists is not None:
            return DEMO_CAMPAIGN_ID

        connection.execute(
            "INSERT INTO campaigns(id, name) VALUES (?, ?)",
            (DEMO_CAMPAIGN_ID, "Greystone Beginnings"),
        )
        connection.execute(
            "INSERT INTO campaign_clock(campaign_id, day, period, time_label) "
            "VALUES (?, 17, 'Morning', 'Morning, Day 17')",
            (DEMO_CAMPAIGN_ID,),
        )
        connection.execute(
            """
            INSERT INTO locations(
                id, campaign_id, name, region, weather, danger, route_status, is_current,
                description, biome, discovered, visit_count, first_discovered_at,
                last_visited_at, can_camp, map_x, map_y
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 1, 1, CURRENT_TIMESTAMP,
                      CURRENT_TIMESTAMP, 1, 2, 2)
            """,
            (
                "location-greystone-road",
                DEMO_CAMPAIGN_ID,
                "Greystone Road",
                "Silvermarch",
                "Clear skies, 68 F",
                "Low danger",
                "Road open toward Greystone Keep",
                "A broad trade road crossing the green hills of Silvermarch.",
                "road",
            ),
        )
        connection.executemany(
            """
            INSERT INTO locations(
                id, campaign_id, name, region, weather, danger, route_status,
                description, biome, discovered, can_camp, map_x, map_y
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ("location-greystone-keep", DEMO_CAMPAIGN_ID, "Greystone Keep", "Silvermarch", "Clear skies", "Guarded", "Southern gate open", "A fortified hill town built around an old stone keep.", "settlement", 1, 0, 4, 1),
                ("location-whispering-woods", DEMO_CAMPAIGN_ID, "Whispering Woods", "Silvermarch", "Cool beneath the canopy", "Moderate danger", "Forest trail open", "Ancient trees crowd a winding hunter's trail.", "forest", 1, 1, 0, 1),
                ("location-northern-ridge", DEMO_CAMPAIGN_ID, "Northern Ridge", "Silvermarch", "Strong western wind", "High danger", "Mountain path open", "A rocky ridge overlooking the northern valleys.", "mountain", 1, 1, 2, 0),
                ("location-ancient-ruins", DEMO_CAMPAIGN_ID, "Ancient Ruins", "Silvermarch", "Unknown", "Unknown", "Route hidden", "Unmapped ruins beyond the eastern hills.", "ruins", 0, 1, 5, 3),
            ),
        )
        connection.executemany(
            """
            INSERT INTO travel_routes(
                id, campaign_id, origin_location_id, destination_location_id,
                distance_miles, travel_minutes, stamina_cost, danger_rating,
                status, requirement, description, bidirectional, discovered
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                ("route-road-keep", DEMO_CAMPAIGN_ID, "location-greystone-road", "location-greystone-keep", 8, 120, 2, 2, "open", "", "The maintained road climbs steadily toward the keep.", 1),
                ("route-road-woods", DEMO_CAMPAIGN_ID, "location-greystone-road", "location-whispering-woods", 5, 90, 2, 5, "open", "", "A narrow trail branches west beneath the old trees.", 1),
                ("route-road-ridge", DEMO_CAMPAIGN_ID, "location-greystone-road", "location-northern-ridge", 11, 180, 3, 7, "open", "", "A steep northern path follows exposed stone and scrub.", 1),
                ("route-woods-ridge", DEMO_CAMPAIGN_ID, "location-whispering-woods", "location-northern-ridge", 7, 150, 3, 6, "blocked", "A fallen bridge blocks the ravine crossing.", "The forest trail rises toward a broken ravine bridge.", 1),
                ("route-keep-ruins", DEMO_CAMPAIGN_ID, "location-greystone-keep", "location-ancient-ruins", 9, 160, 3, 8, "hidden", "Discover the eastern ruin trail.", "A forgotten track leads beyond the eastern hills.", 0),
            ),
        )
        connection.execute(
            """
            INSERT INTO characters(
                id, campaign_id, name, level, character_class, portrait_initials,
                currency, carry_weight, carry_capacity, inventory_capacity, is_player
            ) VALUES (?, ?, ?, 7, 'Warden', 'KS', 1245, 76, 120, 320, 1)
            """,
            (DEMO_CHARACTER_ID, DEMO_CAMPAIGN_ID, "Kaelen Stormborne"),
        )
        connection.executemany(
            """
            INSERT INTO character_attributes(
                id, character_id, name, value, modifier, display_order
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (f"attribute-{index}", DEMO_CHARACTER_ID, name, value, modifier, index)
                for index, (name, value, modifier) in enumerate(
                    (
                        ("Strength", 16, 3),
                        ("Dexterity", 14, 2),
                        ("Constitution", 15, 2),
                        ("Intelligence", 11, 0),
                        ("Wisdom", 17, 3),
                        ("Charisma", 10, 0),
                    )
                )
            ),
        )

        resources = (
            ("health", "Health", 42, 42, "health", "Current and maximum health", "Current and maximum health", 0, 1, 1),
            ("stamina", "Stamina", 28, 28, "stamina", "Physical exertion resource", "Used by physical abilities", 1, 1, 1),
            ("focus", "Focus", 61, 100, "focus", "Used by Warden techniques", "Used by Warden techniques", 2, 0, 1),
            ("resolve", "Resolve", 100, 100, "resolve", "Resistance to fear and coercion", "Resistance to fear and coercion", 3, 0, 1),
            ("experience", "Experience", 2450, 11000, "experience", "8550 experience needed for level 8", "", 4, 0, 0),
        )
        connection.executemany(
            """
            INSERT INTO character_resources(
                id, character_id, name, current_value, maximum_value, resource_type,
                tooltip, sidebar_tooltip, display_order, show_in_summary, show_in_sidebar
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (f"resource-{key}", DEMO_CHARACTER_ID, name, current, maximum, kind,
                 tooltip, sidebar_tooltip, order, summary, sidebar)
                for key, name, current, maximum, kind, tooltip, sidebar_tooltip,
                order, summary, sidebar
                in resources
            ),
        )

        skills = (
            ("Attack", 52, 380, 600, 2, 0, 0),
            ("Strength", 58, 510, 700, 3, 0, 0),
            ("Defense", 48, 120, 500, 0, 0, 0),
            ("Ranged", 45, 260, 480, 0, 0, 0),
            ("Survival", 43, 410, 460, 4, 0, 1),
            ("Magic", 50, 90, 550, 0, 0, 0),
            ("Herblore", 30, 180, 320, 0, 0, 0),
            ("Crafting", 33, 220, 350, 0, 0, 0),
        )
        connection.executemany(
            """
            INSERT INTO skills(
                id, character_id, name, level, current_xp, next_level_xp,
                bonus, locked, recently_increased, display_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (f"skill-{index}", DEMO_CHARACTER_ID, *skill, index)
                for index, skill in enumerate(skills)
            ),
        )

        inventory = (
            ("Iron Dagger", 1, "uncommon", 82, 100, 0, 1, "A balanced dagger recovered on Greystone Road."),
            ("Oak Shield", 1, "common", 64, 100, 0, 0, ""),
            ("Health Potion", 3, "common", None, None, 0, 0, "Restores health."),
            ("Map Fragment", 1, "rare", None, None, 1, 0, ""),
            ("Rope", 1, "common", None, None, 0, 0, ""),
            ("Gold", 1245, "currency", None, None, 0, 0, ""),
            ("Lockpick", 5, "common", None, None, 0, 0, ""),
            ("Torch", 4, "common", None, None, 0, 0, ""),
            ("Travel Rations", 6, "common", None, None, 0, 0, ""),
            ("Antidote", 2, "uncommon", None, None, 0, 0, ""),
            ("Moonstone", 1, "epic", None, None, 0, 0, ""),
            ("Bandages", 3, "common", None, None, 0, 0, ""),
            ("Flint & Steel", 1, "common", None, None, 0, 0, ""),
            (
                "Merchant Letter", 1, "rare", None, None, 1, 0,
                "A sealed letter bearing the roadside merchant's wax mark.",
            ),
            ("Silver Ring", 1, "uncommon", None, None, 0, 0, ""),
            ("Water Flask", 2, "common", None, None, 0, 0, ""),
            ("Arrows", 20, "common", None, None, 0, 0, "A bundle of field arrows."),
            ("Cloth", 4, "common", None, None, 0, 0, "Clean cloth suitable for crafting."),
            ("Herbs", 4, "common", None, None, 0, 0, "Medicinal herbs gathered for crafting."),
            ("Iron Scraps", 4, "common", None, None, 0, 0, "Small iron pieces ready to be reshaped."),
            ("Healer's Kit", 1, "common", None, None, 0, 0, "A compact kit for medicines and wounds."),
        )
        inventory_records = []
        for index, item in enumerate(inventory):
            definition = item_definition(item[0])
            inventory_records.append(
                (
                    f"item-{index}", DEMO_CHARACTER_ID, index, index, *item,
                    definition.item_type, int(definition.consumable),
                    definition.charges, definition.maximum_charges,
                    definition.equip_slot, definition.effect_json(),
                )
            )
        connection.executemany(
            """
            INSERT INTO inventory_items(
                id, character_id, slot_index, inventory_position, name, quantity, rarity, durability,
                maximum_durability, quest_item, selected, description, item_type,
                consumable, charges, maximum_charges, equip_slot, use_effect_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            inventory_records,
        )
        for item_id, *_rest in inventory_records:
            materialize_item_metadata(connection, item_id, difficulty="Adventurer")

        equipment = (
            ("Main Hand", "Iron Dagger", "82%", "item-0"),
            ("Off Hand", "Oak Shield", "64%", "item-1"),
            ("Head", None, "", None),
            ("Body", "Warden Coat", "91%", None),
            ("Hands", "Leather Gloves", "77%", None),
            ("Feet", "Trail Boots", "70%", None),
            ("Neck", "Greenstone Charm", "", None),
            ("Ring", "Silver Ring", "", "item-14"),
            ("Ammunition", "Arrows", "20", "item-16"),
        )
        connection.executemany(
            """
            INSERT INTO equipment_slots(
                id, character_id, slot_index, slot_name, item_name, condition,
                inventory_item_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (f"equipment-{index}", DEMO_CHARACTER_ID, index, *slot)
                for index, slot in enumerate(equipment)
            ),
        )
        connection.execute(
            "UPDATE inventory_items SET inventory_position = NULL WHERE id IN "
            "(SELECT inventory_item_id FROM equipment_slots WHERE character_id = ? "
            "AND inventory_item_id IS NOT NULL)",
            (DEMO_CHARACTER_ID,),
        )
        recalculate_character_item_totals(connection, DEMO_CHARACTER_ID)
        visible = connection.execute(
            "SELECT id FROM inventory_items WHERE character_id = ? "
            "AND inventory_position IS NOT NULL ORDER BY slot_index",
            (DEMO_CHARACTER_ID,),
        ).fetchall()
        connection.execute(
            "UPDATE inventory_items SET inventory_position = NULL WHERE character_id = ?",
            (DEMO_CHARACTER_ID,),
        )
        for position, row in enumerate(visible):
            connection.execute(
                "UPDATE inventory_items SET inventory_position = ? WHERE id = ?",
                (position, row["id"]),
            )
        backfill_item_metadata(connection)
        recalculate_character_item_totals(connection, DEMO_CHARACTER_ID)

        quests = (
            ("quest-heirloom", "The Lost Heirloom", "active", "main", "Recover Lord Aric's heirloom from the Whispering Woods.", 1, 3, 1, "", 150, 50, '[{"name":"Moonstone","quantity":1}]'),
            ("quest-merchant", "A Favor for the Merchant", "active", "optional", "Help the roadside merchant repair the damaged cart.", 1, 2, 0, "", 75, 30, '[]'),
            ("quest-whispers", "Whispers in the Woods", "rumored", "main", "Investigate the voices carried from the Whispering Woods.", 0, 1, 0, "Before dusk", 125, 40, '[]'),
        )
        connection.executemany(
            """
            INSERT INTO quests(
                id, campaign_id, title, status, summary, progress_current,
                progress_maximum, selected, deadline, display_order, quest_type,
                reward_experience, reward_currency, reward_items_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    quest[0], DEMO_CAMPAIGN_ID, quest[1], quest[2], quest[4],
                    quest[5], quest[6], quest[7], quest[8], index, quest[3],
                    quest[9], quest[10], quest[11],
                )
                for index, quest in enumerate(quests)
            ),
        )
        objectives = (
            ("Travel to the bandit camp", 0, 0, "travel", "bandit camp"),
            ("Recover the heirloom", 0, 0, "item_collect", "heirloom"),
            ("Return to Lord Aric in Greystone Keep", 0, 0, "travel", "Greystone Keep"),
            ("Help the roadside merchant", 1, 1, "dialogue", "merchant"),
        )
        connection.executemany(
            """
            INSERT INTO quest_objectives(
                id, quest_id, text, completed, optional, display_order
                , trigger_type, trigger_target, current_count, required_count
            ) VALUES (?, 'quest-heirloom', ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                (f"objective-{index}", objective[0], objective[1], objective[2],
                 index, objective[3], objective[4], int(objective[1]))
                for index, objective in enumerate(objectives)
            ),
        )

        paragraphs = (
            "The road winds through rolling green hills, with the distant walls of Greystone Keep visible on the horizon. A merchant's cart rests beneath a canvas awning beside the road.",
            "A weathered signpost points toward the keep and the shadowed trails of the Whispering Woods.",
        )
        suggestions = (
            "Speak with the merchant",
            "Inspect the damaged cart",
            "Continue toward Greystone Keep",
            "Examine the weathered signpost",
            "Ask about the Whispering Woods",
            "Search the road for tracks",
        )
        connection.execute(
            """
            INSERT INTO narratives(
                campaign_id, title, paragraphs_json, dialogue, prompt,
                suggested_actions_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                DEMO_CAMPAIGN_ID,
                "Greystone Road",
                json.dumps(paragraphs),
                "The merchant looks up as you approach.",
                "What would you like to do?",
                json.dumps(suggestions),
            ),
        )
        connection.executemany(
            "INSERT INTO narrative_messages("
            "id, campaign_id, turn_number, sequence, kind, text"
            ") VALUES (?, ?, 0, ?, ?, ?)",
            (
                (
                    "demo-message-0",
                    DEMO_CAMPAIGN_ID,
                    0,
                    "narrative",
                    paragraphs[0],
                ),
                (
                    "demo-message-1",
                    DEMO_CAMPAIGN_ID,
                    1,
                    "narrative",
                    paragraphs[1],
                ),
                (
                    "demo-message-2",
                    DEMO_CAMPAIGN_ID,
                    2,
                    "spoken",
                    "The merchant looks up as you approach.",
                ),
            ),
        )

        events = (
            ("Now", "experience", "You receive 50 experience.", 0, 0),
            ("Now", "loot", "You pick up an Iron Dagger.", 1, 0),
            ("Now", "system", "Iron Dagger added to inventory.", 2, 0),
            ("Now", "quest", "Quest updated: The Lost Heirloom.", 3, 0),
            ("Day 17, Morning", "travel", "Arrived at Greystone Road", 4, 1),
            ("Day 17, Morning", "dialogue", "Spoke with a roadside merchant", 5, 1),
            ("Day 16, Night", "rest", "Camped at Northern Ridge", 6, 1),
            ("Day 16, Evening", "combat", "Defeated six goblins", 7, 1),
        )
        connection.executemany(
            """
            INSERT INTO events(
                id, campaign_id, time_label, category, summary, sequence, is_recent
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (f"event-{sequence}", DEMO_CAMPAIGN_ID, time_label, category,
                 summary, sequence, recent)
                for time_label, category, summary, sequence, recent in events
            ),
        )
        connection.executemany(
            """
            INSERT INTO npcs(
                id, campaign_id, name, location_id, disposition, notes, status,
                title, portrait_initials, personality, voice_style, biography,
                faction, offers_quest_id, reveals_location_id, reveals_route_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    "npc-roadside-merchant", DEMO_CAMPAIGN_ID, "Roadside Merchant",
                    "location-greystone-road", "friendly", "Cart requires repair.",
                    "friendly", "Traveling Merchant", "RM",
                    "Practical, grateful, and alert to road gossip.",
                    "Warm, direct speech colored by a trader's caution.",
                    "A traveling merchant whose cart was damaged on Greystone Road.",
                    "Greystone Traders", "quest-merchant", "location-whispering-woods", None,
                ),
                (
                    "npc-lord-aric", DEMO_CAMPAIGN_ID, "Lord Aric",
                    "location-greystone-keep", "neutral", "Seeks the lost family heirloom.",
                    "neutral", "Warden of Greystone Keep", "LA",
                    "Measured, duty-bound, and slow to trust.",
                    "Formal, restrained speech with the weight of command.",
                    "The hereditary warden responsible for Greystone Keep and its people.",
                    "Greystone Keep", "quest-heirloom", None, "route-keep-ruins",
                ),
            ),
        )
        connection.executemany(
            "INSERT INTO relationships(id, campaign_id, source_entity_id, target_entity_id, "
            "relationship_type, score, notes) VALUES (?, ?, ?, ?, 'personal', ?, 'Player relationship')",
            (
                ("relationship-player-merchant", DEMO_CAMPAIGN_ID, DEMO_CHARACTER_ID, "npc-roadside-merchant", 20),
                ("relationship-player-aric", DEMO_CAMPAIGN_ID, DEMO_CHARACTER_ID, "npc-lord-aric", 0),
            ),
        )
        connection.executemany(
            "INSERT INTO merchant_stock(" 
            "id, npc_id, name, quantity, rarity, durability, maximum_durability, "
            "base_value, description, display_order" 
            ") VALUES (?, 'npc-roadside-merchant', ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ("stock-roadside-health-potion", "Health Potion", 4, "common", None, None, 50,
                 "A restorative potion that heals 15 health.", 0),
                ("stock-roadside-arrows", "Arrows", 20, "common", None, None, 1,
                 "Field arrows sold individually.", 1),
                ("stock-roadside-shortsword", "Shortsword", 1, "uncommon", 100, 100, 10,
                 "A dependable steel blade suitable for either hand.", 2),
                ("stock-roadside-leather", "Leather Armor", 1, "common", 100, 100, 10,
                 "Supple armor offering protection without excessive weight.", 3),
                ("stock-roadside-lockpick", "Lockpick", 5, "common", None, None, 5,
                 "Used to open locked doors, chests, and mechanisms.", 4),
                ("stock-roadside-rope", "Rope", 3, "common", None, None, 1,
                 "A sturdy length of rope for climbing and securing gear.", 5),
            ),
        )
        connection.execute(
            "INSERT INTO campaign_flags(campaign_id, flag_key, value_json) "
            "VALUES (?, 'merchant_helped', 'true')",
            (DEMO_CAMPAIGN_ID,),
        )
        seed_crafting_recipes(connection, DEMO_CAMPAIGN_ID)
        connection.execute(
            """
            INSERT INTO world_facts(id, campaign_id, subject, predicate, value_json)
            VALUES ('fact-greystone-route', ?, 'Greystone Road', 'route_open', 'true')
            """,
            (DEMO_CAMPAIGN_ID,),
        )
        connection.execute(
            """
            INSERT INTO app_settings(key, value) VALUES ('active_campaign_id', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (DEMO_CAMPAIGN_ID,),
        )
    return DEMO_CAMPAIGN_ID
