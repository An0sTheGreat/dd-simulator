# Release History

Per-release behavior notes moved from `README.md` on 2026-10-27. Release and canonical
Workflow Step numbering is explained in `WORKFLOW_STATUS.md`.

## Release 28 behavior

Package version 0.28.0, database schema 24. The Adventure dashboard is the Concept T layout.

- **Left column:** a character strip (vitals, experience), the paperdoll with nine equipment
  slots, a skill list with descriptions, a scrolling 5 x 5 Inventory card holding up to
  320 slots, and an Abilities & Spells card with a Short Rest button.
- **Right column:** navigation tabs over the location art, a quest or encounter card (the
  encounter card has a target picker when two or more enemies are active), a conversation
  that fades into the scene with per-turn update tags and scroll-back history, and a 2 x 3
  choice grid.
- **Journal page** (quest list, event log, recent events) and **crafting** from the
  Character Sheet.
- **Shared tooltip cards** for items (with equipped comparison), abilities, spells and
  skills; painted skill and ability icons.
- **Schemas 22-24:** message speakers, per-turn notes, and the note's message sequence.
- Packaged check: `--smoke-test-release28`.

Character Sheet data, semantic icons, resource bars, and live splitters.

## Current inventory and equipment presentation

- Inventory pages contain 36 square artwork-backed wells: 6 x 6 at normal width and
  4 x 9 with vertical scrolling when the utility panel is narrow. Wells are fixed at
  96 pixels and semantic item artwork is fixed at 68 pixels.
- The supplied slot artwork is cropped to its visible edge and tiled without gaps.
  Its authored PNG colors are preserved unchanged in both supported themes.
- Equipment uses the supplied centered 3 x 3 board in this order: Ring, Head, Neck;
  Main Hand, Body, Off Hand; Hands, Ammunition, Feet. The board is capped at the exact
  720-pixel (9x source) grid within its 735-pixel layout maximum;
  its 100-pixel maximum targets and 68-pixel maximum icons shrink together when needed.
  An occupied target replaces only its matching silhouette with the supplied slot art.
- Item wells no longer use rarity outlines. Rarity instead colors the hover-card border
  and title. Stack badges, paging, drag/drop, and deterministic Auto-Sort by Default,
  Rarity, Type, or Value remain application-owned. Schema 19 is unchanged.

## Release 26.6 behavior

- Character Sheet occupies the footer slot beside People and presents identity,
  attributes, combat values, saves, attacks, abilities, skills, possessions, and
  currency in a centered, theme-aware surface no wider than three fifths of the page.
- Item hover cards use rarity-specific supplied card ornament, larger semantic art,
  two-column mechanics, readable effect summaries, and italic descriptions. Combat
  ability/spell cards use the same interaction and always list authoritative mechanics.
- Default uses an optimized 3840-pixel runtime copy of the supplied background and
  selected card UI artwork without modifying source resources.
- Each inventory page contains 32 circular wells. Seven columns expose the full page at
  1600 x 900; narrower sidebars switch to four columns and vertical scrolling.
- The minimap uses an actual open-center compass overlay behind its live edge labels.
  The custom main title bar delegates dragging to Windows for top-edge maximize,
  side-edge snap, drag restore, and double-click maximize/restore.

## Release 26.5 behavior

- Inventory uses 32 circular wells per page in an eight-row, four-column grid. Page
  controls appear at the section's top-right only when occupied items exceed one page.
- Schema 19 raises storage reserve to 320 positions while the projection exposes only
  occupied 32-slot pages, avoiding empty-page clutter and preserving saved items.
- Default uses the supplied `Project Resources/background2.png` through an optimized
  runtime copy; the source asset and `dnd_ui_source` remain unchanged.
- The rectangular minimap ornament remains visible at every size. Item hover cards use
  the same corner-and-rail ornament language.
- Player skills, combat abilities, and common named items receive distinct curated
  semantic icons without preventing higher-rarity items from selecting higher tiers.

## Release 26.4 behavior

- Dragging an inventory or equipped item now carries only its transparent SVG artwork.
- Inventory keeps all 28 full-size circular slots visible without a scroll container;
  Equipment occupies a separate 5-column tab immediately to its right.
- The Default surface repeats at 96 pixels, and the minimap uses a rectangular ornate
  frame with north, south, destination, and current-location labels anchored by layout.

## Release 26.3 behavior

- The Default stone surface is a compact seamless tile instead of a stretched image.
- The frameless main window and application dialogs use centered, draggable themed title
  bars; modal dialogs dim and block the rest of the application until dismissed.
- Inventory and equipment use large circular icon wells. Item names and mechanics live
  in hover cards, rarity remains on the ring, and stacked quantities use corner badges.
- Inventory capacity is 28 visible slots. Schema 18 compacts existing bag positions and
  preserves legacy overflow rather than discarding items.
- High Fantasy and Modern Dark display as **Modern Fantasy Simple** and
  **Modern Dark Simple** while retaining their stable saved-preference IDs.

## Release 26.2 behavior

- Translucent panel insets reveal the shared charcoal-stone texture without gradient
  banding or repeated per-panel image costs.
- The title owns its centered left/right ornament; resource bars use dark borders.
- Crafting, combat reward, quest reward, generated-option, travel, and camp dialogs use
  one movable frameless shell with a textured interior and application-owned title bar.

## Release 26.1 behavior

- Corrects the visual gap between the approved mockup and Release 26's initial texture
  pass with native nine-slice panel frames, restrained corner caps, ornamental divider
  grips, title flourishes, and an open-center compass overlay.
- Replaces broad brown leather fields with near-black inset surfaces and thinner aged-
  bronze controls while preserving item density, rarity colors, and every resizer.

