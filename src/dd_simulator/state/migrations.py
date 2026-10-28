"""Ordered, append-only SQLite schema migrations."""

from __future__ import annotations

import sqlite3


MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE campaigns (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'paused', 'complete', 'archived')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE campaign_clock (
            campaign_id TEXT PRIMARY KEY REFERENCES campaigns(id) ON DELETE CASCADE,
            day INTEGER NOT NULL DEFAULT 1 CHECK (day >= 1),
            period TEXT NOT NULL DEFAULT 'Morning',
            time_label TEXT NOT NULL DEFAULT 'Morning, Day 1'
        );

        CREATE TABLE locations (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            region TEXT NOT NULL DEFAULT '',
            weather TEXT NOT NULL DEFAULT '',
            danger TEXT NOT NULL DEFAULT '',
            route_status TEXT NOT NULL DEFAULT '',
            is_current INTEGER NOT NULL DEFAULT 0 CHECK (is_current IN (0, 1))
        );
        CREATE UNIQUE INDEX one_current_location_per_campaign
            ON locations(campaign_id) WHERE is_current = 1;

        CREATE TABLE characters (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 1 CHECK (level >= 1),
            character_class TEXT NOT NULL DEFAULT 'Adventurer',
            portrait_initials TEXT NOT NULL DEFAULT '',
            currency INTEGER NOT NULL DEFAULT 0 CHECK (currency >= 0),
            carry_weight INTEGER NOT NULL DEFAULT 0 CHECK (carry_weight >= 0),
            carry_capacity INTEGER NOT NULL DEFAULT 0 CHECK (carry_capacity >= 0),
            inventory_capacity INTEGER NOT NULL DEFAULT 20 CHECK (inventory_capacity >= 0),
            is_player INTEGER NOT NULL DEFAULT 0 CHECK (is_player IN (0, 1))
        );
        CREATE UNIQUE INDEX one_player_per_campaign
            ON characters(campaign_id) WHERE is_player = 1;

        CREATE TABLE character_attributes (
            id TEXT PRIMARY KEY,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            value INTEGER NOT NULL,
            modifier INTEGER NOT NULL DEFAULT 0,
            display_order INTEGER NOT NULL DEFAULT 0,
            UNIQUE(character_id, name)
        );

        CREATE TABLE character_resources (
            id TEXT PRIMARY KEY,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            current_value INTEGER NOT NULL CHECK (current_value >= 0),
            maximum_value INTEGER NOT NULL CHECK (maximum_value > 0),
            resource_type TEXT NOT NULL,
            tooltip TEXT NOT NULL DEFAULT '',
            sidebar_tooltip TEXT NOT NULL DEFAULT '',
            display_order INTEGER NOT NULL DEFAULT 0,
            show_in_summary INTEGER NOT NULL DEFAULT 0 CHECK (show_in_summary IN (0, 1)),
            show_in_sidebar INTEGER NOT NULL DEFAULT 0 CHECK (show_in_sidebar IN (0, 1)),
            UNIQUE(character_id, resource_type)
        );

        CREATE TABLE skills (
            id TEXT PRIMARY KEY,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 1 CHECK (level >= 0),
            current_xp INTEGER NOT NULL DEFAULT 0 CHECK (current_xp >= 0),
            next_level_xp INTEGER NOT NULL DEFAULT 0 CHECK (next_level_xp >= 0),
            bonus INTEGER NOT NULL DEFAULT 0,
            locked INTEGER NOT NULL DEFAULT 0 CHECK (locked IN (0, 1)),
            recently_increased INTEGER NOT NULL DEFAULT 0 CHECK (recently_increased IN (0, 1)),
            display_order INTEGER NOT NULL DEFAULT 0,
            UNIQUE(character_id, name)
        );

        CREATE TABLE abilities (
            id TEXT PRIMARY KEY,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            resource_type TEXT,
            resource_cost INTEGER NOT NULL DEFAULT 0 CHECK (resource_cost >= 0),
            cooldown_turns INTEGER NOT NULL DEFAULT 0 CHECK (cooldown_turns >= 0),
            unlocked INTEGER NOT NULL DEFAULT 1 CHECK (unlocked IN (0, 1)),
            UNIQUE(character_id, name)
        );

        CREATE TABLE status_effects (
            id TEXT PRIMARY KEY,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            remaining_turns INTEGER CHECK (remaining_turns IS NULL OR remaining_turns >= 0),
            source TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE inventory_items (
            id TEXT PRIMARY KEY,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            slot_index INTEGER NOT NULL CHECK (slot_index >= 0),
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
            rarity TEXT NOT NULL DEFAULT 'common',
            durability INTEGER CHECK (durability IS NULL OR durability >= 0),
            maximum_durability INTEGER CHECK (maximum_durability IS NULL OR maximum_durability > 0),
            quest_item INTEGER NOT NULL DEFAULT 0 CHECK (quest_item IN (0, 1)),
            selected INTEGER NOT NULL DEFAULT 0 CHECK (selected IN (0, 1)),
            description TEXT NOT NULL DEFAULT '',
            UNIQUE(character_id, slot_index)
        );

        CREATE TABLE equipment_slots (
            id TEXT PRIMARY KEY,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            slot_index INTEGER NOT NULL CHECK (slot_index >= 0),
            slot_name TEXT NOT NULL,
            item_name TEXT,
            condition TEXT NOT NULL DEFAULT '',
            selected INTEGER NOT NULL DEFAULT 0 CHECK (selected IN (0, 1)),
            UNIQUE(character_id, slot_index),
            UNIQUE(character_id, slot_name)
        );

        CREATE TABLE quests (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            progress_current INTEGER NOT NULL DEFAULT 0 CHECK (progress_current >= 0),
            progress_maximum INTEGER NOT NULL DEFAULT 1 CHECK (progress_maximum > 0),
            selected INTEGER NOT NULL DEFAULT 0 CHECK (selected IN (0, 1)),
            deadline TEXT NOT NULL DEFAULT '',
            display_order INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE quest_objectives (
            id TEXT PRIMARY KEY,
            quest_id TEXT NOT NULL REFERENCES quests(id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
            optional INTEGER NOT NULL DEFAULT 0 CHECK (optional IN (0, 1)),
            display_order INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE npcs (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            location_id TEXT REFERENCES locations(id) ON DELETE SET NULL,
            disposition TEXT NOT NULL DEFAULT 'neutral',
            notes TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE relationships (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            source_entity_id TEXT NOT NULL,
            target_entity_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            score INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE campaign_flags (
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            flag_key TEXT NOT NULL,
            value_json TEXT NOT NULL,
            PRIMARY KEY (campaign_id, flag_key)
        );

        CREATE TABLE world_facts (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            value_json TEXT NOT NULL,
            UNIQUE(campaign_id, subject, predicate)
        );

        CREATE TABLE narratives (
            campaign_id TEXT PRIMARY KEY REFERENCES campaigns(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            paragraphs_json TEXT NOT NULL,
            dialogue TEXT NOT NULL DEFAULT '',
            prompt TEXT NOT NULL DEFAULT '',
            suggested_actions_json TEXT NOT NULL DEFAULT '[]'
        );

        CREATE TABLE events (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            time_label TEXT NOT NULL,
            category TEXT NOT NULL,
            summary TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            is_recent INTEGER NOT NULL DEFAULT 0 CHECK (is_recent IN (0, 1)),
            UNIQUE(campaign_id, sequence)
        );

        CREATE TABLE journal_entries (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            day INTEGER NOT NULL CHECK (day >= 1),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    (
        2,
        """
        ALTER TABLE campaigns
            ADD COLUMN creation_complete INTEGER NOT NULL DEFAULT 1
            CHECK (creation_complete IN (0, 1));

        ALTER TABLE characters ADD COLUMN species TEXT NOT NULL DEFAULT '';
        ALTER TABLE characters ADD COLUMN age INTEGER CHECK (age IS NULL OR age >= 0);
        ALTER TABLE characters ADD COLUMN gender_identity TEXT NOT NULL DEFAULT '';
        ALTER TABLE characters ADD COLUMN pronouns TEXT NOT NULL DEFAULT '';
        ALTER TABLE characters ADD COLUMN body_description TEXT NOT NULL DEFAULT '';
        ALTER TABLE characters ADD COLUMN face_description TEXT NOT NULL DEFAULT '';
        ALTER TABLE characters ADD COLUMN clothing_style TEXT NOT NULL DEFAULT '';
        ALTER TABLE characters ADD COLUMN background TEXT NOT NULL DEFAULT '';
        ALTER TABLE characters ADD COLUMN personality_json TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE characters ADD COLUMN primary_strength TEXT NOT NULL DEFAULT '';
        ALTER TABLE characters ADD COLUMN meaningful_flaw TEXT NOT NULL DEFAULT '';
        ALTER TABLE characters ADD COLUMN motivation TEXT NOT NULL DEFAULT '';
        ALTER TABLE characters ADD COLUMN biography TEXT NOT NULL DEFAULT '';
        ALTER TABLE characters ADD COLUMN backstory TEXT NOT NULL DEFAULT '';

        CREATE TABLE campaign_preferences (
            campaign_id TEXT PRIMARY KEY REFERENCES campaigns(id) ON DELETE CASCADE,
            world_type TEXT NOT NULL,
            tone TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            content_preferences TEXT NOT NULL DEFAULT '',
            visual_style TEXT NOT NULL,
            camera_style TEXT NOT NULL
        );
        """,
    ),
    (
        3,
        """
        ALTER TABLE inventory_items ADD COLUMN item_type TEXT NOT NULL DEFAULT 'misc'
            CHECK (item_type IN ('misc', 'consumable', 'charged', 'equipment', 'quest', 'currency', 'tool'));
        ALTER TABLE inventory_items ADD COLUMN consumable INTEGER NOT NULL DEFAULT 0
            CHECK (consumable IN (0, 1));
        ALTER TABLE inventory_items ADD COLUMN charges INTEGER
            CHECK (charges IS NULL OR charges >= 0);
        ALTER TABLE inventory_items ADD COLUMN maximum_charges INTEGER
            CHECK (maximum_charges IS NULL OR maximum_charges > 0);
        ALTER TABLE inventory_items ADD COLUMN equip_slot TEXT NOT NULL DEFAULT '';
        ALTER TABLE inventory_items ADD COLUMN use_effect_json TEXT NOT NULL DEFAULT '{}';
        ALTER TABLE equipment_slots ADD COLUMN inventory_item_id TEXT
            REFERENCES inventory_items(id) ON DELETE SET NULL;
        CREATE INDEX equipment_inventory_item ON equipment_slots(inventory_item_id);

        UPDATE inventory_items SET item_type = 'quest' WHERE quest_item = 1;
        UPDATE inventory_items SET item_type = 'currency' WHERE name = 'Gold';

        UPDATE inventory_items
        SET item_type = 'consumable', consumable = 1,
            use_effect_json = '{"resources":{"health":15},"remove_statuses":[],"use_summary":"Drank a Health Potion."}'
        WHERE name = 'Health Potion';
        UPDATE inventory_items
        SET item_type = 'consumable', consumable = 1,
            use_effect_json = '{"resources":{"health":8},"remove_statuses":[],"use_summary":"Applied Bandages."}'
        WHERE name = 'Bandages';
        UPDATE inventory_items
        SET item_type = 'consumable', consumable = 1,
            use_effect_json = '{"resources":{"stamina":6},"remove_statuses":[],"use_summary":"Ate Travel Rations."}'
        WHERE name = 'Travel Rations';
        UPDATE inventory_items
        SET item_type = 'consumable', consumable = 1,
            use_effect_json = '{"resources":{"stamina":2},"remove_statuses":[],"use_summary":"Drank from a Water Flask."}'
        WHERE name = 'Water Flask';
        UPDATE inventory_items
        SET item_type = 'consumable', consumable = 1,
            use_effect_json = '{"resources":{},"remove_statuses":["Poisoned"],"use_summary":"Used an Antidote."}'
        WHERE name = 'Antidote';
        UPDATE inventory_items
        SET item_type = 'consumable', consumable = 1,
            use_effect_json = '{"resources":{},"remove_statuses":[],"use_summary":"Lit a Torch."}'
        WHERE name = 'Torch';
        UPDATE inventory_items
        SET item_type = 'charged', charges = 20, maximum_charges = 20,
            use_effect_json = '{"resources":{},"remove_statuses":[],"use_summary":"Struck Flint & Steel."}'
        WHERE name = 'Flint & Steel';

        UPDATE inventory_items SET item_type = 'equipment', equip_slot = 'Main Hand'
        WHERE lower(name) IN (
            'iron dagger', 'longsword', 'shortsword', 'battleaxe', 'warhammer',
            'spear', 'quarterstaff', 'dagger', 'mace', 'rapier', 'greatsword',
            'handaxe', 'wand', 'parrying blade', 'shortbow', 'longbow',
            'light crossbow', 'heavy crossbow', 'throwing knives', 'sling'
        );
        UPDATE inventory_items SET item_type = 'equipment', equip_slot = 'Off Hand'
        WHERE lower(name) IN ('oak shield', 'wooden shield', 'round shield', 'kite shield', 'buckler');
        UPDATE inventory_items SET item_type = 'equipment', equip_slot = 'Body'
        WHERE lower(name) IN (
            'traveling clothes', 'padded armor', 'leather armor', 'studded leather',
            'chain shirt', 'scale mail', 'chain mail', 'mage robes',
            'druidic leathers', 'warden coat'
        );
        UPDATE inventory_items SET item_type = 'equipment', equip_slot = 'Ring'
        WHERE lower(name) IN ('silver ring', 'signet ring');
        UPDATE inventory_items SET item_type = 'equipment', equip_slot = 'Neck'
        WHERE lower(name) IN ('family locket', 'prayer beads');

        UPDATE equipment_slots
        SET inventory_item_id = (
            SELECT inventory_items.id
            FROM inventory_items
            WHERE inventory_items.character_id = equipment_slots.character_id
              AND inventory_items.name = equipment_slots.item_name
            ORDER BY inventory_items.slot_index
            LIMIT 1
        )
        WHERE item_name IS NOT NULL;
        """,
    ),
    (
        4,
        """
        ALTER TABLE campaign_clock ADD COLUMN minute_of_day INTEGER NOT NULL DEFAULT 480
            CHECK (minute_of_day >= 0 AND minute_of_day < 1440);
        ALTER TABLE campaign_clock ADD COLUMN turn_number INTEGER NOT NULL DEFAULT 0
            CHECK (turn_number >= 0);
        UPDATE campaign_clock SET minute_of_day = CASE lower(period)
            WHEN 'afternoon' THEN 780
            WHEN 'evening' THEN 1080
            WHEN 'night' THEN 1320
            ELSE 480
        END;

        CREATE TABLE action_turns (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            turn_number INTEGER NOT NULL CHECK (turn_number >= 1),
            player_action TEXT NOT NULL,
            narration TEXT NOT NULL,
            state_changes_json TEXT NOT NULL DEFAULT '[]',
            quest_notes_json TEXT NOT NULL DEFAULT '[]',
            suggested_actions_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(campaign_id, turn_number)
        );
        """,
    ),
    (
        5,
        """
        ALTER TABLE narratives ADD COLUMN player_action TEXT NOT NULL DEFAULT '';
        ALTER TABLE narratives
            ADD COLUMN response_segments_json TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE action_turns
            ADD COLUMN response_segments_json TEXT NOT NULL DEFAULT '[]';
        """,
    ),
    (
        6,
        """
        CREATE TABLE narrative_messages (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            turn_number INTEGER NOT NULL CHECK (turn_number >= 0),
            sequence INTEGER NOT NULL CHECK (sequence >= 0),
            kind TEXT NOT NULL
                CHECK (kind IN ('player', 'narrative', 'monologue', 'spoken')),
            text TEXT NOT NULL CHECK (length(trim(text)) > 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(campaign_id, turn_number, sequence)
        );
        CREATE INDEX narrative_message_order
            ON narrative_messages(campaign_id, turn_number, sequence);

        INSERT INTO narrative_messages(
            id, campaign_id, turn_number, sequence, kind, text, created_at
        )
        SELECT id || '-player', campaign_id, turn_number, 0, 'player',
               player_action, created_at
        FROM action_turns;

        INSERT INTO narrative_messages(
            id, campaign_id, turn_number, sequence, kind, text, created_at
        )
        SELECT id || '-response', campaign_id, turn_number, 1, 'narrative',
               narration, created_at
        FROM action_turns;
        """,
    ),
    (
        7,
        """
        ALTER TABLE narrative_messages RENAME TO narrative_messages_v6;

        CREATE TABLE narrative_messages (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            turn_number INTEGER NOT NULL CHECK (turn_number >= 0),
            sequence INTEGER NOT NULL CHECK (sequence >= 0),
            kind TEXT NOT NULL CHECK (
                kind IN (
                    'player', 'narrative', 'monologue', 'spoken', 'combat', 'system'
                )
            ),
            text TEXT NOT NULL CHECK (length(trim(text)) > 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(campaign_id, turn_number, sequence)
        );
        INSERT INTO narrative_messages(
            id, campaign_id, turn_number, sequence, kind, text, created_at
        )
        SELECT id, campaign_id, turn_number, sequence, kind, text, created_at
        FROM narrative_messages_v6;
        DROP TABLE narrative_messages_v6;
        CREATE INDEX narrative_message_order
            ON narrative_messages(campaign_id, turn_number, sequence);

        CREATE TABLE combat_encounters (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            location_id TEXT REFERENCES locations(id) ON DELETE SET NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK (
                status IN ('active', 'victory', 'defeat', 'escaped', 'resolved')
            ),
            round_number INTEGER NOT NULL DEFAULT 1 CHECK (round_number >= 1),
            current_index INTEGER NOT NULL DEFAULT 0 CHECK (current_index >= 0),
            starting_distance INTEGER NOT NULL DEFAULT 25
                CHECK (starting_distance >= 0),
            environment TEXT NOT NULL DEFAULT '',
            hazard TEXT NOT NULL DEFAULT '',
            end_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX one_active_combat_per_campaign
            ON combat_encounters(campaign_id) WHERE status = 'active';
        CREATE INDEX combat_encounter_history
            ON combat_encounters(campaign_id, created_at DESC);

        CREATE TABLE combatants (
            id TEXT PRIMARY KEY,
            encounter_id TEXT NOT NULL
                REFERENCES combat_encounters(id) ON DELETE CASCADE,
            character_id TEXT REFERENCES characters(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            side TEXT NOT NULL CHECK (side IN ('player', 'ally', 'enemy')),
            status TEXT NOT NULL DEFAULT 'active' CHECK (
                status IN ('active', 'defeated', 'retreated', 'surrendered')
            ),
            current_health INTEGER NOT NULL CHECK (current_health >= 0),
            maximum_health INTEGER NOT NULL CHECK (maximum_health > 0),
            armor_class INTEGER NOT NULL CHECK (armor_class >= 0),
            attack_bonus INTEGER NOT NULL DEFAULT 0,
            damage_dice_count INTEGER NOT NULL DEFAULT 1
                CHECK (damage_dice_count >= 1),
            damage_die_size INTEGER NOT NULL DEFAULT 4 CHECK (damage_die_size >= 2),
            damage_bonus INTEGER NOT NULL DEFAULT 0,
            initiative INTEGER NOT NULL DEFAULT 0,
            initiative_modifier INTEGER NOT NULL DEFAULT 0,
            distance_feet INTEGER NOT NULL DEFAULT 0 CHECK (distance_feet >= 0),
            movement_feet INTEGER NOT NULL DEFAULT 15 CHECK (movement_feet >= 0),
            attack_range_feet INTEGER NOT NULL DEFAULT 5
                CHECK (attack_range_feet >= 0),
            cover_bonus INTEGER NOT NULL DEFAULT 0,
            morale INTEGER NOT NULL DEFAULT 50 CHECK (morale BETWEEN 0 AND 100),
            intelligence TEXT NOT NULL DEFAULT 'average',
            weapon_name TEXT NOT NULL DEFAULT '',
            weapon_item_id TEXT REFERENCES inventory_items(id) ON DELETE SET NULL,
            declared_intent TEXT NOT NULL DEFAULT '',
            display_order INTEGER NOT NULL DEFAULT 0,
            UNIQUE(encounter_id, display_order)
        );
        CREATE INDEX combatant_encounter_order
            ON combatants(encounter_id, display_order);

        CREATE TABLE combat_conditions (
            id TEXT PRIMARY KEY,
            combatant_id TEXT NOT NULL REFERENCES combatants(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            armor_modifier INTEGER NOT NULL DEFAULT 0,
            attack_modifier INTEGER NOT NULL DEFAULT 0,
            remaining_rounds INTEGER CHECK (
                remaining_rounds IS NULL OR remaining_rounds >= 0
            ),
            source TEXT NOT NULL DEFAULT '',
            UNIQUE(combatant_id, name)
        );

        CREATE TABLE combat_turns (
            id TEXT PRIMARY KEY,
            encounter_id TEXT NOT NULL
                REFERENCES combat_encounters(id) ON DELETE CASCADE,
            round_number INTEGER NOT NULL CHECK (round_number >= 1),
            sequence INTEGER NOT NULL CHECK (sequence >= 0),
            actor_id TEXT NOT NULL REFERENCES combatants(id),
            target_id TEXT REFERENCES combatants(id),
            action_type TEXT NOT NULL CHECK (
                action_type IN (
                    'attack', 'ability', 'advance', 'defend', 'use_item', 'flee',
                    'retreat', 'surrender', 'wait'
                )
            ),
            d20_roll INTEGER CHECK (d20_roll IS NULL OR d20_roll BETWEEN 1 AND 20),
            modifier INTEGER NOT NULL DEFAULT 0,
            total INTEGER,
            target_number INTEGER,
            damage INTEGER NOT NULL DEFAULT 0 CHECK (damage >= 0),
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(encounter_id, sequence)
        );
        CREATE INDEX combat_turn_order ON combat_turns(encounter_id, sequence);

        UPDATE inventory_items
        SET item_type = 'equipment', equip_slot = 'Ammunition'
        WHERE lower(name) IN ('arrows', 'bolts', 'sling stones');

        INSERT INTO equipment_slots(
            id, character_id, slot_index, slot_name, item_name, condition,
            selected, inventory_item_id
        )
        SELECT 'equipment-ammunition-' || characters.id,
               characters.id,
               COALESCE((
                   SELECT MAX(slot_index) + 1 FROM equipment_slots existing
                   WHERE existing.character_id = characters.id
               ), 0),
               'Ammunition', NULL, '', 0, NULL
        FROM characters
        WHERE NOT EXISTS (
            SELECT 1 FROM equipment_slots existing
            WHERE existing.character_id = characters.id
              AND lower(existing.slot_name) = 'ammunition'
        );
        """,
    ),
    (
        8,
        """
        ALTER TABLE abilities ADD COLUMN action_key TEXT NOT NULL DEFAULT '';
        ALTER TABLE abilities ADD COLUMN action_kind TEXT NOT NULL DEFAULT 'ability'
            CHECK (action_kind IN ('ability', 'spell'));
        ALTER TABLE abilities ADD COLUMN spell_slot_cost INTEGER NOT NULL DEFAULT 0
            CHECK (spell_slot_cost >= 0);
        ALTER TABLE abilities ADD COLUMN current_uses INTEGER
            CHECK (current_uses IS NULL OR current_uses >= 0);
        ALTER TABLE abilities ADD COLUMN maximum_uses INTEGER
            CHECK (maximum_uses IS NULL OR maximum_uses > 0);
        ALTER TABLE abilities ADD COLUMN cooldown_remaining INTEGER NOT NULL DEFAULT 0
            CHECK (cooldown_remaining >= 0);
        ALTER TABLE abilities ADD COLUMN display_order INTEGER NOT NULL DEFAULT 0;
        CREATE UNIQUE INDEX ability_action_key
            ON abilities(character_id, action_key) WHERE action_key <> '';

        ALTER TABLE combat_conditions ADD COLUMN damage_modifier INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE combat_conditions ADD COLUMN damage_per_round INTEGER NOT NULL DEFAULT 0
            CHECK (damage_per_round >= 0);
        ALTER TABLE combat_conditions ADD COLUMN healing_per_round INTEGER NOT NULL DEFAULT 0
            CHECK (healing_per_round >= 0);

        ALTER TABLE combat_turns RENAME TO combat_turns_v7;
        CREATE TABLE combat_turns (
            id TEXT PRIMARY KEY,
            encounter_id TEXT NOT NULL
                REFERENCES combat_encounters(id) ON DELETE CASCADE,
            round_number INTEGER NOT NULL CHECK (round_number >= 1),
            sequence INTEGER NOT NULL CHECK (sequence >= 0),
            actor_id TEXT NOT NULL REFERENCES combatants(id),
            target_id TEXT REFERENCES combatants(id),
            action_type TEXT NOT NULL CHECK (
                action_type IN (
                    'attack', 'ability', 'spell', 'advance', 'defend', 'use_item',
                    'flee', 'retreat', 'surrender', 'wait', 'effect'
                )
            ),
            action_key TEXT NOT NULL DEFAULT '',
            d20_roll INTEGER CHECK (d20_roll IS NULL OR d20_roll BETWEEN 1 AND 20),
            modifier INTEGER NOT NULL DEFAULT 0,
            total INTEGER,
            target_number INTEGER,
            damage INTEGER NOT NULL DEFAULT 0 CHECK (damage >= 0),
            healing INTEGER NOT NULL DEFAULT 0 CHECK (healing >= 0),
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(encounter_id, sequence)
        );
        INSERT INTO combat_turns(
            id, encounter_id, round_number, sequence, actor_id, target_id,
            action_type, d20_roll, modifier, total, target_number, damage, summary,
            created_at
        )
        SELECT id, encounter_id, round_number, sequence, actor_id, target_id,
               action_type, d20_roll, modifier, total, target_number, damage, summary,
               created_at
        FROM combat_turns_v7;
        DROP TABLE combat_turns_v7;
        CREATE INDEX combat_turn_order ON combat_turns(encounter_id, sequence);
        """,
    ),
    (
        9,
        """
        CREATE TABLE enemy_archetypes (
            archetype_key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            tier INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 5),
            biome TEXT NOT NULL DEFAULT 'any',
            maximum_health INTEGER NOT NULL CHECK (maximum_health > 0),
            armor_class INTEGER NOT NULL CHECK (armor_class >= 0),
            attack_bonus INTEGER NOT NULL DEFAULT 0,
            damage_die_size INTEGER NOT NULL DEFAULT 4 CHECK (damage_die_size >= 2),
            damage_bonus INTEGER NOT NULL DEFAULT 0,
            initiative_modifier INTEGER NOT NULL DEFAULT 0,
            distance_feet INTEGER NOT NULL DEFAULT 25 CHECK (distance_feet >= 0),
            movement_feet INTEGER NOT NULL DEFAULT 15 CHECK (movement_feet >= 0),
            attack_range_feet INTEGER NOT NULL DEFAULT 5 CHECK (attack_range_feet >= 0),
            morale INTEGER NOT NULL DEFAULT 50 CHECK (morale BETWEEN 0 AND 100),
            intelligence TEXT NOT NULL DEFAULT 'average',
            weapon_name TEXT NOT NULL DEFAULT 'Weapon',
            abilities_json TEXT NOT NULL DEFAULT '[]',
            resistances_json TEXT NOT NULL DEFAULT '[]',
            vulnerabilities_json TEXT NOT NULL DEFAULT '[]',
            behavior_profile TEXT NOT NULL DEFAULT '',
            loot_table_json TEXT NOT NULL DEFAULT '[]',
            reinforcement_key TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        ALTER TABLE combat_encounters ADD COLUMN generated INTEGER NOT NULL DEFAULT 0
            CHECK (generated IN (0, 1));
        ALTER TABLE combat_encounters ADD COLUMN intro_complete INTEGER NOT NULL DEFAULT 1
            CHECK (intro_complete IN (0, 1));
        ALTER TABLE combat_encounters ADD COLUMN introduction TEXT NOT NULL DEFAULT '';
        ALTER TABLE combat_encounters ADD COLUMN terrain TEXT NOT NULL DEFAULT '';
        ALTER TABLE combat_encounters ADD COLUMN awareness_state TEXT NOT NULL DEFAULT 'aware'
            CHECK (awareness_state IN ('aware', 'player_surprised', 'enemies_surprised'));
        ALTER TABLE combat_encounters ADD COLUMN difficulty_rating INTEGER NOT NULL DEFAULT 1
            CHECK (difficulty_rating BETWEEN 1 AND 10);
        ALTER TABLE combat_encounters ADD COLUMN preparation_choice TEXT NOT NULL DEFAULT '';
        ALTER TABLE combat_encounters ADD COLUMN reinforcement_archetype_key TEXT NOT NULL DEFAULT '';
        ALTER TABLE combat_encounters ADD COLUMN reinforcement_round INTEGER;
        ALTER TABLE combat_encounters ADD COLUMN reinforcement_arrived INTEGER NOT NULL DEFAULT 0
            CHECK (reinforcement_arrived IN (0, 1));

        ALTER TABLE combatants ADD COLUMN archetype_key TEXT NOT NULL DEFAULT '';
        ALTER TABLE combatants ADD COLUMN abilities_json TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE combatants ADD COLUMN resistances_json TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE combatants ADD COLUMN vulnerabilities_json TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE combatants ADD COLUMN behavior_profile TEXT NOT NULL DEFAULT '';

        CREATE TABLE combat_rewards (
            id TEXT PRIMARY KEY,
            encounter_id TEXT NOT NULL UNIQUE
                REFERENCES combat_encounters(id) ON DELETE CASCADE,
            outcome TEXT NOT NULL CHECK (
                outcome IN ('victory', 'defeat', 'escaped', 'resolved')
            ),
            experience INTEGER NOT NULL DEFAULT 0 CHECK (experience >= 0),
            skill_experience INTEGER NOT NULL DEFAULT 0 CHECK (skill_experience >= 0),
            currency INTEGER NOT NULL DEFAULT 0 CHECK (currency >= 0),
            progression_applied INTEGER NOT NULL DEFAULT 0
                CHECK (progression_applied IN (0, 1)),
            acknowledged INTEGER NOT NULL DEFAULT 0 CHECK (acknowledged IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            acknowledged_at TEXT
        );

        CREATE TABLE combat_reward_items (
            id TEXT PRIMARY KEY,
            reward_id TEXT NOT NULL REFERENCES combat_rewards(id) ON DELETE CASCADE,
            item_key TEXT NOT NULL,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
            rarity TEXT NOT NULL DEFAULT 'common' CHECK (
                rarity IN ('common', 'uncommon', 'rare', 'epic', 'legendary')
            ),
            description TEXT NOT NULL DEFAULT '',
            claimed INTEGER NOT NULL DEFAULT 0 CHECK (claimed IN (0, 1)),
            claimed_at TEXT,
            UNIQUE(reward_id, item_key)
        );
        CREATE INDEX combat_reward_pending
            ON combat_rewards(acknowledged, created_at DESC);
        CREATE INDEX combat_reward_item_claims
            ON combat_reward_items(reward_id, claimed);
        """,
    ),
    (
        10,
        """
        ALTER TABLE quests ADD COLUMN quest_type TEXT NOT NULL DEFAULT 'main'
            CHECK (quest_type IN ('main', 'optional', 'follow_up'));
        ALTER TABLE quests ADD COLUMN started_day INTEGER CHECK (started_day IS NULL OR started_day >= 1);
        ALTER TABLE quests ADD COLUMN started_minute INTEGER CHECK (
            started_minute IS NULL OR started_minute BETWEEN 0 AND 1439
        );
        ALTER TABLE quests ADD COLUMN deadline_day INTEGER CHECK (deadline_day IS NULL OR deadline_day >= 1);
        ALTER TABLE quests ADD COLUMN deadline_minute INTEGER CHECK (
            deadline_minute IS NULL OR deadline_minute BETWEEN 0 AND 1439
        );
        ALTER TABLE quests ADD COLUMN completed_at TEXT;
        ALTER TABLE quests ADD COLUMN failed_at TEXT;
        ALTER TABLE quests ADD COLUMN abandoned_at TEXT;
        ALTER TABLE quests ADD COLUMN failure_reason TEXT NOT NULL DEFAULT '';
        ALTER TABLE quests ADD COLUMN reward_experience INTEGER NOT NULL DEFAULT 100 CHECK (reward_experience >= 0);
        ALTER TABLE quests ADD COLUMN reward_currency INTEGER NOT NULL DEFAULT 25 CHECK (reward_currency >= 0);
        ALTER TABLE quests ADD COLUMN reward_reputation INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE quests ADD COLUMN reward_faction TEXT NOT NULL DEFAULT '';
        ALTER TABLE quests ADD COLUMN reward_items_json TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE quests ADD COLUMN follow_up_quest_id TEXT REFERENCES quests(id) ON DELETE SET NULL;

        ALTER TABLE quest_objectives ADD COLUMN trigger_type TEXT NOT NULL DEFAULT 'custom_action'
            CHECK (trigger_type IN (
                'combat', 'travel', 'item_collect', 'item_use', 'item_examine',
                'dialogue', 'custom_action'
            ));
        ALTER TABLE quest_objectives ADD COLUMN trigger_target TEXT NOT NULL DEFAULT '';
        ALTER TABLE quest_objectives ADD COLUMN current_count INTEGER NOT NULL DEFAULT 0 CHECK (current_count >= 0);
        ALTER TABLE quest_objectives ADD COLUMN required_count INTEGER NOT NULL DEFAULT 1 CHECK (required_count > 0);
        ALTER TABLE quest_objectives ADD COLUMN completed_at TEXT;

        UPDATE quests SET quest_type = 'optional', status = 'active'
            WHERE lower(status) = 'optional';
        UPDATE quests SET status = 'completed', completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP), selected = 0
            WHERE lower(status) = 'complete';
        UPDATE quests SET started_day = 1, started_minute = 480
            WHERE lower(status) = 'active';
        UPDATE quest_objectives SET current_count = CASE WHEN completed = 1 THEN 1 ELSE 0 END;
        UPDATE quest_objectives SET trigger_type = 'travel'
            WHERE lower(text) LIKE 'travel %' OR lower(text) LIKE 'return %';
        UPDATE quest_objectives SET trigger_type = 'item_collect'
            WHERE lower(text) LIKE 'recover %' OR lower(text) LIKE 'collect %';

        CREATE TABLE quest_updates (
            id TEXT PRIMARY KEY,
            quest_id TEXT NOT NULL REFERENCES quests(id) ON DELETE CASCADE,
            objective_id TEXT REFERENCES quest_objectives(id) ON DELETE SET NULL,
            update_type TEXT NOT NULL CHECK (
                update_type IN ('activated', 'progress', 'completed', 'failed', 'abandoned')
            ),
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE faction_reputation (
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            faction TEXT NOT NULL,
            score INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (campaign_id, faction)
        );

        CREATE TABLE quest_rewards (
            id TEXT PRIMARY KEY,
            quest_id TEXT NOT NULL UNIQUE REFERENCES quests(id) ON DELETE CASCADE,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            experience INTEGER NOT NULL DEFAULT 0 CHECK (experience >= 0),
            currency INTEGER NOT NULL DEFAULT 0 CHECK (currency >= 0),
            reputation INTEGER NOT NULL DEFAULT 0,
            faction TEXT NOT NULL DEFAULT '',
            progression_applied INTEGER NOT NULL DEFAULT 0 CHECK (progression_applied IN (0, 1)),
            acknowledged INTEGER NOT NULL DEFAULT 0 CHECK (acknowledged IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            acknowledged_at TEXT
        );

        CREATE TABLE quest_reward_items (
            id TEXT PRIMARY KEY,
            reward_id TEXT NOT NULL REFERENCES quest_rewards(id) ON DELETE CASCADE,
            item_key TEXT NOT NULL,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
            rarity TEXT NOT NULL DEFAULT 'common',
            description TEXT NOT NULL DEFAULT '',
            claimed INTEGER NOT NULL DEFAULT 0 CHECK (claimed IN (0, 1)),
            claimed_at TEXT,
            UNIQUE(reward_id, item_key)
        );

        CREATE INDEX quest_status_order ON quests(campaign_id, status, display_order);
        CREATE INDEX quest_objective_triggers
            ON quest_objectives(trigger_type, trigger_target, completed);
        CREATE INDEX quest_reward_pending
            ON quest_rewards(campaign_id, acknowledged, created_at DESC);
        """,
    ),
    (
        11,
        """
        ALTER TABLE locations ADD COLUMN description TEXT NOT NULL DEFAULT '';
        ALTER TABLE locations ADD COLUMN biome TEXT NOT NULL DEFAULT 'road';
        ALTER TABLE locations ADD COLUMN discovered INTEGER NOT NULL DEFAULT 0
            CHECK (discovered IN (0, 1));
        ALTER TABLE locations ADD COLUMN visit_count INTEGER NOT NULL DEFAULT 0
            CHECK (visit_count >= 0);
        ALTER TABLE locations ADD COLUMN first_discovered_at TEXT;
        ALTER TABLE locations ADD COLUMN last_visited_at TEXT;
        ALTER TABLE locations ADD COLUMN can_camp INTEGER NOT NULL DEFAULT 0
            CHECK (can_camp IN (0, 1));
        ALTER TABLE locations ADD COLUMN map_x INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE locations ADD COLUMN map_y INTEGER NOT NULL DEFAULT 0;

        UPDATE locations
        SET discovered = 1,
            first_discovered_at = COALESCE(first_discovered_at, CURRENT_TIMESTAMP);
        UPDATE locations
        SET visit_count = MAX(1, visit_count),
            last_visited_at = COALESCE(last_visited_at, CURRENT_TIMESTAMP)
        WHERE is_current = 1;

        CREATE TABLE travel_routes (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            origin_location_id TEXT NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
            destination_location_id TEXT NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
            distance_miles INTEGER NOT NULL DEFAULT 1 CHECK (distance_miles > 0),
            travel_minutes INTEGER NOT NULL DEFAULT 60 CHECK (travel_minutes > 0),
            stamina_cost INTEGER NOT NULL DEFAULT 1 CHECK (stamina_cost >= 0),
            danger_rating INTEGER NOT NULL DEFAULT 0 CHECK (danger_rating BETWEEN 0 AND 10),
            status TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'blocked', 'locked', 'hidden')),
            requirement TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            bidirectional INTEGER NOT NULL DEFAULT 1 CHECK (bidirectional IN (0, 1)),
            discovered INTEGER NOT NULL DEFAULT 1 CHECK (discovered IN (0, 1)),
            UNIQUE(campaign_id, origin_location_id, destination_location_id)
        );
        CREATE INDEX travel_route_origin
            ON travel_routes(campaign_id, origin_location_id, status);
        CREATE INDEX travel_route_destination
            ON travel_routes(campaign_id, destination_location_id, status);

        CREATE TABLE travel_history (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            route_id TEXT REFERENCES travel_routes(id) ON DELETE SET NULL,
            origin_location_id TEXT NOT NULL REFERENCES locations(id),
            destination_location_id TEXT NOT NULL REFERENCES locations(id),
            departed_day INTEGER NOT NULL CHECK (departed_day >= 1),
            departed_minute INTEGER NOT NULL CHECK (departed_minute BETWEEN 0 AND 1439),
            arrived_day INTEGER NOT NULL CHECK (arrived_day >= 1),
            arrived_minute INTEGER NOT NULL CHECK (arrived_minute BETWEEN 0 AND 1439),
            stamina_spent INTEGER NOT NULL DEFAULT 0 CHECK (stamina_spent >= 0),
            outcome TEXT NOT NULL DEFAULT 'arrived'
                CHECK (outcome IN ('arrived', 'encounter', 'interrupted')),
            encounter_id TEXT REFERENCES combat_encounters(id) ON DELETE SET NULL,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX travel_history_campaign
            ON travel_history(campaign_id, created_at DESC);

        CREATE TABLE camp_history (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            location_id TEXT NOT NULL REFERENCES locations(id),
            started_day INTEGER NOT NULL CHECK (started_day >= 1),
            started_minute INTEGER NOT NULL CHECK (started_minute BETWEEN 0 AND 1439),
            duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX camp_history_campaign
            ON camp_history(campaign_id, created_at DESC);
        """,
    ),
    (
        12,
        """
        ALTER TABLE inventory_items ADD COLUMN inventory_position INTEGER
            CHECK (inventory_position IS NULL OR inventory_position >= 0);
        UPDATE inventory_items SET inventory_position = slot_index;
        UPDATE equipment_slots AS equipment
        SET inventory_item_id = (
            SELECT item.id FROM inventory_items AS item
            WHERE item.character_id = equipment.character_id
              AND lower(trim(item.name)) = lower(trim(equipment.item_name))
            ORDER BY item.slot_index LIMIT 1
        )
        WHERE equipment.inventory_item_id IS NULL AND equipment.item_name IS NOT NULL;
        UPDATE inventory_items
        SET inventory_position = NULL
        WHERE id IN (
            SELECT inventory_item_id FROM equipment_slots
            WHERE inventory_item_id IS NOT NULL
        );
        UPDATE inventory_items AS item
        SET inventory_position = (
            SELECT COUNT(*) FROM inventory_items AS earlier
            WHERE earlier.character_id = item.character_id
              AND earlier.inventory_position IS NOT NULL
              AND earlier.slot_index < item.slot_index
        )
        WHERE item.inventory_position IS NOT NULL;
        CREATE UNIQUE INDEX inventory_visible_position
            ON inventory_items(character_id, inventory_position)
            WHERE inventory_position IS NOT NULL;
        CREATE TRIGGER inventory_default_visible_position
        AFTER INSERT ON inventory_items
        WHEN NEW.inventory_position IS NULL
        BEGIN
            UPDATE inventory_items SET inventory_position = NEW.slot_index WHERE id = NEW.id;
        END;
        UPDATE characters SET inventory_capacity = MAX(40, inventory_capacity * 2);

        ALTER TABLE npcs ADD COLUMN status TEXT NOT NULL DEFAULT 'neutral'
            CHECK (status IN (
                'friendly', 'neutral', 'suspicious', 'hostile',
                'unavailable', 'departed', 'deceased'
            ));
        ALTER TABLE npcs ADD COLUMN title TEXT NOT NULL DEFAULT '';
        ALTER TABLE npcs ADD COLUMN portrait_initials TEXT NOT NULL DEFAULT '';
        ALTER TABLE npcs ADD COLUMN personality TEXT NOT NULL DEFAULT '';
        ALTER TABLE npcs ADD COLUMN voice_style TEXT NOT NULL DEFAULT '';
        ALTER TABLE npcs ADD COLUMN biography TEXT NOT NULL DEFAULT '';
        ALTER TABLE npcs ADD COLUMN faction TEXT NOT NULL DEFAULT 'Local';
        ALTER TABLE npcs ADD COLUMN available INTEGER NOT NULL DEFAULT 1
            CHECK (available IN (0, 1));
        ALTER TABLE npcs ADD COLUMN known INTEGER NOT NULL DEFAULT 1
            CHECK (known IN (0, 1));
        ALTER TABLE npcs ADD COLUMN offers_quest_id TEXT REFERENCES quests(id) ON DELETE SET NULL;
        ALTER TABLE npcs ADD COLUMN reveals_location_id TEXT REFERENCES locations(id) ON DELETE SET NULL;
        ALTER TABLE npcs ADD COLUMN reveals_route_id TEXT REFERENCES travel_routes(id) ON DELETE SET NULL;

        UPDATE npcs SET status = CASE lower(disposition)
            WHEN 'friendly' THEN 'friendly'
            WHEN 'hostile' THEN 'hostile'
            WHEN 'suspicious' THEN 'suspicious'
            ELSE 'neutral' END;
        UPDATE npcs
        SET portrait_initials = upper(substr(name, 1, 1)),
            personality = COALESCE(NULLIF(notes, ''), 'Observant and grounded.'),
            voice_style = 'Natural fantasy dialogue grounded in known facts.';
        UPDATE npcs SET title = 'Traveling Merchant', faction = 'Greystone Traders',
            reveals_location_id = CASE
                WHEN id = 'npc-roadside-merchant'
                 AND EXISTS (
                    SELECT 1 FROM locations
                    WHERE id = 'location-whispering-woods'
                      AND campaign_id = npcs.campaign_id
                 )
                THEN 'location-whispering-woods'
                ELSE reveals_location_id
            END
        WHERE id = 'npc-roadside-merchant';
        INSERT OR IGNORE INTO npcs(
            id, campaign_id, name, location_id, disposition, notes, status, title,
            portrait_initials, personality, voice_style, biography, faction,
            available, known, offers_quest_id
        )
        SELECT 'npc-lord-aric', campaigns.id, 'Lord Aric', 'location-greystone-keep',
               'neutral', 'Seeks the lost family heirloom.', 'neutral', 'Warden of Greystone Keep',
               'LA', 'Measured, duty-bound, and slow to trust.',
               'Formal, restrained speech with the weight of command.',
               'The hereditary warden responsible for Greystone Keep and its people.',
               'Greystone Keep', 1, 1, 'quest-heirloom'
        FROM campaigns
        WHERE campaigns.id = 'demo-greystone'
          AND EXISTS (SELECT 1 FROM locations WHERE id = 'location-greystone-keep');

        CREATE TABLE npc_conversations (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            npc_id TEXT NOT NULL REFERENCES npcs(id) ON DELETE CASCADE,
            turn_number INTEGER NOT NULL DEFAULT 1 CHECK (turn_number >= 1),
            player_text TEXT NOT NULL,
            npc_text TEXT NOT NULL,
            monologue TEXT NOT NULL DEFAULT '',
            check_type TEXT NOT NULL DEFAULT '',
            d20_roll INTEGER CHECK (d20_roll IS NULL OR d20_roll BETWEEN 1 AND 20),
            modifier INTEGER NOT NULL DEFAULT 0,
            total INTEGER,
            difficulty INTEGER,
            outcome TEXT NOT NULL DEFAULT 'neutral',
            relationship_delta INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(campaign_id, npc_id, turn_number)
        );
        CREATE INDEX npc_conversation_history
            ON npc_conversations(campaign_id, npc_id, turn_number DESC);

        CREATE TABLE npc_memories (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            npc_id TEXT NOT NULL REFERENCES npcs(id) ON DELETE CASCADE,
            summary TEXT NOT NULL,
            importance INTEGER NOT NULL DEFAULT 1 CHECK (importance BETWEEN 1 AND 5),
            source_conversation_id TEXT REFERENCES npc_conversations(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX npc_memory_importance
            ON npc_memories(campaign_id, npc_id, importance DESC, created_at DESC);

        INSERT INTO relationships(
            id, campaign_id, source_entity_id, target_entity_id,
            relationship_type, score, notes
        )
        SELECT 'relationship-player-' || npcs.id, npcs.campaign_id,
               characters.id, npcs.id, 'personal',
               CASE npcs.status WHEN 'friendly' THEN 20 WHEN 'hostile' THEN -40 ELSE 0 END,
               'Player relationship'
        FROM npcs
        JOIN characters ON characters.campaign_id = npcs.campaign_id
                       AND characters.is_player = 1
        WHERE NOT EXISTS (
            SELECT 1 FROM relationships existing
            WHERE existing.campaign_id = npcs.campaign_id
              AND existing.source_entity_id = characters.id
              AND existing.target_entity_id = npcs.id
        );
        """,
    ),
    (
        13,
        """
        ALTER TABLE inventory_items ADD COLUMN item_category TEXT NOT NULL DEFAULT 'misc';
        ALTER TABLE inventory_items ADD COLUMN weight REAL NOT NULL DEFAULT 0.1
            CHECK (weight >= 0);
        ALTER TABLE inventory_items ADD COLUMN value_gp INTEGER NOT NULL DEFAULT 0
            CHECK (value_gp >= 0);
        ALTER TABLE inventory_items ADD COLUMN identified INTEGER NOT NULL DEFAULT 1
            CHECK (identified IN (0, 1));
        ALTER TABLE inventory_items ADD COLUMN damage_text TEXT NOT NULL DEFAULT '';
        ALTER TABLE inventory_items ADD COLUMN armor_value INTEGER NOT NULL DEFAULT 0
            CHECK (armor_value >= 0);
        ALTER TABLE inventory_items ADD COLUMN healing_value INTEGER NOT NULL DEFAULT 0
            CHECK (healing_value >= 0);
        ALTER TABLE inventory_items ADD COLUMN compatible_slots_json TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE inventory_items ADD COLUMN requirements_json TEXT NOT NULL DEFAULT '{}';
        ALTER TABLE inventory_items ADD COLUMN bonuses_json TEXT NOT NULL DEFAULT '{}';
        ALTER TABLE inventory_items ADD COLUMN penalties_json TEXT NOT NULL DEFAULT '{}';
        ALTER TABLE inventory_items ADD COLUMN generated_difficulty TEXT NOT NULL DEFAULT 'Adventurer';
        ALTER TABLE inventory_items ADD COLUMN item_generation_version INTEGER NOT NULL DEFAULT 0
            CHECK (item_generation_version >= 0);

        ALTER TABLE characters ADD COLUMN equipment_armor_bonus INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE characters ADD COLUMN equipment_attack_bonus INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE characters ADD COLUMN equipment_bonuses_json TEXT NOT NULL DEFAULT '{}';
        """,
    ),
    (
        14,
        """
        CREATE TABLE visual_assets (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            asset_kind TEXT NOT NULL
                CHECK (asset_kind IN ('portrait', 'location', 'item', 'scene')),
            subject_type TEXT NOT NULL
                CHECK (subject_type IN ('character', 'location', 'item', 'scene')),
            subject_id TEXT NOT NULL,
            state_signature TEXT NOT NULL,
            version INTEGER NOT NULL CHECK (version >= 1),
            asset_role TEXT NOT NULL DEFAULT 'state'
                CHECK (asset_role IN ('canonical', 'active', 'state', 'history')),
            relative_path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            mime_type TEXT NOT NULL DEFAULT 'image/png',
            width INTEGER NOT NULL DEFAULT 0 CHECK (width >= 0),
            height INTEGER NOT NULL DEFAULT 0 CHECK (height >= 0),
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN (
                    'pending', 'confirmed', 'superseded', 'rejected', 'missing'
                )),
            canonical INTEGER NOT NULL DEFAULT 0 CHECK (canonical IN (0, 1)),
            active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
            source TEXT NOT NULL DEFAULT 'local',
            prompt_summary TEXT NOT NULL DEFAULT '',
            negative_prompt TEXT NOT NULL DEFAULT '',
            generation_seed TEXT NOT NULL DEFAULT '',
            reference_asset_ids_json TEXT NOT NULL DEFAULT '[]',
            attachment_references_json TEXT NOT NULL DEFAULT '[]',
            art_style TEXT NOT NULL DEFAULT '',
            camera_style TEXT NOT NULL DEFAULT '',
            lighting_style TEXT NOT NULL DEFAULT '',
            appearance_lock_json TEXT NOT NULL DEFAULT '{}',
            use_count INTEGER NOT NULL DEFAULT 0 CHECK (use_count >= 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            confirmed_at TEXT,
            last_used_at TEXT,
            UNIQUE(
                campaign_id, asset_kind, subject_type, subject_id,
                state_signature, version
            )
        );
        CREATE INDEX visual_asset_resolution
            ON visual_assets(
                campaign_id, asset_kind, subject_type, subject_id,
                state_signature, status, version DESC
            );
        CREATE UNIQUE INDEX visual_asset_canonical_subject
            ON visual_assets(campaign_id, asset_kind, subject_type, subject_id)
            WHERE canonical = 1 AND status = 'confirmed';
        CREATE UNIQUE INDEX visual_asset_active_subject
            ON visual_assets(campaign_id, asset_kind, subject_type, subject_id)
            WHERE active = 1 AND status = 'confirmed';

        CREATE TABLE visual_asset_history (
            id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL REFERENCES visual_assets(id) ON DELETE CASCADE,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            action TEXT NOT NULL
                CHECK (action IN (
                    'staged', 'confirmed', 'rejected', 'reused',
                    'superseded', 'missing'
                )),
            state_signature TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX visual_asset_history_subject
            ON visual_asset_history(campaign_id, asset_id, created_at DESC);
        """,
    ),
    (
        15,
        """
        CREATE TABLE campaign_state_audits (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            sequence INTEGER NOT NULL CHECK (sequence >= 1),
            event_type TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            operation_json TEXT NOT NULL DEFAULT '{}',
            before_checksum TEXT NOT NULL,
            after_checksum TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(campaign_id, sequence)
        );
        CREATE INDEX campaign_state_audit_order
            ON campaign_state_audits(campaign_id, sequence);

        CREATE TABLE campaign_checkpoints (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
            current_scene_id TEXT NOT NULL DEFAULT '',
            state_checksum TEXT NOT NULL,
            visual_references_json TEXT NOT NULL DEFAULT '[]',
            backup_relative_path TEXT NOT NULL,
            audit_sequence INTEGER NOT NULL DEFAULT 0 CHECK (audit_sequence >= 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX campaign_checkpoint_history
            ON campaign_checkpoints(campaign_id, created_at DESC, id DESC);

        CREATE TABLE campaign_repair_reports (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            status TEXT NOT NULL CHECK (status IN ('clean', 'proposed', 'applied', 'failed')),
            discrepancies_json TEXT NOT NULL DEFAULT '[]',
            corrections_json TEXT NOT NULL DEFAULT '[]',
            before_checksum TEXT NOT NULL,
            after_checksum TEXT NOT NULL DEFAULT '',
            backup_relative_path TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            applied_at TEXT
        );
        CREATE INDEX campaign_repair_history
            ON campaign_repair_reports(campaign_id, created_at DESC, id DESC);
        """,
    ),
    (
        16,
        """
        CREATE TABLE merchant_stock (
            id TEXT PRIMARY KEY,
            npc_id TEXT NOT NULL REFERENCES npcs(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 0),
            rarity TEXT NOT NULL DEFAULT 'common',
            durability INTEGER CHECK (durability IS NULL OR durability >= 0),
            maximum_durability INTEGER
                CHECK (maximum_durability IS NULL OR maximum_durability > 0),
            base_value INTEGER NOT NULL DEFAULT 1 CHECK (base_value >= 0),
            description TEXT NOT NULL DEFAULT '',
            display_order INTEGER NOT NULL DEFAULT 0,
            UNIQUE(npc_id, id)
        );
        CREATE INDEX merchant_stock_display
            ON merchant_stock(npc_id, display_order, name);

        CREATE TABLE commerce_transactions (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            npc_id TEXT NOT NULL REFERENCES npcs(id) ON DELETE CASCADE,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            action TEXT NOT NULL CHECK (action IN ('buy', 'sell', 'barter')),
            item_name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
            unit_price INTEGER NOT NULL CHECK (unit_price >= 0),
            total_price INTEGER NOT NULL CHECK (total_price >= 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX commerce_transaction_history
            ON commerce_transactions(campaign_id, created_at DESC, id DESC);

        INSERT OR IGNORE INTO merchant_stock(
            id, npc_id, name, quantity, rarity, durability,
            maximum_durability, base_value, description, display_order
        )
        SELECT 'stock-roadside-health-potion', id, 'Health Potion', 4, 'common',
               NULL, NULL, 50, 'A restorative potion that heals 15 health.', 0
        FROM npcs WHERE id = 'npc-roadside-merchant';
        INSERT OR IGNORE INTO merchant_stock(
            id, npc_id, name, quantity, rarity, durability,
            maximum_durability, base_value, description, display_order
        )
        SELECT 'stock-roadside-arrows', id, 'Arrows', 20, 'common',
               NULL, NULL, 1, 'Field arrows sold individually.', 1
        FROM npcs WHERE id = 'npc-roadside-merchant';
        INSERT OR IGNORE INTO merchant_stock(
            id, npc_id, name, quantity, rarity, durability,
            maximum_durability, base_value, description, display_order
        )
        SELECT 'stock-roadside-shortsword', id, 'Shortsword', 1, 'uncommon',
               100, 100, 10, 'A dependable steel blade suitable for either hand.', 2
        FROM npcs WHERE id = 'npc-roadside-merchant';
        INSERT OR IGNORE INTO merchant_stock(
            id, npc_id, name, quantity, rarity, durability,
            maximum_durability, base_value, description, display_order
        )
        SELECT 'stock-roadside-leather', id, 'Leather Armor', 1, 'common',
               100, 100, 10, 'Supple armor offering protection without excessive weight.', 3
        FROM npcs WHERE id = 'npc-roadside-merchant';
        INSERT OR IGNORE INTO merchant_stock(
            id, npc_id, name, quantity, rarity, durability,
            maximum_durability, base_value, description, display_order
        )
        SELECT 'stock-roadside-lockpick', id, 'Lockpick', 5, 'common',
               NULL, NULL, 5, 'Used to open locked doors, chests, and mechanisms.', 4
        FROM npcs WHERE id = 'npc-roadside-merchant';
        INSERT OR IGNORE INTO merchant_stock(
            id, npc_id, name, quantity, rarity, durability,
            maximum_durability, base_value, description, display_order
        )
        SELECT 'stock-roadside-rope', id, 'Rope', 3, 'common',
               NULL, NULL, 1, 'A sturdy length of rope for climbing and securing gear.', 5
        FROM npcs WHERE id = 'npc-roadside-merchant';
        """,
    ),
    (
        17,
        """
        CREATE TABLE crafting_recipes (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            skill_name TEXT NOT NULL DEFAULT 'Crafting',
            difficulty INTEGER NOT NULL CHECK (difficulty >= 0),
            output_name TEXT NOT NULL,
            output_quantity INTEGER NOT NULL DEFAULT 1 CHECK (output_quantity > 0),
            output_rarity TEXT NOT NULL DEFAULT 'common',
            crafting_xp INTEGER NOT NULL DEFAULT 0 CHECK (crafting_xp >= 0),
            required_tool TEXT NOT NULL DEFAULT '',
            tool_use_cost INTEGER NOT NULL DEFAULT 0 CHECK (tool_use_cost >= 0),
            unlocked INTEGER NOT NULL DEFAULT 1 CHECK (unlocked IN (0, 1)),
            display_order INTEGER NOT NULL DEFAULT 0,
            UNIQUE(campaign_id, name)
        );
        CREATE INDEX crafting_recipe_display
            ON crafting_recipes(campaign_id, unlocked DESC, display_order, name);

        CREATE TABLE crafting_recipe_ingredients (
            id TEXT PRIMARY KEY,
            recipe_id TEXT NOT NULL REFERENCES crafting_recipes(id) ON DELETE CASCADE,
            item_name TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            display_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX crafting_ingredient_recipe
            ON crafting_recipe_ingredients(recipe_id, display_order, id);

        CREATE TABLE crafting_results (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            recipe_id TEXT NOT NULL REFERENCES crafting_recipes(id) ON DELETE RESTRICT,
            recipe_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('success', 'failure')),
            score INTEGER NOT NULL,
            difficulty INTEGER NOT NULL,
            output_name TEXT NOT NULL DEFAULT '',
            output_quantity INTEGER NOT NULL DEFAULT 0 CHECK (output_quantity >= 0),
            output_rarity TEXT NOT NULL DEFAULT '',
            quality TEXT NOT NULL DEFAULT '',
            ingredients_consumed_json TEXT NOT NULL DEFAULT '[]',
            tool_uses_json TEXT NOT NULL DEFAULT '[]',
            crafting_xp INTEGER NOT NULL DEFAULT 0 CHECK (crafting_xp >= 0),
            summary TEXT NOT NULL DEFAULT '',
            acknowledged INTEGER NOT NULL DEFAULT 0 CHECK (acknowledged IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            acknowledged_at TEXT
        );
        CREATE INDEX crafting_result_pending
            ON crafting_results(campaign_id, acknowledged, created_at DESC);

        INSERT OR IGNORE INTO crafting_recipes(
            id, campaign_id, name, description, skill_name, difficulty,
            output_name, output_quantity, output_rarity, crafting_xp,
            required_tool, tool_use_cost, unlocked, display_order
        ) SELECT 'recipe-' || id || '-field-bandages', id, 'Field Bandages',
                 'Cut and bind clean cloth into dependable field dressings.',
                 'Crafting', 20, 'Bandages', 2, 'common', 12, '', 0, 1, 0
          FROM campaigns;
        INSERT OR IGNORE INTO crafting_recipes(
            id, campaign_id, name, description, skill_name, difficulty,
            output_name, output_quantity, output_rarity, crafting_xp,
            required_tool, tool_use_cost, unlocked, display_order
        ) SELECT 'recipe-' || id || '-health-potion', id, 'Restorative Draught',
                 'Steep medicinal herbs in clean water to produce a healing potion.',
                 'Crafting', 30, 'Health Potion', 1, 'common', 25,
                 'Healer''s Kit', 1, 1, 1
          FROM campaigns;
        INSERT OR IGNORE INTO crafting_recipes(
            id, campaign_id, name, description, skill_name, difficulty,
            output_name, output_quantity, output_rarity, crafting_xp,
            required_tool, tool_use_cost, unlocked, display_order
        ) SELECT 'recipe-' || id || '-lockpick-set', id, 'Lockpick Set',
                 'Shape narrow iron scraps into a matched set of lockpicks.',
                 'Crafting', 38, 'Lockpick', 3, 'common', 30,
                 'Flint & Steel', 1, 1, 2
          FROM campaigns;

        INSERT OR IGNORE INTO crafting_recipe_ingredients(id, recipe_id, item_name, quantity, display_order)
        SELECT 'ingredient-' || id || '-bandages-cloth',
               'recipe-' || id || '-field-bandages', 'Cloth', 2, 0 FROM campaigns;
        INSERT OR IGNORE INTO crafting_recipe_ingredients(id, recipe_id, item_name, quantity, display_order)
        SELECT 'ingredient-' || id || '-potion-herbs',
               'recipe-' || id || '-health-potion', 'Herbs', 2, 0 FROM campaigns;
        INSERT OR IGNORE INTO crafting_recipe_ingredients(id, recipe_id, item_name, quantity, display_order)
        SELECT 'ingredient-' || id || '-potion-water',
               'recipe-' || id || '-health-potion', 'Water Flask', 1, 1 FROM campaigns;
        INSERT OR IGNORE INTO crafting_recipe_ingredients(id, recipe_id, item_name, quantity, display_order)
        SELECT 'ingredient-' || id || '-lockpick-iron',
               'recipe-' || id || '-lockpick-set', 'Iron Scraps', 2, 0 FROM campaigns;

        INSERT OR IGNORE INTO inventory_items(
            id, character_id, slot_index, inventory_position, name, quantity,
            rarity, description, item_type
        ) SELECT 'item-demo-cloth', id,
                 COALESCE((SELECT MAX(slot_index) + 1 FROM inventory_items WHERE character_id = characters.id), 0),
                 (WITH RECURSIVE slots(n) AS (SELECT 0 UNION ALL SELECT n + 1 FROM slots WHERE n < 39)
                  SELECT MIN(n) FROM slots WHERE n NOT IN (
                      SELECT inventory_position FROM inventory_items
                      WHERE character_id = characters.id AND inventory_position IS NOT NULL
                  )),
                 'Cloth', 4, 'common', 'Clean cloth suitable for crafting.', 'misc'
          FROM characters WHERE campaign_id = 'campaign-greystone' AND is_player = 1;
        INSERT OR IGNORE INTO inventory_items(
            id, character_id, slot_index, inventory_position, name, quantity,
            rarity, description, item_type
        ) SELECT 'item-demo-herbs', id,
                 COALESCE((SELECT MAX(slot_index) + 1 FROM inventory_items WHERE character_id = characters.id), 0),
                 (WITH RECURSIVE slots(n) AS (SELECT 0 UNION ALL SELECT n + 1 FROM slots WHERE n < 39)
                  SELECT MIN(n) FROM slots WHERE n NOT IN (
                      SELECT inventory_position FROM inventory_items
                      WHERE character_id = characters.id AND inventory_position IS NOT NULL
                  )),
                 'Herbs', 4, 'common', 'Medicinal herbs gathered for crafting.', 'misc'
          FROM characters WHERE campaign_id = 'campaign-greystone' AND is_player = 1;
        INSERT OR IGNORE INTO inventory_items(
            id, character_id, slot_index, inventory_position, name, quantity,
            rarity, description, item_type
        ) SELECT 'item-demo-iron-scraps', id,
                 COALESCE((SELECT MAX(slot_index) + 1 FROM inventory_items WHERE character_id = characters.id), 0),
                 (WITH RECURSIVE slots(n) AS (SELECT 0 UNION ALL SELECT n + 1 FROM slots WHERE n < 39)
                  SELECT MIN(n) FROM slots WHERE n NOT IN (
                      SELECT inventory_position FROM inventory_items
                      WHERE character_id = characters.id AND inventory_position IS NOT NULL
                  )),
                 'Iron Scraps', 4, 'common', 'Small iron pieces ready to be reshaped.', 'misc'
          FROM characters WHERE campaign_id = 'campaign-greystone' AND is_player = 1;
        INSERT OR IGNORE INTO inventory_items(
            id, character_id, slot_index, inventory_position, name, quantity,
            rarity, description, item_type, charges, maximum_charges
        ) SELECT 'item-demo-healers-kit', id,
                 COALESCE((SELECT MAX(slot_index) + 1 FROM inventory_items WHERE character_id = characters.id), 0),
                 (WITH RECURSIVE slots(n) AS (SELECT 0 UNION ALL SELECT n + 1 FROM slots WHERE n < 39)
                  SELECT MIN(n) FROM slots WHERE n NOT IN (
                      SELECT inventory_position FROM inventory_items
                      WHERE character_id = characters.id AND inventory_position IS NOT NULL
                  )),
                 'Healer''s Kit', 1, 'common',
                 'A compact kit used to prepare medicines and dress wounds.',
                 'charged', 5, 5
          FROM characters WHERE campaign_id = 'campaign-greystone' AND is_player = 1;
        """,
    ),
    (
        18,
        """
        UPDATE inventory_items
        SET inventory_position = inventory_position + 1000000
        WHERE inventory_position IS NOT NULL;

        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY character_id
                       ORDER BY inventory_position, slot_index, id
                   ) - 1 AS compact_position
            FROM inventory_items
            WHERE inventory_position IS NOT NULL
        )
        UPDATE inventory_items
        SET inventory_position = (
            SELECT compact_position FROM ranked WHERE ranked.id = inventory_items.id
        )
        WHERE inventory_position IS NOT NULL;

        UPDATE characters
        SET inventory_capacity = MAX(
            28,
            COALESCE((
                SELECT COUNT(*) FROM inventory_items
                WHERE character_id = characters.id
                  AND inventory_position IS NOT NULL
            ), 0)
        );
        """,
    ),
    (
        19,
        """
        UPDATE characters
        SET inventory_capacity = MAX(320, inventory_capacity);
        """,
    ),
    (
        20,
        """
        ALTER TABLE campaigns ADD COLUMN premise TEXT NOT NULL DEFAULT '';
        """,
    ),
    (
        21,
        """
        ALTER TABLE characters ADD COLUMN pending_ability_points INTEGER NOT NULL DEFAULT 0
            CHECK (pending_ability_points >= 0);
        ALTER TABLE quest_objectives ADD COLUMN completion_gate INTEGER NOT NULL DEFAULT 0
            CHECK (completion_gate IN (0, 1));

        UPDATE quest_objectives
        SET completion_gate = 1
        WHERE optional = 0
          AND quest_id LIKE '%-preset-quest-%'
          AND display_order = (
              SELECT MAX(candidate.display_order)
              FROM quest_objectives AS candidate
              WHERE candidate.quest_id = quest_objectives.quest_id
                AND candidate.optional = 0
          );

        UPDATE character_resources
        SET maximum_value = CASE (
            SELECT MIN(20, MAX(1, characters.level))
            FROM characters WHERE characters.id = character_resources.character_id
        )
            WHEN 1 THEN 300 WHEN 2 THEN 600 WHEN 3 THEN 1800
            WHEN 4 THEN 3800 WHEN 5 THEN 7500 WHEN 6 THEN 9000
            WHEN 7 THEN 11000 WHEN 8 THEN 14000 WHEN 9 THEN 16000
            WHEN 10 THEN 21000 WHEN 11 THEN 15000 WHEN 12 THEN 20000
            WHEN 13 THEN 20000 WHEN 14 THEN 25000 WHEN 15 THEN 30000
            WHEN 16 THEN 30000 WHEN 17 THEN 40000 WHEN 18 THEN 40000
            WHEN 19 THEN 50000 ELSE 1
        END
        WHERE resource_type = 'experience';
        """,
    ),
    (
        22,
        """
        ALTER TABLE narrative_messages
            ADD COLUMN speaker_npc_id TEXT REFERENCES npcs(id) ON DELETE SET NULL;
        CREATE INDEX narrative_message_speaker ON narrative_messages(speaker_npc_id);
        """,
    ),
    (
        23,
        """
        CREATE TABLE turn_notes (
            id INTEGER PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            turn_number INTEGER NOT NULL CHECK (turn_number >= 0),
            kind TEXT NOT NULL CHECK (
                kind IN ('xp', 'item', 'quest', 'relationship', 'travel', 'resource', 'other')
            ),
            text TEXT NOT NULL CHECK (length(trim(text)) > 0)
        );
        CREATE INDEX turn_note_order ON turn_notes(campaign_id, turn_number, id);
        """,
    ),
)


LATEST_SCHEMA_VERSION = MIGRATIONS[-1][0]


def apply_migrations(connection: sqlite3.Connection) -> int:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    applied = {
        int(row[0])
        for row in connection.execute("SELECT version FROM schema_migrations")
    }
    for version, sql in MIGRATIONS:
        if version in applied:
            continue
        try:
            connection.executescript(
                "BEGIN IMMEDIATE;\n"
                + sql
                + f"\nINSERT INTO schema_migrations(version) VALUES ({version});\n"
                + "COMMIT;"
            )
        except sqlite3.Error:
            connection.rollback()
            raise
    from dd_simulator.state.item_actions import (
        backfill_item_metadata,
        recalculate_character_item_totals,
    )
    from dd_simulator.state.item_catalog import ensure_catalog_merchant_stock

    backfill_item_metadata(connection)
    ensure_catalog_merchant_stock(connection)
    character_ids = connection.execute("SELECT id FROM characters").fetchall()
    for row in character_ids:
        recalculate_character_item_totals(connection, str(row["id"]))
    return LATEST_SCHEMA_VERSION
