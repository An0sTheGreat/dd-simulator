# Project Decision Record

Date: 2026-07-22

## Confirmed decisions

- Target: Windows desktop application packaged as an `.exe`.
- Language: Python 3.12 or newer. Development currently uses Python 3.14.3.
- UI: PySide6 / Qt with reusable widgets, semantic object names, QSS, and
  external theme tokens.
- State: SQLite will be the authoritative Game-State Ledger in the state phase.
- Validation: typed Python models first; Pydantic may be introduced with the
  structured model turn schema.
- Unsloth Studio: stateless, authenticated OpenAI-compatible API at
  `http://localhost:<PORT>/v1` (default `8888`, `Authorization: Bearer sk-unsloth-…`),
  with the application owning all persistent state. Explicit model loading uses the
  installed build's `/api/inference/load` management route. See `UNSLOTH.md`.
- LM Studio: retained as the secondary external server (`http://localhost:1234/v1`, no
  key, native `/api/v1/models` loading on LM Studio 0.4+). Saved LM Studio setups keep
  working. Decided 2026-10-27.
- Testing: pytest for nonvisual logic and Qt offscreen smoke tests.
- Packaging: PyInstaller one-folder Windows distribution for the initial build.
- Rules scope: custom fantasy rules inspired by tabletop role-playing games,
  preserving the supplied adventure terminology and constraints.
- Visual scope: portrait and location images are planned, but the Visual
  Registry will precede any automatic image generation.
- Network boundary: localhost-only by default.
- Fresh-install UI theme: Release 24 Default styling based on the supplied
  `dnd_ui_source` concept. Existing High Fantasy and Modern Dark preferences remain
  valid and their theme files are unchanged.

## Current milestone

Release 24 keeps item visuals application-owned. A semantic manifest and cached atlas
select stable icons from item facts and rarity without an LM or image-generation call.
Both supported simple themes display those icons. Model prose is normalized at the
existing response boundary before semantic styling, and SQLite's existing immediate
transactions remain the autosave mechanism.

Release 23 treats World & Safety as immutable generation context. A full campaign
randomizer uses one structured local-model request, then application code validates
every generated catalog choice and required field before updating the in-memory form.
No generated draft writes state without the existing review and confirmation step.

Release 22 removes the redundant Skills, Quests, and Campaign navigation destinations
without shifting the footer layout: disabled blank slots retain its six equal columns.
The shared skill card displays persisted XP progress in theme accent colors. Campaign
management moves intact into Settings' right column. No schema migration is required.

Release 21 makes crafting application-owned SQLite state. Recipes, ingredient and tool
requirements, check targets, campaign modifiers, material consumption, item quality,
rarity, output, and Crafting XP are deterministic and committed atomically. Unsloth Studio
does not resolve or modify crafting. Results remain pending until acknowledged. The
People page uses a saved vertical splitter between a centered one-third-width Trade
region and a full-width conversation region.

Release 20 is the first post-workflow gameplay expansion. Merchant stock, prices,
bartering, item transfers, and currency are application-owned SQLite state. Unsloth Studio
is limited to existing NPC prose. Trades use explicit confirmation and one atomic
transaction. Navigation return controls and People responses use centered
one-third-width footers.

Release 19 completes canonical Workflow Step 19. PyInstaller remains a one-folder
distribution; only `dist\DnDSimulator\DnDSimulator.exe` is runnable. Startup verifies
configuration storage and schema readiness. Settings is a scrollable half-width left
column. Installed model choice is separate from explicit loading; only a model that
Unsloth Studio confirms as loaded can replace the shared generation model.

Release 17 implements canonical Workflow Step 17. Normal SQLite persistence remains
continuous; a named save is a verified checkpoint with schema, scene, visual,
checksum, and audit metadata. Checkpoint load and safe repair create recovery backups
before changing authoritative state. Replay verification compares the persisted
before/after checksum chain with current campaign state. The Settings page exposes
these operations without giving Unsloth Studio database authority.

The Release 17 People-tab repair selects the model Unsloth Studio reports as loaded instead
of the first installed model, sends bounded recent NPC context, retries structured
format drift once without strict response-format enforcement, and rejects failed
generation without committing the player's input or a generic fallback response.

Release 16 implements canonical Workflow Step 16. Visual files remain local and
are copied beneath the campaign configuration directory; SQLite stores relative
paths, hashes, versions, state signatures, canonical and active selection,
generation metadata, appearance locks, confirmation state, reuse counters, and
append-only history. Exact confirmed state matches outrank the canonical fallback.
Pending or missing files remain explicit placeholders. Artwork is never
automatically approved, and Unsloth Studio does not own visual state.

Release 15 is complete. It refines the two-parent Skills
page, compatible bidirectional inventory/equipment dragging, persistent item
metadata, hover information cards, and derived equipment statistics. The canonical
workflow remains separate: Workflow Step 15 (Map, Time, and World State) is
materially complete, and Workflow Step 16 (Visual Registry) is implemented by
Release 16. Schema version 13 supplies deterministic persistent item details,
stable legacy-equipment identities, compatible-slot validation, and recalculated
carry/armor/attack summaries. See `WORKFLOW_STATUS.md`.
Release 15 hover cards use a persistent application-owned two-column presentation
instead of native timed tooltips, and the UI font-size preference scales compiled
theme typography without changing the selected theme.