## Release 26 behavior

- Default now layers purpose-built charcoal stone, dark leather, and hammered iron
  textures beneath its existing bronze frame language.
- Buttons, tabs, fields, list selections, scrollbars, and splitters use clearer carved,
  beveled, hover, pressed, selected, and disabled states.
- Resource bars keep their authoritative values and distinct fills but no longer show
  decorative icons. Existing item icons and rarity colors remain unchanged.
- Texture URLs are resolved relative to the theme directory at runtime, including from
  the packaged application. High Fantasy and Modern Dark assets remain untouched.
- Five 1920 x 1080 preview captures covered Adventure, Inventory, People, Settings, and
  Character Creation. `scripts/capture_previews.py` regenerates them under
  `artifacts/previews`; historical captures were removed in the 2026-10-27 cleanup.

## Release 25 behavior

- Item and generated-response hover cards are created only while hovered, preventing
  hidden top-level tooltip windows from appearing during launch and dashboard refreshes.
- Inventory and equipment cards keep a larger icon left of the existing text block;
  hover-card icons render at 64 pixels.
- The runtime renders the numbered semantic SVG matching the selected manifest record.
  Healing Potion uses `0919`, Greater Healing Potion `0918`, Minor Healing Vial `0920`,
  and arrows use an arrow record instead of an atlas crop.
- All 1,686 semantic records participate in one application-owned loot pool. Tier weights
  decrease from 100 to 35, 12, 4, and 1 for tiers zero through four. Combat, quests,
  merchants/bartering, and explicit search/open actions use that shared selector.
- Unsloth Studio receives only eight stable, scene-specific loot candidates per action. The
  application validates any discovery and derives its mechanics; the model only narrates.
- Narrative segments retain the semantic kind and punctuation supplied by the model.
  The application removes transport backticks but no longer splits passages or inserts quotes.
- Trade, barter, buy, purchase, and sell actions entered on Adventure open the present
  merchant in People and use its existing dialogue/trade flow. People dialogue is written
  into the shared twenty-message Adventure transcript.

## Release 24 behavior

- Fresh installations use the new **Default** theme. Existing saved theme choices remain
  unchanged, and the High Fantasy and Modern Dark theme files are untouched.
- Default follows the supplied dark-stone UI concept with layered bronze frames, warm
  parchment text, compact inset cards, themed controls, and the existing draggable
  splitters and saved panel sizes.
- Generated item visuals are resolved locally from the supplied 1,686-record semantic
  manifest. Name, item category, mechanics, slots, description, and rarity select a
  stable icon; rare and higher items prefer more elaborate visual tiers.
- One cached 16-pixel atlas supplies inventory, equipment, drag cards, hover cards,
  skills, resources, trade, crafting, rewards, and navigation. No LLM or image service
  participates in icon selection.
- Non-combat model prose now explicitly forbids Markdown and single-quote dialogue
  delimiters. The parser removes stray backticks, converts clear dialogue to ordinary
  double quotes, and separates mixed narration/dialogue before theme styling.
- SQLite transactions still commit each accepted action immediately. A file-backed
  quit/reopen regression verifies that Return to Adventure shows the last committed turn.
- Runtime asset terms and packaging notes are recorded in `docs/ASSET_CREDITS.md`.

## Release 23 behavior

- World & Safety is the first creation tab. **Randomize Campaign** makes one bounded
  Unsloth Studio request and fills every other tab while preserving those selections.
- The generated profile is accepted only when all required fields exist, age is valid,
  exactly three focus skills and one or two personality traits are supplied, and every
  class, ancestry, item, trait, motivation, and skill matches an application catalog.
- Campaign Name and Character Name each provide three selectable Unsloth Studio options.
  Appearance generation explicitly prioritizes world type, tone, starting region,
  content boundaries, and visual direction.
- Role & Skills now contains personality, strength, flaw, and motivation. Focus Skills
  uses eight buttons; choosing three disables the rest until a selected skill is removed.
- Every creation form uses a centered one-third-width column. World & Safety,
  Appearance, and Story use tighter vertical spacing. Schema version 17 is unchanged.

## Release 22 behavior

- Every player skill card uses its authoritative current and next-level XP in a thin
  progress bar. High Fantasy uses its gold accent; Modern Dark uses its blue accent.
- Dedicated Skills and Quests pages are removed because the same information already
  exists in Adventurer Tools and the adventure dashboard.
- Their footer positions, plus the former Campaigns position, remain disabled blank
  buttons so Map, People, and Settings do not move.
- Campaign management occupies the right half of Settings. New Campaign and Load
  Selected retain their existing behavior; cancelling creation returns to Settings.
- This is a presentation-only release. The Game-State Ledger remains schema version 17.

## Release 21 behavior

- Adventurer Tools now includes a themed Crafting tab with persistent recipes,
  ingredient ownership, tool requirements, skill targets, output previews, and clear
  unavailable reasons.
- Crafting is resolved deterministically from the player's Crafting skill, equipment
  bonuses, recipe difficulty, and campaign difficulty. Unsloth Studio does not choose the
  result or any mechanical value.
- Successful crafts consume ingredients and tool uses atomically, place the output in
  inventory, award Crafting XP, and write Event Log and audit records. Failed checks
  preserve materials and tools while awarding reduced practice XP.
- Each attempt creates a durable, theme-aware result popup. A second attempt is blocked
  until the current result is acknowledged, so a restart cannot silently lose it.
- The People page has a saved vertical splitter between Trade and conversation. Trade
  stays centered at approximately one third of the page width while conversation keeps
  the full available width below it.

## Release 20 behavior

- Present merchants expose persistent stock in the People tab. The player can buy,
  sell, or accept a deterministic barter quote after explicit confirmation.
