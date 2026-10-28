# Game-State Ledger

SQLite is the authoritative source for persistent Release 26.8.3 campaign facts.
The database is stored as `game_state.db` beside `preferences.json` in the
application configuration directory. The `DDSIM_CONFIG_DIR` environment
variable can redirect both files for development and testing.

## Boundaries

- UI widgets consume immutable presentation models and never execute SQL.
- `GameStateService` coordinates campaign selection and dashboard loading.
- `CampaignRepository` owns campaign metadata and active-campaign selection.
- `DashboardProjection` performs read-only row-to-presentation conversion.
- `GameStateDatabase` owns connections, migrations, transactions, foreign-key
  enforcement, timeouts, WAL mode, and integrity checks.
- Gameplay code must validate a complete typed change set before using
  the transaction boundary. The LLM must never write to SQLite directly.

## Schema versions

Version 1 defines campaign metadata and time; player characters,
attributes, resources, skills, abilities, and status effects; inventory and
equipment; quests and objectives; locations, NPCs, relationships, world facts,
and flags; plus narrative, event, and journal history. Primary keys are stable
text identifiers. Foreign keys use deliberate cascade or nulling behavior, and
checks reject invalid values such as negative quantities and multiple current
player/location records.

Applied versions are recorded in `schema_migrations`. Migrations are ordered,
append-only, and run within an immediate transaction.

Release 22 adds no schema migration. Skill progress bars read the existing
`current_xp` and `next_level_xp` values, and relocated Campaign controls continue to
use the existing service boundary. Version 17 was current for that release.

Release 23 also adds no migration. Generated campaign drafts remain in memory until
the user reviews, confirms, and submits the existing `CharacterCreationDraft`; only
then does the established atomic creation transaction write schema-version-17 state.

Version 18 compacts visible bag positions and sets normal inventory capacity to
28 slots. Existing campaigns with more than 28 visible stacks retain enough capacity
to avoid data loss; capacity returns to the normal bound as those stacks leave.

Version 19 raises persistent inventory reserve to 320 positions. The current presentation
projects a minimum of 36 positions and adds another 36-slot page only when the highest
occupied position requires it. This later presentation change needs no migration: no
inventory rows are discarded or renumbered. Default, rarity, type, and value sorting
reassign only visible bag positions in a single audited transaction; equipped rows are
excluded and stable source order resolves equal keys.

Version 22 adds nullable `narrative_messages.speaker_npc_id`, a foreign key to
`npcs(id)` with `ON DELETE SET NULL`. Existing transcript rows keep a NULL speaker.
People dialogue stores its NPC on the spoken line. Free-form turns may propose an
optional `speaker_id` on spoken segments; the application keeps it only when it names
an available NPC at the current location and otherwise stores NULL without rejecting
the turn. The dashboard projection exposes each message's turn number, speaker id,
speaker name, and the speaker's confirmed canonical Visual Registry portrait path.

Version 23 adds `turn_notes(campaign_id, turn_number, kind, text)`, short player-facing
tags (`xp`, `item`, `quest`, `relationship`, `travel`, `resource`, `other`) for the
turn that caused them. State helpers buffer notes in a connection-scoped TEMP table;
the flow that writes the turn's transcript messages (free-form action, combat, People
dialogue, travel, camp) moves them into `turn_notes` in the same transaction, and
notes from flows without a transcript message (panel item actions, trading, crafting)
are discarded. The dashboard projection returns the newest whole turns up to 40
messages plus `has_older_messages`, attaching each turn's notes to its last message;
`GameStateService.older_messages(campaign_id, before_turn, limit=40)` pages back.

Without a schema change, the dashboard projection also carries the Concept T character
data: skill descriptions from `SKILL_DESCRIPTIONS`, unlocked powers split into
`abilities` and `spells` by `action_kind` with a short `status_label`, every occupied
bag position in order (`inventory`, up to `inventory_capacity`, 320) beside the paged
`inventory_preview`, and `portrait_path`: the confirmed Visual Registry portrait, else
a codex portrait picked from the ancestry's pack by a hash of the character id, else
empty so the initials show.