Release 14 added current-location NPC conversations, deterministic visible social
checks, relationship memory, and application-owned quest/discovery effects.
Schema version 12 also separates equipped items from 40 visible inventory
positions while preserving stable item records, adds drag/swap and deterministic
auto-sort, exposes combat abilities separately in both Skills views, and repairs
current story locations into map discovery. Unsloth Studio can phrase NPC speech and
monologue but cannot choose or alter mechanics.

Phase 13 replaces the Map placeholder with discovered location nodes and
inspectable direct routes. Schema version 11 stores route distance, time, stamina,
danger, status, requirements, visibility, travel history, linked encounters,
camp permissions, and camp history. Map-confirmed travel is now the only path that
can change destination, preventing free-form model proposals from bypassing travel
costs. Four- and eight-hour camp actions recover bounded resources. Optional Unsloth
Studio travel prose runs asynchronously outside the write transaction and has no
mechanical authority.

Phase 12 adds deterministic persistent quest lifecycles, typed objective triggers,
campaign-clock deadlines, follow-up activation, and idempotent XP, currency,
reputation, and item rewards. Completed quests are locked and gray in the compact
six-column Quest page; active quest cards expand inline. A theme-aware completion
dialog keeps unclaimed items durable. Schema version 10 stores these facts, and
Unsloth Studio remains limited to phrasing bounded narrative and quest notes.

Phase 11 adds a persistent enemy-archetype catalog and deterministic encounter
generation keyed by campaign, location, clock, difficulty, and level. Generated
encounters reveal terrain, awareness, enemy capabilities, and a required tactical
preparation choice before initiative continues. Enemy special abilities,
resistances, vulnerabilities, morale negotiation, tactics, and reinforcements are
application-owned. Every encounter creates one idempotent reward record; victories
apply progression and currency once and retain individually claimable loot until
acknowledged. Schema version 9 stores these facts. The dashboard also gains a
persistent vertical row divider, and the Modern Proof identifier now presents a
high-contrast Modern Dark palette for preference compatibility.

Phase 10 extends deterministic persistent combat with four catalogued actions
for every selectable class and the demo Warden. The application owns resource
costs, spell slots, range, attack rolls, saving throws, direct/area damage, healing, buffs,
lasting conditions, periodic damage, cooldowns, limited uses, and short-rest
recovery. The Combat tab exposes separate non-editable ability and spell
selectors with availability explanations. Schema version 8 extends the existing
ability, condition, and combat-turn ledgers without granting Unsloth Studio any new
mechanical authority.

Phase 9 established deterministic persistent combat on top of the Phase 8
structured non-combat loop. The Combat tab owns Attack, Power Strike, Advance,
Defend, healing-item use, and Flee commands. SQLite persists encounter status,
round/current initiative index, combatants, health, armor, distance, movement,
range, weapons, morale, conditions, intent, and every mechanical turn. The
application calculates all rolls and outcomes, synchronizes resources and item
exhaustion, awards progression, and resumes active encounters after restart.
One optional bounded Unsloth Studio request can phrase the resolved player beat and
select only from application-supplied legal enemy intents. Schema version 7
adds the combat ledger and combat/system transcript kinds.

Phase 8 established the structured non-combat turn loop prescribed by the
architecture guide. Each player action sends one bounded, ID-bearing context to
local Unsloth Studio and requests narration plus enumerated state proposals. The
application independently validates ownership, operation type, field, value,
resource limits, item rules, quest state, known destinations, route state, and
time bounds. Narration and every approved change then share one SQLite
transaction with the turn audit and event row. Invalid proposals reject the
complete outcome. Cancel prevents commit, failures preserve the action for
Retry, and normal factual panel reads still make no model calls. Schema version
4 adds turn/minute tracking and append-only action-turn records. Schema version
5 adds the submitted player action and ordered narrative, monologue, and spoken
response segments. Schema version 6 adds append-only transcript messages with a
20-message UI projection.

The Phase 8 dashboard revision consolidates Player Summary and Resources,
removes redundant Profile, Inventory/Equipment, and Journal navigation pages,
and keeps Skills as a compact detail view. Inventory actions and journal/event
information remain available directly on the adventure dashboard.

## Decisions still requiring later input

- Target GPU, VRAM, RAM, and storage profile.
- Final preferred Unsloth Studio model and quantization after comparing in-app evaluation
  reports on the target hardware. The application now persists an explicit loaded
  selection and uses path-specific bounded output caps.
- Expanded spell catalogs and campaign-authored enemy archetypes beyond the
  Phase 11 starter catalog.
- Final location for user campaign data and backup retention policy.

These open decisions do not block Release 18. Model discovery no longer assumes the
first installed model: it exposes loaded readiness and persists an explicit selection.