- Prices use the item's authoritative value, rarity, durability, campaign difficulty,
  and NPC relationship. Unsloth Studio may phrase merchant dialogue but never chooses a
  price, moves an item, or changes currency.
- Each transaction atomically transfers one item, updates currency and carry totals,
  writes transaction and Event Log records, and participates in checkpoint checksums.
- Quest items, currency items, equipped items, unavailable merchants, full inventory,
  stale offers, and unaffordable purchases are rejected without partial changes.
- The People page centers its six responses, written response row, and Return to
  Adventure control in a responsive one-third-width footer. Return controls on Skills,
  Quests, Map, and Settings use the same centered treatment.

## Release 19 behavior

- Settings uses two invisible equal columns over one full-page themed surface. The
  scrollable controls remain in the left column; the right column stays empty.
- Models discovered through Unsloth Studio's `GET /v1/models` can be selected.
  **Load Selected Model** calls Unsloth's `POST /api/inference/load` management route
  asynchronously; success selects and saves the loaded model, refreshes status, and
  enables evaluation.
- Selecting a dropdown entry alone never loads a large model. Failed loads preserve
  the prior working selection and show the server error; manual loading in Unsloth
  Studio plus Refresh Models remains supported.
- Startup readiness reports source or packaged mode, configuration storage location,
  and active database schema. Database recovery behavior remains unchanged.

## Release 18 behavior

- Settings discovers models from the local Unsloth Studio server and distinguishes
  **Loaded and ready** models from installed models that still need to be loaded.
  Only loaded models can be selected or evaluated.
- The explicit model choice is saved separately from layout preferences and is used
  by character suggestions, adventure actions, combat narration, travel prose, and
  People dialogue through their shared client. Refresh rescans Unsloth Studio without
  loading or unloading models behind the user's back.
- A three-sample evaluator uses isolated Greystone fixtures and never reads or writes
  campaign state. It records strict JSON success, compatibility retries, latency,
  prompt/completion tokens, token rate, bounded continuity/authority quality checks,
  reported context, and reported model memory when available.
- The latest JSON and Markdown evaluation reports are written under
  `%APPDATA%\DnDSimulator\model-evaluations` (or `DDSIM_CONFIG_DIR` when set).
- Common, Uncommon, Rare, Epic, and Legendary items use theme-specific, high-contrast
  colors. The item's stored rarity now styles both inventory and equipped cards,
  hover details, and reward cards, and therefore follows equip/unequip, drag/drop,
  auto-sort, save/load, and live theme changes.

## Release 17 behavior

- People-tab custom questions and all six suggested responses use the same loaded
  Unsloth Studio model selection as the main adventure resolver. The client prefers the
  model that Unsloth Studio's `GET /v1/models` marks as `loaded`, so settings from another
  installed model are not selected accidentally.
- NPC dialogue includes a bounded snapshot of the NPC profile, relationship,
  memories, recent conversation, player profile, current location, active quests,
  and content preferences. Malformed structured output retries once without strict
  response-format enforcement for Gemma-compatible JSON and accepted text output.
- Failed NPC generation commits no conversation or relationship change, preserves
  the written input, and shows an actionable themed error instead of silently
  persisting repetitive fallback dialogue.
- Schema version 15 adds named checkpoints, campaign state audits, replay checksums,
  and repair reports. Checkpoints include schema/current-scene/visual metadata and
  a verified SQLite backup; load creates a recovery backup before restoring the
  selected campaign and rebuilding every panel.
- Settings provides Create Checkpoint, Load Checkpoint, Inspect & Repair, and Verify
  Replay controls. Safe repair covers current-location visibility, inventory
  capacity, equipped/bag separation, and missing visual files. Unsafe discrepancies
  require restoration from a verified checkpoint.
- File-backed ledgers are backed up automatically before schema migration.

## Historical Release 16 behavior

- Equipped item cards show current/maximum durability. Equipped ammunition cards
  show their authoritative stack quantity and refresh with dashboard state.
- The Event Log has no expanding spacer after its final entry. It opens at the
  newest entry, follows the bottom when already current, and preserves an older
  reading position across action-driven dashboard refreshes.
- Schema version 14 adds versioned portrait, location, item, and scene assets;
  stable visual-state signatures; separate canonical and active selection;
  pending/confirmed/superseded/rejected/missing states; content hashes, reuse
  counters, and append-only visual history.
- File-backed campaigns store copied artwork under `visual_assets` beside the
  Game-State Ledger. Exact confirmed state matches take priority over the canonical
  fallback, so returning to a prior location state restores its exact stored image.
- Registry metadata preserves prompt and negative-prompt summaries, generation
  seeds, reference and attachment IDs, art/camera/lighting direction, and character
  appearance-lock facts. Character state signatures include current equipment;
  location signatures normalize ordinary weather/time changes and version material
  scene changes such as storms, structural condition, danger, route, or viewpoint.
- Confirmed portraits and location images render in both themes. Pending, missing,
  or unregistered states retain explicit safe placeholders and never display an
  unconfirmed image.

## Historical Release 15 behavior

- Release and canonical Workflow Step numbers are now separate and documented in
  `docs/WORKFLOW_STATUS.md`; the application header and package identify Release 15.
- The Skills page uses two equal parent regions. Player Skills vertically fill up
  to three fixed child columns on the left; Combat Abilities & Spells use the same
  behavior in three fixed child columns on the right.
- Inventory items drag into compatible equipment targets only. One-handed weapons
  may use Main Hand or Off Hand, while shields, armor, jewelry, ammunition, and
  other equipment are constrained to their configured slots. Replaced equipment
  returns to the dragged item's former inventory position atomically.
