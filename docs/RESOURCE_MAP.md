# Project Resource Map

All files in `X:\D&D Simulator\Project Resources` were inventoried and
structurally inspected before implementation.

## Authoritative resources

- `Main instructions.docx`: gameplay behavior, instruction routing, character
  creation order, formatting, commands, progress bars, continuity, and the
  opening flow.
- `Adventure Reference Guide.docx`: complete Game-State Ledger fields,
  detailed character creation, menus, inventory, equipment, progression,
  checks, combat, quests, NPCs, economy, time, maps, visual continuity, and
  save/repair rules.
- Application Architecture and Setup Guide (`.docx`; its original filename still names
  the former local-model server):
  Python/PySide6/SQLite architecture, bounded context construction, Unsloth Studio
  API boundary, typed state-change validation, transactions, memory, testing,
  and packaging guidance.
- `D&D_Simulator_Simple_ChatGPT_Project_Workflow.docx`: ordered build workflow,
  acceptance checks, completion record, and scope-control rules.
- `D&D SIMULATOR — APPLICATION UI IMPLEMENTATION INSTRUCTIONS.docx`: approved
  Version 1 layout, reusable widget structure, mandatory multi-theme design,
  token system, accessibility, responsive behavior, tests, and the UI Phase 1
  assignment.
- `Version 1.png`: 1536x1024 approved UI reference showing a dense high-fantasy
  dashboard with character summary, narrative/action area, objectives, event
  log, recent timeline, minimap, skills, inventory, and persistent navigation.

## Implementation constraints carried forward

- Release identifiers describe packaged implementation batches; Workflow Step
  identifiers preserve the canonical resource sequence. The current mapping is
  recorded in `WORKFLOW_STATUS.md`.

- SQLite, not the LLM or visible narration, owns factual game state.
- UI panels display service data without LLM calls.
- Model-proposed changes must be structured, enumerated, validated, and
  committed atomically.
- Layout, widget logic, theme tokens, theme QSS, theme assets, campaign artwork,
  and user preferences remain separate.
- Theme styling is not hard-coded into widgets.
- The application must remain readable, keyboard-accessible, high-DPI aware,
  and usable at approximately 1280x720.
- Existing visual assets must be reused exactly when the Visual Registry says a
  valid state-matched asset exists.
- Release 16 implements Workflow Step 16 with campaign-local asset folders,
  canonical and active-state character portraits, versioned location/item/scene
  visuals, deterministic state signatures, generation/reference metadata,
  appearance locks, append-only history, exact-match reuse, pending confirmation,
  and explicit missing/unregistered placeholders. No model-generated mechanics or
  automatic artwork approval is introduced.
- Release 17 implements Workflow Step 17 with named SQLite checkpoints,
  schema/current-scene/visual metadata, path-contained recovery backups, campaign
  checksums, append-only mutation audits, evidence-first safe repairs, and replay
  chain validation. Loading and repair remain application-owned operations; the LLM
  cannot choose or execute a correction.
- Release 18 implements Workflow Step 18 with local model discovery, explicit
  loaded-instance selection, isolated schema/latency/token/quality probes, persisted
  evaluation reports, and bounded configuration guidance. It also carries item rarity
  through inventory and equipment presentation using theme-owned semantic colors.
- Release 19 implements Workflow Step 19 with one-folder packaging verification,
  source/package startup readiness, model discovery and explicit loading through Unsloth Studio's API, and a scrollable
  half-width Settings column. Model loading remains explicit and campaign state remains
  outside the model-management boundary.
- Release 20 is a post-workflow gameplay expansion. It adds persistent merchant stock,
  deterministic pricing and barter adjustments, atomic transactions, commerce audit
  coverage, and consistent centered navigation footers.
- Release 21 adds persistent application-owned crafting recipes, ingredients, tools,
  deterministic checks, atomic outputs, Crafting XP, Event Log/audit coverage, and a
  durable themed result acknowledgement. It also adds a saved People-page splitter
  without changing the centered one-third-width Trade region.
- Release 22 consolidates duplicate navigation in accordance with the approved dense
  dashboard: skill XP appears on the shared Adventurer Tools cards, Quests remains on
  the adventure dashboard, disabled footer placeholders preserve alignment, and the
  existing Campaign browser occupies Settings' right column. Schema 17 is unchanged.