Version 12 adds nullable visible inventory positions while retaining stable
legacy item keys, migrates equipped items out of the bag, doubles existing
capacity with a 40-slot minimum, and adds NPC status, availability, personality,
voice, faction, quest/discovery effects, bounded conversation history, and
important memories. Current locations are repaired as discovered and visited
when projected through the service.

Version 13 adds deterministic item category, weight, value, identification,
damage, armor, healing, compatible slots, requirements, bonuses, penalties,
generation difficulty/version, and character equipment-summary fields. Existing
items are backfilled by application-owned catalog rules; Unsloth Studio has no authority
over mechanical values.

Version 14 adds the Visual Registry. `visual_assets` stores versioned portrait,
location, item, and scene metadata; state signatures; copied relative paths;
content hashes and dimensions; pending/confirmed/superseded/rejected/missing state;
separate canonical and active flags; prompt/negative-prompt summaries; generation
seeds; reference and attachment IDs; art, camera, and lighting direction; character
appearance locks; and reuse counters. `visual_asset_history` preserves every stage,
confirmation, rejection, supersession, missing-file finding, and reuse decision.
Confirmed exact state matches resolve before canonical fallbacks; an exact pending
or missing visual projects a safe UI state without being treated as confirmed
artwork. A character may retain its confirmed canonical portrait while a separate
confirmed active-state portrait reflects current equipment.

Version 15 adds `campaign_checkpoints`, `campaign_state_audits`, and
`campaign_repair_reports`. A named checkpoint records its label, schema version,
current scene, active/canonical visual references, campaign checksum, audit sequence,
and a path-contained SQLite backup. Loading first validates SQLite integrity, exact
schema compatibility, metadata, and stored campaign checksum, then creates a recovery
backup, restores only the selected campaign inside one deferred-foreign-key
transaction, and rebuilds presentation state. File-backed databases also receive an
automatic pre-migration backup before any later numbered migration is applied.

Version 16 adds `merchant_stock` and `commerce_transactions`. Stock belongs to an NPC;
transaction history belongs to the campaign, merchant, and player. Buy, sell, and
barter operations validate location, availability, ownership, capacity, restrictions,
and currency before committing inventory, stock, wallet, carry totals, Event Log, and
audit changes together. Pricing is deterministic application code based on value,
rarity, condition, difficulty, and relationship.

Version 17 adds `crafting_recipes`, `crafting_recipe_ingredients`, and
`crafting_results`. Recipes persist their Crafting-skill target, required tool and
tool-use cost, output template, quantity, XP award, and deterministic quality rules.
Ingredients reference stable item names and required quantities. Each attempt records
its score, target, success, consumed materials/tool uses, output, XP, and acknowledgement
state. One unacknowledged result blocks another attempt. Successful transactions consume
requirements, create or stack the output, update carry totals, award skill progression,
and append Event Log/audit evidence atomically; failure preserves materials and tools.

Audited gameplay mutations record typed operation metadata plus before/after campaign
checksums. Replay verification walks that persisted checksum chain from a named
checkpoint and compares it with current authoritative state. Repair inspection records
evidence and proposed corrections; applicable repairs create a recovery backup before
correcting current-location visibility, invalid inventory capacity, equipped/bag
overlap, or unavailable confirmed visuals. Page corruption or an invalid player count
is never guessed at and instead requires checkpoint restoration.

Equipping accepts an optional destination equipment index. The transaction checks
ownership and the item's persisted compatible-slot allowlist before changing either
record. An occupied destination returns its prior item to the source inventory
position. Unequipping still requires a valid empty bag position. Both directions
recalculate carry weight, equipment armor, attack bonus, and combined bonuses before
commit; failure rolls back the complete move.