- Equipment still drags into a chosen empty inventory slot. All inventory and
  equipment drags retain the complete themed item card as visual feedback.
- Schema version 13 persistently records category, weight, value, identification,
  damage, armor, healing, compatible slots, requirements, bonuses, penalties, and
  item-generation difficulty/version. Legacy equipped-only records receive stable
  item identities without becoming visible in the bag.
- Newly materialized items use deterministic application-owned catalog rules based
  on identity, rarity, and campaign difficulty. Locally generated descriptions
  provide a fallback for every item; Unsloth Studio never determines mechanics.
- Hovering an inventory or equipment item opens a persistent themed information card
  beside the pointer. Its two-column table presents identity, condition, value,
  quantity, mechanics, status, and compatible slots, with an italic description
  below. It remains open for the full hover and closes on leave or interaction.
- Settings provides working Small, Default, and Large font-size choices. The choice
  scales each theme's typography hierarchy live, persists with UI preferences, and
  remains active when themes change. Equipment mutations immediately recalculate
  carry weight, armor, attack, and combined equipment bonuses.

## Historical Release 14 behavior

- People at the current location appear in the sidebar and on a dedicated,
  theme-aware conversation page with status, disposition, relationship score,
  portrait initials, a 20-message history, six immediate-send choices, and a
  written-response field.
- Social checks, relationship changes, memories, quest progress, reputation,
  and location/route reveals are deterministic and auditable. Unsloth Studio may
  phrase speech and monologue only after the application resolves those facts.
- Inventory capacity is 40 visible slots. Equipped records stay linked to their
  equipment slots but leave the bag until safely unequipped into a free slot.
- Inventory supports drag-to-move/swap, deterministic Auto-Sort, selection and
  scroll preservation, and nearby themed detail popouts.
- Equipped items can be dragged into a chosen empty bag slot to unequip them.
  Every inventory and equipment drag carries the themed item card under the cursor;
  equipped items remain outside the bag and Auto-Sort until deliberately unequipped.
- Combat abilities and spells are separated from general player skills in both
  Skills views, with costs, range, uses, cooldowns, effects, and availability.
- Suggested narrative responses submit immediately; event panels preserve their
  scroll position; all dashboard resize handles share one visual treatment while
  retaining their independent drag directions, limits, and saved positions.
- Every current location is discovered, visited, shown, and highlighted on the
  map after load, including story transitions to Greystone Keep.

## Phase 13 behavior

- The Map page displays discovered locations on fixed map coordinates and lets
  the player inspect direct known routes from the current location.
- Route confirmation shows distance, duration, stamina cost, danger, status,
  requirements, and the possibility of an arrival encounter.
- Travel validates discovery, direction, route state, active combat, and stamina
  before atomically advancing time, changing location, recording history,
  progressing travel objectives, and appending narrative and events.
- Blocked, locked, hidden, and unavailable routes cannot be bypassed by free-form
  Unsloth Studio actions. Destination changes must use the Map travel transaction.
- Deterministic danger checks can start an existing generated encounter on arrival,
  with the encounter linked back to durable travel history.
- Four- and eight-hour camp actions are available only at permitted locations.
  Camping advances the clock, recovers bounded resources, checks quest deadlines,
  and records camp history; eight hours also resets limited uses and cooldowns.
- Optional Unsloth Studio travel and camp prose runs off the UI thread and outside the
  write transaction. Local code owns every route, cost, clock, recovery, quest,
  danger, encounter, and persistence decision, with deterministic prose fallback.

## Phase 12 behavior

- Quests persist rumored, active, completed, failed, and abandoned lifecycle states.
- Combat, travel, item collection/use/examination, dialogue, and bounded custom
  events automatically advance matching objectives; Unsloth Studio never calculates progress.
- Campaign-clock deadlines fail overdue quests deterministically, and completed
  quests can activate configured follow-ups.
- XP, currency, faction reputation, and item rewards are recorded once. Item
  rewards remain individually claimable if inventory capacity is temporarily full.
- Quest completion opens a theme-aware reward popup. Acknowledgement hides the
  popup without deleting the reward audit record.
- The compact Quest page follows the Skills-page density. Clicking an active,
  rumored, failed, or abandoned quest expands its objectives inline; completed
  quests are gray, collapsed, and cannot reveal their objectives.
- Quest cards fill vertically before creating up to six equal-width columns.

- The main window starts at 1600x900 and supports a 1280x720 minimum.
- The right utility sidebar retains a 360-pixel minimum width.
- Modern Fantasy Simple and Modern Dark Simple use the same widgets and layout. Modern Dark Simple
  replaces the former light Modern Proof palette while keeping its clean geometry.
- The selected theme, splitter positions, active tabs, event filter, and last
  navigation page are saved in the user's application-data directory.
- Invalid or missing theme preferences fall back to Modern Fantasy Simple.
- Reusable panels present a player summary, location, narrative, objectives,
  event history, minimap placeholder, resources, skills, equipment, and a
  28-slot inventory.
- Runtime values come from immutable SQLite-backed projections; deterministic
  mock data remains available only for isolated UI tests and previews.
- Inventory items support quantities, rarity, durability, quest markers,
  selection, arrow-key navigation, context menus, tooltips, and empty slots.
  Equipment has matching selection and context-menu behavior.
- Use applies catalogued resource or status effects, decrements consumable
  stacks, charges, or durability only after validation succeeds, and retains
  exhausted reusable items at zero charges or durability.
- Equip and Unequip use stable inventory-item references. Legacy equipped items
  without an inventory row move into the first free slot when unequipped.
- Free-form Examine validates item ownership and provides bounded item details
  to narration without consuming or mutating the item. Equip proposals are
  limited to owned, unequipped items with configured equipment slots.