- Release 23 reorganizes the supplied creation sequence so World & Safety establishes
  generation context first. One bounded local-model request may propose a complete
  remaining profile, but application catalogs and deterministic validation reject any
  unsupported field before the form changes. Name and appearance suggestions retain
  explicit user approval, and the form uses compact centered responsive controls.
- Release 24 adds the supplied `dnd_ui_source` concept as an isolated Default theme.
  `Icons_svg/manifest.json` and `Icons_original_sheet.png` were the deterministic runtime
  item source until Phase 8; the runtime source is now the library manifest
  (`item_icon_manifest.json` and the CraftPix PNGs in `ui/assets/icons/library`); `UI_pack_3` supplies only the Map, People, and Settings navigation icons.
  Existing themes and all splitter behavior remain independent of those assets.
- Phase 4 adds navigation, real tab switching, keyboard-accessible selection,
  local action validation, context-action requests, settings, and UI preference
  persistence over the Phase 3 widgets. None of these interactions implements
  gameplay actions, combat, SQLite, or Unsloth Studio.
- Phase 5 implements the SQLite boundary prescribed by the resources. The UI
  reads an immutable dashboard projection through services and repositories;
  it has no direct SQL dependency. The deterministic seed matches the approved
  Greystone dashboard while leaving gameplay mutations and Unsloth Studio for later
  phases.
- Phase 6 implements the written setup sequence from Character Creation sections
  B and Z. The desktop form preserves all 22 written choices, adds the user's
  requested selectable focus skills and one multiline biography/backstory field,
  and applies the active theme to the campaign browser, every input control,
  validation feedback, allocation counter, and final review.
- Phase 6.1 implements the architecture guide's stateless, OpenAI-compatible
  Unsloth Studio boundary at `http://localhost:<PORT>/v1` (authenticated with an
  `sk-unsloth-…` API key). Character randomization uses
  bounded draft context and strict three-option structured output; the UI owns
  option approval and SQLite remains the only persistent authority. All fixed
  creation choices are non-editable full-click dropdowns, equipment is fully
  selectable, personality is capped at two, and blank content preferences use
  the documented balanced default.
- Phase 7 implements the guide's deterministic command-validation and atomic
  transaction boundary for inventory Use, Equip, Unequip, and Drop. Item rules,
  resource/status effects, stack consumption, charges, durability, equipment
  references, quest protection, and inventory events are owned by application
  code and SQLite; Unsloth Studio has no access to this mutation path.
- Phase 8 implements the guide's structured-turn workflow: capture and classify
  input, reject combat before inference, build bounded current context, call Unsloth
  Studio once with a strict schema, retry malformed formatting once, validate a
  small operation allowlist, commit the complete turn atomically, and rebuild
  every panel from SQLite. Cancellation after generation but before commit leaves
  the ledger unchanged.
- Phase 9 implements the reference guide's Combat, Dice and Checks, and Health
  rules as a SQLite-backed deterministic engine. It tracks initiative, rounds,
  health, distance, cover, conditions, weapons, ammunition, hazards, and morale;
  preserves player control; allows retreat and surrender; warns at critical
  health; and atomically commits items, resources, progression, events, and the
  shared transcript. Unsloth Studio may only phrase resolved mechanics and choose
  from application-supplied enemy intents.
- Phase 10 expands that deterministic boundary with a starter four-action
  catalog for every selectable class, persistent mana/spell slots/cooldowns and
  limited uses, direct and area effects, healing, buffs, periodic conditions,
  availability explanations, and short-rest recovery. Unsloth Studio receives only
  the already-resolved mechanical summary for optional narration.
- Phase 11 adds the application-owned enemy archetype and loot catalogs. Location,
  level, difficulty, and clock facts select a deterministic encounter; Unsloth Studio
  can phrase only bounded presentation text and legal enemy intent choices.

## Visual verification

LibreOffice 26.2.4.2 was installed after the initial structural review and was
invoked directly from `C:\Program Files\LibreOffice\program` because it is not
on `PATH`. All five Word documents were converted and every rendered page was
visually inspected: 119 pages in total. No content was clipped or lost. The
Adventure Reference Guide contains one blank trailing page. None of the Word
files contains embedded image relationships; the standalone PNG remains the
approved visual reference.