Version 2 adds creation-completion state, character identity, ancestry, age,
gender/pronouns, body and facial descriptions, clothing, background,
personality, strength, flaw, motivation, biography, and backstory. The
`campaign_preferences` table stores world type, tone, difficulty, content
boundaries, visual style, and camera style. Existing Phase 5 campaigns migrate
as complete and retain every prior row.

Version 3 adds item type, consumable state, current and maximum charges,
equipment targets, structured deterministic use effects, and stable references
from equipment slots to inventory rows. Existing equipment is linked by
character and item name where a matching inventory row exists. Legacy equipped
items without a match are preserved and receive an inventory row if unequipped.

Version 4 adds `minute_of_day` and `turn_number` to the campaign clock and an
append-only `action_turns` table. Each row stores the normalized player action,
committed narration, exact proposed-change JSON, quest notes, suggested actions,
and campaign turn number. Existing schema-v3 clocks receive a deterministic
minute value based on their stored period.

Version 5 adds `player_action` and `response_segments_json` to the current
narrative projection and typed response-segment JSON to each `action_turns`
audit row. Existing version-4 narrative rows remain readable through their
paragraph and dialogue fields until a new turn commits typed segments.

Version 6 adds append-only `narrative_messages`. Each message has a campaign,
turn, in-turn sequence, kind, and text. Existing action turns are backfilled as
player/response pairs. The dashboard reads the newest 20 messages and restores
them to chronological order; older ledger history remains stored.

Version 7 preserves the version-6 transcript while extending its kind constraint
with `combat` and `system`. It adds `combat_encounters`, `combatants`,
`combat_conditions`, and `combat_turns`. These tables persist active and resolved
encounters, initiative order, rounds, health, armor, distance, movement, range,
weapons, morale, declared intent, conditions, every visible roll, target number,
damage result, and outcome. A partial unique index permits only one active
encounter per campaign.

Version 8 extends `abilities` with stable action keys, ability/spell kind,
spell-slot cost, current/maximum uses, cooldown state, and display order.
`combat_conditions` gains damage/healing-per-round fields, and `combat_turns`
adds stable action keys plus healing audit values. Existing version-7 encounter
and turn rows are copied into the expanded constrained table without loss.

Version 9 adds `enemy_archetypes`, generated encounter introduction, terrain,
awareness, difficulty, preparation, and reinforcement fields, plus per-combatant
ability/resistance/vulnerability/tactics snapshots. `combat_rewards` guarantees
one outcome and progression award per encounter. `combat_reward_items` keeps each
loot claim independently durable, including unclaimed items blocked by capacity.

Version 10 adds quest lifecycle timestamps, typed objective triggers and counts,
clock deadlines, follow-up links, configured XP/currency/reputation/item rewards,
append-only quest updates, faction reputation, durable quest reward records, and
individually claimable quest reward items. Legacy `complete` status is normalized
to `completed`, and existing objective completion is preserved.

Version 11 extends locations with descriptions, biomes, discovery and visit state,
camp permissions, and map coordinates. `travel_routes` stores directed or
bidirectional distance, duration, stamina, danger, status, requirements, and
visibility. `travel_history` records every validated departure and arrival plus
linked encounters; `camp_history` records location, duration, clock origin, and
recovery narrative. Existing current locations are safely backfilled as discovered
and visited.

## Startup and recovery

The first startup creates the ledger and transactionally inserts the Greystone
demo campaign. Seeding is idempotent. An active campaign identifier is stored
in `app_settings`.

If SQLite rejects an existing file, the application does not rename, truncate,
or replace it. It logs the error, displays a warning, and creates a shared
in-memory recovery ledger for that application session. This recovery session
is intentionally nonpersistent.

## Current mutation boundary