- Drop removes an entire stack after confirmation, rejects quest or equipped
  items, and never performs a partial write.
- Successful inventory mutations refresh every visible projection and append a
  recent inventory event. Failed mutations preserve resources, items, equipment,
  and event history.
- Sending a free-form non-combat action builds a fresh bounded snapshot containing
  only the current scene, player resources, inventory/equipment, active objectives,
  known locations, preferences, and eight recent events.
- Unsloth Studio returns ordered narrative, monologue, and spoken segments, up to
  twelve typed state proposals, quest notes, and exactly six suggested actions
  through a strict JSON schema. Common safe
  JSON wrappers are accepted and malformed turns receive one format-only retry.
- Deterministic code validates stable target ownership and permits only bounded
  resource spending/restoration, existing item commands, known-location movement,
  active-objective completion, and time advancement. Active encounters route
  exclusively through the Combat tab so freeform input cannot bypass mechanics.
- Combat persists encounters, combatants, initiative, round/current turn, health,
  armor, distance, movement, weapon range, cover, conditions, morale, declared
  intent, and an append-only mechanical turn log in SQLite.
- The Combat tab offers Attack, Advance, Defend, Use Potion, Negotiate, and Flee alongside
  contextual non-editable Class Ability and Spell selectors. Every selectable
  class receives four initial actions; unavailable choices explain resource,
  cooldown, use, equipment, range, or health restrictions.
- Deterministic effects cover weapon and spell attacks, saving throws, direct
  and area damage, healing, armor/attack buffs, lasting conditions, and round-based damage.
  Mana, spell slots, stamina, focus, resolve, limited uses, and cooldowns persist.
- Short Rest is available outside active encounters and restores spell slots,
  limited uses, cooldowns, and part of missing health and combat resources.
- Attack rolls, critical hits, armor, damage dice, stamina costs, healing,
  ammunition, durability, critical-health warnings, retreat, surrender, defeat,
  victory, character XP, skill XP, and level thresholds are application-owned.
- Unsloth Studio receives resolved mechanics plus an exact list of legal enemy intents.
  It may phrase a combat beat and select only from those intents; it cannot alter
  rolls, health, damage, items, resources, or conditions. Invalid model output
  falls back to deterministic intent and combat text.
- Combat messages share the latest-20 transcript. The player action, optional
  model prose, mechanical enemy turns, events, and resulting state commit in one
  transaction.
- Starting combat without an explicit test encounter deterministically creates a
  location-, difficulty-, level-, and campaign-aware encounter from the persistent
  enemy archetype catalog. Generated encounters present terrain, awareness,
  visible enemy capabilities, and Take Cover, Scout, or Charge preparation before
  normal initiative advances.
- Enemy archetypes persist abilities, tactics, morale, resistances,
  vulnerabilities, loot, and optional reinforcement metadata. Application code
  resolves all special attacks, conditions, damage modifiers, and reinforcements.
- Every resolved encounter receives exactly one persistent outcome/reward record.
  Victories apply character XP, Attack XP, and currency once, then present a
  theme-aware modal with individually claimable loot. Unclaimed items remain in
  the encounter ledger when inventory capacity is exhausted, and the modal is
  restored after restart until the player continues.
- The horizontal divider between Narrative/Quests and Event Log/Recent Events can
  be dragged vertically. Its position persists with the other UI preferences and
  survives dashboard refreshes.
- Event Log and Recent Events keep their normal typography when that divider is
  moved and expose independent vertical scrolling when their viewports become
  shorter than their content.
- A valid turn writes its state changes, narration, clock/turn number, audit row,
  and action event atomically. Any invalid proposal or database failure rolls the
  entire turn back.
- The action field displays progress without clearing the player's text. Cancel
  discards the generated outcome before commit; failure preserves the text and
  offers Retry.
- The narrative panel projects the latest 20 append-only player and response
  messages in chronological order and automatically scrolls to the newest entry.
  Player-facing suggestions never expose internal ledger IDs.
- Bottom navigation contains only focused Skills, Quests, Map, Settings, and
  Campaigns destinations. Profile, Inventory/Equipment, and Journal stay on the
  adventure dashboard instead of being duplicated as full-size pages.
- Player Summary now contains Health, Stamina, Focus, Resolve, Experience,
  currency, and carry weight in one compact panel. The standalone resource
  sidebar was removed, and the full Skills page uses fixed-height compact rows.
- The standalone Quests page reuses one expanded Quests & Objectives panel rather
  than duplicating a second quest pane. Quest records use compact 52-pixel rows,
  display at least ten at normal page height, and scroll when the list grows.
- Utility, objective, and event tabs switch visible content. Outside combat,
  suggested actions populate the player-action field and Send routes the action
  through the validated Phase 8 turn transaction.
- Semantic button roles provide distinct primary, navigation, destructive,
  hover, pressed, selected, focus, and disabled states in both themes.
- Settings can restore UI defaults. Future font-size, motion, and contrast
  controls are visibly disabled until their implementation phase.
- On first launch, a versioned SQLite database is created and seeded
  transactionally with the deterministic Greystone campaign.
- The dashboard is a read-only projection of stored rows through typed service
  and repository boundaries; widgets never issue SQL directly.
- SQLite foreign keys, constraints, rollback behavior, schema migrations, and
  integrity checks protect the Game-State Ledger.
- Campaign services can list, create, select, and load campaign records. New
  campaign shells remain inactive until a character-creation flow populates
  their required state.
- If the on-disk ledger cannot be opened, the original file is left untouched
  and the current session uses an in-memory recovery ledger with a visible
  warning.
- The campaign browser lists stored campaigns and loads a selected completed
  campaign without restarting the application.
- Character creation is divided into Identity, Appearance, Role & Skills,
  Equipment, Story, World & Safety, and Final Review sections on one dedicated
  application screen.
- Fixed-choice fields use non-editable, full-click dropdowns. Equipment uses
  curated dropdowns throughout. Focus skills use multi-selection, personality
  is capped at two selections, and prose fields remain multiline text boxes.
- Body and height, face and features, clothing style, biography, and backstory
  each have a theme-aware Randomize control. Requests run outside the UI thread,
  discover the loaded local model, and return exactly three selectable options.
- Biography and backstory prompts include the current character choices.
  Content preferences use a concise balanced profile when left blank.
- Unsloth Studio failures preserve the existing field value and present a clear
  local-server error without preventing manual character creation.
- Adult-age rules vary by ancestry. Required values, text limits, personality,
  and the three-skill allocation are validated before final confirmation.
- High Fantasy and Modern Dark style the entire campaign and creation flow and
  can be switched live from the shared header.
- Schema migration version 2 preserves Phase 5 databases while adding character
  identity, appearance, story, world, safety, and visual-direction fields.
- Schema migration version 3 preserves existing campaigns while adding item
  types, consumable flags, charges, equip targets, deterministic use effects,
  and equipment-to-inventory references.
- Schema migration version 4 adds minute/turn tracking and append-only structured
  action-turn audit records while preserving schema-v3 campaigns.
- Schema migration version 5 stores the submitted player action plus ordered
  narrative, monologue, and spoken response segments.
- Schema migration version 6 adds append-only narrative messages and backfills
  prior action turns as player/response message pairs.
- Schema migration version 7 expands transcript kinds for combat/system messages
  and adds encounters, combatants, combat conditions, and combat turns while
  preserving version-6 transcript rows.
- Schema migration version 8 extends abilities with stable catalog keys, action
  kind, spell-slot cost, limited uses, cooldown state, and display order; combat
  conditions gain periodic effects and combat turns gain action-key/healing audit
  fields while preserving version-7 encounters.
- Schema migration version 9 adds persistent enemy archetypes, generated encounter
  context and preparation state, enemy tactical traits, reinforcements, and
  idempotent encounter rewards with separately claimable item rows.
- A completed creation writes the campaign, character, starting equipment,
  initial resources, skills, quest, location, narrative, event, and active
  campaign selection in one transaction. Any failure rolls everything back.
- High Fantasy prefers the Georgia serif family available on supported Windows
  systems; Modern Dark uses bundled Bitstream Vera Sans for deterministic
  packaged and headless rendering.
- Theme manifests include stable asset tokens. Missing artwork falls back to
  the default theme or the widget's QSS presentation without breaking startup.

## Architecture boundary

SQLite is the authoritative Game-State Ledger. Unsloth Studio is stateless and used
for optional character writing, bounded non-combat narration/proposals, and
constrained combat narration/intent. It cannot calculate or commit mechanics.
Opening factual UI panels does not call the model.

Initial character-image approval remains reserved for the future Visual
Registry phase; no character image becomes canonical in Phase 11.

See `docs/GAME_STATE_LEDGER.md`, `docs/UNSLOTH.md`, `docs/DECISIONS.md`, and
`docs/RESOURCE_MAP.md` for implementation and intake records.

## Release 26.9.1 interaction maintenance

- Free-form player text can address known local people but cannot insert a new NPC. NPC
  discovery remains owned by saved campaign, travel, quest, and encounter state.
- The People page keeps the active NPC selected after dialogue refresh instead of returning
  to the first person in the list.
- Newly committed player/response pairs receive a three-second emphasis in Narrative &
  Player Action and People; reduced-motion mode uses a static cue.
- Preset campaigns keep their badge in campaign selection, but the in-game title contains
  only the campaign name.
- Inventory/equipment quantity presentation and the title-bar Theme/window controls retain
  fixed sizing while narrative, page, and tooltip text follows the global font percentage.
- The packaged deterministic location catalog now includes Mountain and Swamp variants,
  bringing the current runtime catalog to 95 images.

## Release 26.9 behavior

- Character Creation now uses four tabs: Local AI Model Selection, Character Sheet,
  Campaign, and Final Review. The editable sheet reuses the live sheet's identity,
  ability-card, three-column, equipment, and themed scrolling presentation.
- Ability scores use the standard 27-point D&D 5E point-buy table, start at 8, stop at
  15, and must spend the full budget. The sheet shows live modifiers and points left.
- Supported classes use their D&D 5E hit dice and expose hover details for role, primary
  abilities, saving throws, proficiencies, and Constitution-adjusted level-1 HP.
- New characters begin with 100 gold. Level-1 HP equals the class hit-die maximum plus
  Constitution modifier, with a minimum of 1.
- The read-only Character Sheet now includes appearance, biography/backstory, role,
  equipped items, skills, abilities, possessions, and current currency from live state.
- The former minimap panel now shows the active location artwork, filling and rescaling
  with its sidebar splitter while preserving aspect ratio. Location Summary contains only
  state details. Campaign selection includes confirmed deletion with cascading ledger
  cleanup and safe active-campaign replacement.
- Settings uses minus/plus font scaling from 75% to 150%. Each themed font retains its
  original relative size, while inherited Qt text scales with the same percentage.
- First-run setup recommends Qwen3-4B Q4_K_M (2.5 GB) and suggests Gemma 4 E4B
  Uncensored HauhauCS Aggressive Q8 K P through Unsloth Studio.
- Database schema 20 is unchanged.

## Release 27 behavior