Campaign metadata shells can be created and listed through the service API, but
cannot become active because they lack the state required for a dashboard. The
character-creation service validates a complete typed draft and creates the
campaign, character, initial equipment/resources/skills, opening quest,
location, narrative, event, preferences, and active selection in one
transaction. Phase 7 adds typed inventory commands. Use, Equip, Unequip, and
Drop validate the active player, slot, item rules, resources, status effects,
equipment state, quest protection, charges, and durability before committing.
Each successful command and its inventory event share one transaction; an
event-write or constraint failure rolls back the entire command. Free-form
action submission and broader rules resolution use separate typed mutation paths.

Phase 8 admits a bounded subset of non-combat proposals: spending or restoring
eligible resources by at most ten points, operating on owned inventory and
equipment through Phase 7 rules, examining owned items without mutation,
completing an existing active objective,
moving only to a known unblocked campaign location, and advancing time by at
most eight hours. Stable IDs and ownership are rechecked inside the transaction.
The current narrative, transcript messages, suggestions, clock, structured
audit, state deltas, and event append either commit together or roll back together.

Phase 9 adds `CombatService` as a deterministic transaction boundary. Encounter
creation snapshots legal player and enemy combat values. Each command validates
turn ownership, target, range, inventory, ammunition, resources, and current
encounter state before rolling. Player mechanics, bounded LM prose/intent,
automatic enemy turns, synchronized health, item exhaustion, durability,
conditions, progression, events, and transcript messages commit together.
Invalid range, missing ammunition, insufficient stamina, full-health healing,
or stale targets roll the entire command back. Resolved encounters remain
queryable and a running encounter resumes from its stored round/current index.

Phase 10 routes catalogued abilities and spells through the same transaction.
Class ownership, target, range, health state, resource cost, spell slots,
limited uses, and cooldown are validated before any roll or write. Direct,
area, healing, buff, condition, saving-throw, and periodic effects are application-owned and
audited. Round transitions decrement effects and cooldowns. Short Rest is
rejected during active combat and atomically recovers bounded resources, spell
slots, limited uses, and cooldown state outside combat.

Phase 11 generates encounters from ledger facts before copying the selected
archetypes into combatant snapshots. Preparation, negotiation, enemy special
abilities, resistance/vulnerability modifiers, reinforcements, encounter outcome,
progression, currency, and reward rows stay inside the combat transaction.
Claiming loot is a later validated inventory transaction, so closing the popup or
running out of capacity cannot lose an award. Acknowledgement only suppresses the
pending popup; it does not delete its audit record.

Phase 12 keeps quest mechanics inside the same deterministic boundary. Validated
combat, movement, inventory, dialogue, and custom-action events match explicit
objective triggers and update counts within their caller's transaction. Clock
advancement checks deadlines. Completion creates one reward record, applies
progression once, activates a configured rumored follow-up, and collapses the
completed quest. Reward claims validate inventory capacity in a later transaction;
acknowledgement suppresses the popup but retains the audit rows.

Phase 13 makes Map travel the sole destination-changing transaction. Route
direction, discovery, status, stamina, active combat, destination ownership, clock,
quest deadlines, and encounter danger are locally validated. Location, clock,
stamina, quest progress, travel history, transcript, and event writes commit
together. A later generated-encounter transaction is linked back to the durable
journey row. Camping uses its own validated transaction and never runs during
combat or at a location that forbids camp.

Phase 6.1 character randomization does not cross this mutation boundary. Unsloth
Studio receives only a bounded copy of the current creation draft and returns
three text suggestions. A suggestion changes an in-memory form field only after
the user selects it; the normal validation and final transaction remain the
sole persistence path. Empty content preferences are normalized to the balanced
default profile before persistence.

Schema 20 adds the authoritative campaign premise. Character creation requires the
editable World & Safety premise, stores it on the campaign, uses it for the starting
location and opening transcript, and includes it in every bounded action context sent
to Unsloth Studio. The normal creation transaction and autosave path remain the sole
persistence boundary.