- A shared presentation-boundary sanitizer removes code fences, Markdown emphasis,
  headings, links, simple HTML tags, and control characters from model-authored names,
  narration, dialogue, travel, combat, and generated options before display.
- Ordered quest objectives can no longer be skipped. Important confrontations and other
  gated objectives require prior required objectives plus an explicit resolved action;
  travel, combat, and item gates must arrive through their deterministic state systems.
- First-run Local AI Setup now explains storage, hardware, and evaluation expectations.
  Settings exposes model architecture, quantization, context, and loaded-memory metadata,
  includes a concise recovery sequence, and exports application/runtime/evaluation logs
  without campaign or preference data.
- Deadly difficulty now affects merchant pricing and social-check targets in addition to
  its existing encounter, crafting, reward, and item-generation effects.
- Key setup, settings, motion, status, and diagnostic controls have explicit accessibility
  names and keyboard-focus coverage. Database schema 21 is unchanged.

## Release 26.9.4 behavior

- The sole packaged preset is now **The Last Orrery of Sol**, an original level 1–5
  science-fantasy campaign with five chained milestone quests across Earth, Luna, Mars,
  Europa, and Mercury. It includes authored locations, routes, NPCs, opening context,
  objective gates, rewards, unlocks, and finale constraints.
- All application/runtime material for the retired Crown Beneath the Furrows preset was
  removed. Its source PDF remains only as a historical project resource.
- Preset opening suggestions, weather, relationship notes, and initial events are now
  data-driven instead of inheriting campaign-specific Brindlewatch values.
- Gameplay now requires a configured local AI model. The ineffective non-AI action path
  and its setup option were removed; obsolete setup preferences return to Local AI Setup.
- Automated preset validation covers closed references, opening data, all five quest
  transitions, level 1–5 progression, currency, and signature reward persistence.
- Database schema 21 is unchanged.

## Release 26.9.3 behavior

- Character advancement now uses fixed levels 1-20 and standard cumulative experience
  thresholds. Combat and quest rewards share one idempotent award path, so the experience
  bar, character level, maximum HP, proficiency bonus, spell resources, and unlocks update
  together and survive autosave/reload.
- Level gains add the fixed class hit-die average plus Constitution modifier to maximum and
  current HP. Proficiency increases at levels 5, 9, 13, and 17 and applies to attacks, spell
  attacks, and class-proficient saving throws shown on the Character Sheet.
- Ability-score improvements occur at the standard class levels, including Fighter and Rogue
  extras. A themed level-up dialog requires every pending point to be assigned, caps scores
  at 20, and retroactively adjusts HP when Constitution's modifier rises.
- Class abilities and original spell features unlock by level. Caster resources scale with
  class and level; cantrips require no mana or spell slot and add a damage die at levels 5,
  11, and 17.
- Preset and generated quests mark their final required objective as a completion gate.
  Investigation, preparation, or uncertain wording can no longer finish a mission; a clearly
  resolved outcome is required. Level-one experience now displays against 300 XP instead of
  appearing to vanish through the former 100-XP rollover.
- Database schema 21 adds pending ability-score points and quest completion gates.

## Release 26.9.2 behavior

- Explicit attacks and combat preparation begin an encounter without waiting for freeform
  narration to infer combat. Dialogue and combat skill checks show a themed transient result
  with the roll, modifier, total, target, and success/failure state.
- The newest player action and resolved response fade smoothly over three seconds. Reduced
  motion keeps the existing static emphasis.
- Explicit pickups and direct gifts become persistent inventory entries, stack when possible,
  receive semantic item metadata/icons, and update the event and quest ledgers atomically.
- Integer-like model resource amounts are normalized before validation. Gemma 4 E4B Uncensored
  HauhauCS Aggressive Q8 K P replaces GPT-OSS-20B as the secondary Unsloth Studio recommendation.
- Database schema 20 is unchanged.

## Release 26.8.3 behavior

- Campaign generation preserves an existing campaign name and accepts a labeled or
  unlabeled premise. Without an existing name, a short first line may supply the title.
- Generated prose entering Narrative & Player Action is capped at 125 total words across
  regular actions, combat, travel/camp, and synced dialogue. Campaign introductions have
  a separate 220-word maximum.
- Database schema 20 is unchanged.

## Release 26.8.2 behavior

- Biography and Backstory are one editable `Biography/Backstory` field and one bounded
  generator; persisted legacy backstory storage remains compatible.
- Body and Height options must contain explicit height and build details and may not
  substitute clothing, actions, scenery, or story prose.
- Campaign titles use three numbered plain-text choices. Full campaign generation uses
  labeled name and premise fields, with existing JSON variants retained as compatibility
  input. The model evaluation now probes these real Character Creation contracts.
- Custom was removed from the campaign Difficulty choices. Database schema 20 is unchanged.

## Release 26.8.1 behavior

- Cancelling a generated-option dialog leaves the field unchanged and the same Randomize
  control may be used again without limit.
- The shared option parser accepts three validated JSON strings, simple option objects,
  or three numbered/bulleted plain-text choices. Existing uniqueness, placeholder, word,
  and character limits still apply before the chooser is shown.
- Database schema 20 is unchanged.

## Release 26.8 behavior

- Character Creation begins with a required Local AI Model Selection tab. All later
  sections remain disabled until Unsloth Studio reports the selected model as loaded.
  Loading a model unloads other active models first (`POST /api/inference/unload`).
- Non-mechanical creation, campaign, name, and opening requests use plain JSON prompts
  with application-side parsing and validation instead of strict `response_format` schemas.
  Tool-call arguments are accepted when a model returns valid JSON there. Mechanical
  generation retains strict schemas but retries in plain-JSON compatibility mode after
  HTTP 400/422 or structured-response failures, then remembers that choice for
  the selected model during the session.
- Generated appearance fields are limited to 75 words; generated biography and backstory
  fields to 120 words. Players may write up to 4,000 characters in each field with a live
  counter. Campaign titles are normalized and limited to 12 words.
- Personality traits now use two-choice buttons with explanatory hover text. Focus skills
  and traits show an explicit check mark when selected. Starting equipment dropdowns
  expose deterministic mechanics in their item hover text.
- The five-step creation flow is fully renumbered. Final Review uses compact data tables
  and full-width wrapping narrative blocks, and Create Campaign remains disabled until
  the written-profile confirmation is checked.
- Database schema 20 is unchanged.

## Release 26.7 behavior

- The post-release cleanup removes the Default theme and every bundled Default-only
  asset. Modern Fantasy Simple is the startup and saved-preference fallback; Modern Dark
  Simple remains selectable. Both use opaque, bordered item-hover surfaces containing
  the complete icon, mechanics table, and description.

- The Default theme now uses the project-owner-supplied `background_dark.jpg` and a
  focused set of labeled Deep Dark Fantasy SVG panels, buttons, dividers, resource
  frames, scrollbars, and ornaments. Item and skill icons are unchanged.
- A vertical splitter between Minimap and Adventurer Tools is resizable and persisted
  with the existing dashboard splitters.
- Inventory uses at most six columns and keeps its existing paging/scroll fallback.
- Character Sheet Skills and Abilities & Spells remain top-aligned with compact spacing.
- Dragging the maximized custom title bar restores the normal window beneath the pointer
  before delegating movement and edge snapping to Windows.
- Primary, navigation, New Campaign, Begin Encounter, and Auto-Sort controls now use the
  same Deep Dark artwork in inactive, hover, pressed, selected, and disabled states; the
  superseded card-derived button rail is no longer packaged.
- Default-theme panel surfaces use approximately 75% opacity so the supplied background
  remains visible without reducing text contrast. Header ornaments are restored and the
  custom minimize, maximize, and close controls reserve enough height for complete frames.
- Item hover cards paint their rarity ornament on a transparent outer layer around one
  inset surface, keeping both mechanics and the italic description inside the visible
  frame without a rectangular black halo.

## Smoke-test switches

- Use **Change Local AI Setup** in Settings to switch modes or model locations later.

For automated packaging verification, the application accepts
`--smoke-test`; it initializes the real window and exits cleanly after a short
Qt event-loop cycle. `--smoke-test-character-creation` additionally fills the
packaged creation form, commits a campaign, reloads it from SQLite, verifies the
resulting dashboard, and exits with a failure code if any stage fails.
`--smoke-test-inventory-actions` uses a consumable through the packaged service,
reloads its quantity and inventory event, and verifies the atomic result.
`--smoke-test-action-resolution` commits a deterministic structured turn,
resource change, narration, audit row, and action event through the packaged app.
`--smoke-test-combat` completes a deterministic encounter and verifies initiative,
stamina, damage, victory, progression, and combat-transcript persistence.
`--smoke-test-abilities` casts a deterministic packaged spell and verifies its
class catalog, damage, mana, spell-slot, and combat-audit persistence.
`--smoke-test-phase11` verifies packaged enemy-catalog synchronization,
deterministic encounter generation, introduction context, and preparation state.
`--smoke-test-phase12` completes a deterministic quest, projects and claims its
reward, acknowledges the themed popup, and reloads the completed quest state.
`--smoke-test-phase13` travels a packaged route, reloads the world map and
travel history, returns to the starting location, and verifies camp recovery.
`--smoke-test-phase14` verifies 40-slot equipped-item separation, atomic item
movement and sort, NPC dialogue persistence, combat-skill projection, People
navigation, and Greystone Keep map repair.
`--smoke-test-release15` retains the Release 15 itemization checks on the current schema,
the two-parent Skills layout, compatible inventory-to-equipment dragging, and
safe return of replaced equipment to the source bag slot. Historical `phase`
smoke-test switches remain supported as compatibility aliases for their original
implementation batches.

`--smoke-test-release16` verifies schema version 15 compatibility, equipped durability and
ammunition quantity, the compact bottom-following Event Log, Visual Registry
staging and confirmation, state-matched projection, and packaged image rendering.

`--smoke-test-release17` creates and restores a named checkpoint, validates the
audit/checksum replay chain, applies a safe repair from a recovery backup, verifies
People dialogue persistence, and checks the Settings reliability controls.

`--smoke-test-release18` verifies the packaged explicit-model boundary, Settings
model controls, equipment rarity properties, and compiled rarity selectors without
requiring Unsloth Studio to be running.

`--smoke-test-release19` verifies isolated first-run database/storage readiness,
model selection controls, and the scrollable half-width Settings page without
loading a real model.

`--smoke-test-release20` buys an item from the roadside merchant through the packaged
ledger, verifies the currency debit and merchant stock, then checks the themed trade
panel and centered People, navigation, and Settings footers.

`--smoke-test-release21` crafts an available recipe through the packaged ledger,
verifies the persistent result and acknowledgement path, and checks the Crafting page,
the themed result popup, and the resizable one-third-width People trade region.

`--smoke-test-release22` verifies each player skill's packaged XP bar, the three
disabled navigation placeholders, removal of redundant destinations, and Campaign
management in Settings' right column.

`--smoke-test-release23` verifies the World & Safety-first creation flow, eight-button
focus-skill selection and reselection, centered compact forms, full-campaign generation
control, and individual Campaign/Character Name randomizers.

Historical smoke switches remain compatibility aliases. `--smoke-test-release26-8`
verifies both supported themes, opaque item-hover surfaces, six-column inventory,
