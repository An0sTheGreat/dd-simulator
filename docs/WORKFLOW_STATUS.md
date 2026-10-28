# Release and Workflow Status

This project uses two deliberately separate identifiers:

- **Release** identifies an application implementation batch and its packaged build.
- **Workflow Step** identifies the canonical ordered workflow in
  `D&D_Simulator_Simple_ChatGPT_Project_Workflow.docx`.

Historical database migrations, preview filenames, test modules, and command-line
smoke-test aliases keep their original identifiers so saved campaigns and developer
automation remain compatible. New user-visible milestones use `Release` and canonical
resource sequencing uses `Workflow Step`.

## Current status

| Project milestone | Status | Canonical workflow coverage |
| --- | --- | --- |
| Release 14 | Complete | NPCs/relationships plus refinements to inventory, map, events, and navigation |
| Release 15 | Complete | Skills, equipment, and itemization refinement before the next canonical step |
| Release 16 | Complete | Visual Registry plus equipped-item and Event Log refinements |
| Release 17 | Complete | Save/load/repair/replay plus People-tab dialogue repair |
| Release 18 | Complete | Model evaluation/performance plus persistent rarity presentation |
| Release 19 | Complete | Packaging, setup, first-run validation, and model-load repair |
| Release 20 | Complete | Economy, bartering, persistent merchant stock, and centered navigation controls |
| Release 21 | Complete | Deterministic crafting, durable result acknowledgement, and resizable People trade/conversation layout |
| Release 22 | Complete | Skill XP bars, redundant-navigation removal, and Campaign management inside Settings |
| Release 23 | Complete | World-first Character Creation, validated full-campaign generation, and compact centered forms |
| Release 24 | Complete | Isolated Default UI, deterministic semantic icons, narrative cleanup, and restart-persistence verification |
| Release 25 | Complete | Direct semantic SVGs, tiered catalog loot, lazy hover cards, natural narrative segments, and Adventure/People trade continuity |
| Release 25.1 | Complete | Prevent Default-theme semantic icons from briefly becoming parentless native windows |
| Release 26 | Complete | Textured Default-theme surfaces, fantasy control states, icon-free resource bars, and preserved resizers |
| Release 26.1 | Complete | Approved-mockup fidelity correction with scalable ornament, dark insets, compass frame, and themed splitter grips |
| Release 26.2 | Complete | Shared textured panel surface, aligned title ornament, subdued resource borders, and themed popup shell |
| Release 26.3 | Complete | Tiled Default surface, custom window chrome, modal dimming, circular icon inventory, and 28-slot persistence |
| Release 26.4 | Complete | Transparent icon dragging, separate no-scroll Inventory/Equipment tabs, smaller surface tile, and rectangular minimap |
| Release 26.5 | Complete | Supplied Default background, 32-slot inventory pages, restored minimap/hover ornament, and distinct rarity-aware icons |
| Release 26.6 | Complete | Character Sheet, supplied card styling, semantic ability cards, responsive inventory, live compass overlay, and native window snap |
| Release 26.7 | Complete | Deep Dark Fantasy Default revamp, dark supplied backdrop, persisted sidebar splitter, six-column inventory, compact Character Sheet, and drag-restore repair |
| Release 26.7 maintenance | Complete | Retired Default theme; Modern Fantasy Simple fallback and opaque hover cards for both supported themes |
| Release 26.7 creation maintenance | Complete | Four-step character creation, campaign-only generation, autosaved asynchronous opening, DM context, and equipped-item comparison |
| Release 26.8 | Complete | Required local-model gate, exclusive model loading, schema compatibility fallback, bounded creation prose, button traits, and readable final review |
| Release 26.8.1 | Complete | Unlimited cancel-and-randomize retries with safe option-object and numbered-text parsing |
| Release 26.8.2 | Complete | Field-specific appearance generation, combined biography/backstory, and robust labeled campaign generation |
| Release 26.8.3 | Complete | Unlabeled campaign-premise compatibility and bounded Narrative & Player Action prose |
| Release 26.9 | Complete | D&D 5E Character Sheet creation, point-buy, class HP, live sheet detail, campaign deletion, and 100 starting gold |
| Release 26.9.1 | Complete | Responsive location artwork, global percentage font scaling, chooser retries, and Qwen/Gemma first-run recommendations |
| Release 26.9.1 maintenance | Complete | State-owned NPC discovery, persistent People selection, recent-turn emphasis, clean in-game preset titles, and font-scale exemptions |
| Release 27 | Complete | Model-text sanitization, ordered deterministic quest gates, first-run guidance, diagnostics export, difficulty tuning, and accessibility checks |
| Workflow Step 15: Map, Time, and World State | Materially complete | Implemented primarily in historical Release/Phase 13 |
| Workflow Step 16: Visual Registry | Complete | Implemented and packaged in Release 16 |
| Workflow Step 17: Save, Load, Repair, and Replay | Complete | Implemented and packaged in Release 17 |
| Workflow Step 18: Model Evaluation and Performance | Complete | Implemented and packaged in Release 18 |
| Workflow Step 19: Packaging, Setup, and First-Run Validation | Complete | Implemented and packaged in Release 19 |

Release 16 is the completed implementation batch for canonical Workflow Step 16.
Its acceptance boundary includes schema migration, exact state-matched asset reuse,
pending and confirmation transitions, themed portrait/location renders, Event Log
and equipment-card regressions, and packaged smoke verification. Merchants,
economy, and crafting remain later expansion work.

Release 17 is the completed implementation batch for canonical Workflow Step 17.
It adds schema-aware named checkpoints, pre-load and pre-repair recovery backups,
campaign integrity evidence, safe correction reports, and persisted audit/checksum
replay verification. The same release repairs People-tab dialogue by selecting Unsloth
Studio's actually loaded model, sending bounded NPC context, retrying format drift,
and committing nothing when generation fails. Workflow Step 18 is the exact next
canonical step; Release 18 completes it without granting models gameplay authority.

Release 18 discovers installed and loaded models from Unsloth Studio, allows only loaded
instances to be selected, persists the explicit choice outside UI-reset state, and
routes every existing generation path through the same client. Settings exposes a
three-sample, campaign-isolated evaluator reporting schema reliability, compatibility
retries, latency, token rate, bounded quality checks, context, and memory metadata when
Unsloth Studio supplies them. Reports are written beneath the user's configuration folder.
The same release standardizes Common, Uncommon, Rare, Epic, and Legendary theme tokens
so an item's stored rarity follows it between inventory, equipment, hover cards, reward
cards, drag/drop, sort, and reload.

Release 19 completes the packaging and first-run workflow. Settings uses one
scrollable left column occupying half the page. Models remain selectable;
an explicit Load Selected Model action calls Unsloth Studio's `/api/inference/load`
route on a worker thread, saves only a confirmed loaded model, and refreshes readiness
before evaluation or play. Startup reports source/package mode, writable configuration
storage, and database schema readiness. Source and packaged smoke tests use isolated
configuration directories. Canonical Workflow Steps 1-19 are now complete; later
releases are gameplay-expansion work rather than unfinished foundation work.

Release 20 begins that gameplay expansion with application-owned merchant stock,
deterministic buy/sell/barter quotes, atomic inventory and currency transfers,
transaction/Event Log persistence, and checkpoint coverage. The themed People trade
panel shows current stock and eligible player items. Dialogue remains the only Unsloth
Studio role in commerce. People response controls and Return to Adventure controls
are centered at roughly one third page width without changing bottom navigation.

Release 21 adds the next application-owned gameplay system: persistent recipes,
ingredient and tool requirements, deterministic difficulty checks, atomic material
consumption and output creation, Crafting XP, Event Log/audit records, and durable
result acknowledgement. The People page now saves an independent vertical splitter
between its centered one-third-width Trade region and full-width conversation region.
Unsloth Studio has no authority over crafting inputs, difficulty, quality, rarity, output,
inventory movement, tool use, or progression.

Release 22 is a presentation consolidation. Shared skill cards now show thin
authoritative XP progress bars using each theme's primary accent. Skills and Quests
no longer register duplicate navigation pages, while three disabled blank footer
buttons preserve the established six-column geometry. The existing Campaign browser
moves into Settings' right column and keeps its creation/load workflows. No migration
or model-authority change is introduced; schema version 17 remains current.

Release 23 makes World & Safety the first Character Creation decision and uses it as
immutable context for one optional full-profile Unsloth Studio request. Application code
validates the complete response against existing catalogs and the creation validator
before changing the form. Individual campaign/character names retain the three-option
approval flow. Role/personality fields are consolidated, focus skills use eight bounded
toggle buttons, and all creation forms use compact centered one-third-width layouts.
No schema migration or model gameplay authority is added.

Release 24 introduces a fresh-install Default theme based on the approved dark-stone
concept while preserving saved theme preferences and leaving both existing theme files
unchanged. A cached application-owned atlas and semantic manifest resolve generated
item visuals deterministically from name, category, mechanics, slots, description, and
rarity. The LM turn boundary now normalizes stray backticks and clearly mixed dialogue
segments before presentation. Existing transactional persistence is verified through a
file-backed close/reopen and Return-to-Adventure regression. Schema 17 is unchanged.

Release 25 replaces atlas crops with the actual numbered semantic SVGs and makes all
1,686 records eligible through one tier-weighted application catalog. Combat and quest
rewards, merchant stock, and explicit scene searches share that catalog while Unsloth Studio
receives only a validated eight-item shortlist. Tooltip windows are created lazily,
narrative text keeps the model-declared semantic kind without heuristic quote rewriting,
and Adventure trade requests route into the existing People conversation and commerce
flow. People dialogue is projected back into the shared Adventure transcript. Schema 17
remains current.

Release 26 is a presentation-only refinement of the isolated Default theme. Original
charcoal-stone, dark-leather, and hammered-iron textures supply the application rails,
panel interiors, controls, cards, scrollbars, and splitter handles. Theme-relative asset
URLs are converted to packaged absolute paths at load time. The pass preserves semantic
item artwork, rarity colors, compact inventory geometry, every draggable splitter, and
the untouched High Fantasy and Modern Dark themes. Resource bars retain their values and
color identity without decorative icons. Schema 17 remains current.

Release 26.1 corrects the initial pass against its approved visual target. One native
nine-slice frame supplies blackened-iron rails, aged-bronze lines, and restrained corner
caps at arbitrary panel sizes. Separate transparent assets add the header flourishes,
open-center minimap compass, and centered horizontal/vertical splitter grips. Near-black
insets replace the oversized brown leather fields. All existing panel behavior, semantic
icons, rarity colors, and non-Default themes remain unchanged. Schema 17 remains current.

Release 26.2 removes the remaining flat gradient presentation by allowing one shared
charcoal-stone surface to show through translucent panel insets. The title label now
owns its centered ornament, resource bars use dark low-contrast outlines, and all
application-owned modal workflows share a movable frameless shell with a custom title
bar, textured interior, and existing nine-slice ornament. Schema 17 remains current.

Release 26.3 replaces the stretched application surface with a compact seamless tile,
centers the ornamental application title using equal side regions, and gives the main
window and shared dialogs matching draggable chrome. Modal dialogs dim the application.
Inventory and equipment now use circular icon-only wells with rarity rings, hover-only
names/details, and quantity badges. Schema 18 compacts bag positions and establishes a
28-slot baseline without discarding legacy overflow. Stable theme IDs remain unchanged;
their simplified display names are Modern Fantasy Simple and Modern Dark Simple.

Release 26.4 keeps the existing circular item components but separates the utility
Inventory and Equipment views. All 28 inventory wells remain visible without a scroll
container; Equipment uses a 5-column, 2-row layout. Drag previews use only the semantic
SVG pixmap. The Default surface tile is reduced to 96 pixels, and the minimap compass is
a rectangular framed layout whose cardinal and destination labels remain anchored as it
resizes. Schema 18 remains current.

Release 26.5 expands each Inventory page to 32 icon wells and reveals compact previous
and next controls only when occupied items require another page. Schema 19 raises the
persistent storage reserve to 320 positions while projection exposes only the minimum
occupied set of 32-slot pages. Default now uses the supplied `background2.png` through
an optimized runtime copy, restores a prominent rectangular minimap ornament, and
ornaments item-hover cards. Curated mappings give the demonstrated skills, abilities,
and common items distinct semantic SVGs while retaining tier-appropriate escalation
for rare and legendary variants.

Release 26.6 adds an original read-only Character Sheet in the former blank footer slot,
centered at no more than three fifths page width and projected entirely from authoritative
campaign state. Supplied card references now provide rarity-specific item-hover framing
and selected control ornament; abilities and spells share the hover lifecycle and always
show their deterministic cost, effect, range, target, use, cooldown, duration, and save
statistics. The supplied high-resolution background is optimized for Qt without changing
the source. Inventory keeps 32 slots per page, uses a no-scroll seven-column arrangement
at 1600 x 900, and returns to four scrollable columns when narrow. The Default minimap
draws its real compass PNG behind live rectangular edge labels. Custom chrome retains its
look while delegating title dragging to Windows for maximize/snap behavior. Schema 19 is
unchanged.

Release 26.7 replaces only the Default theme's outer presentation with the supplied
Deep Dark Fantasy SVG system and `background_dark.jpg`. Shared SVG panel, button,
resource-frame, divider, scrollbar, and ornament assets style the application without
altering semantic item or skill icons. The Minimap/Adventurer Tools boundary is now a
saved vertical splitter, inventory never exceeds six columns, and Character Sheet skill
and ability sections stay compact and top-aligned. Custom chrome restores a maximized
window beneath the active pointer before Windows continues the native move/snap loop.
The completed refinement unifies inactive and interactive button states on the Deep Dark
family, retires the older card-derived button rail, uses translucent panel surfaces,
restores title ornaments, prevents custom window-control frame clipping, and nests item
hover content inside a transparent rarity ornament so descriptions remain within the card.
Schema 19 is unchanged; Modern Fantasy Simple and Modern Dark Simple are untouched.

Release 26.7 maintenance subsequently retires the Default theme and its packaged assets.
Modern Fantasy Simple is now the startup/fallback theme, including for a saved `default`
preference. Both supported simple themes paint the shared item-hover surface directly,
preventing transparent cards while retaining icons, mechanics, and descriptions.

The current Release 26.7 maintenance pass replaces the circular-well presentation with
the supplied square inventory and 3 x 3 equipment artwork. Inventory now projects in
36-slot pages (6 x 6 normally, 4 x 9 when narrow); the equipment board uses the fixed
Ring/Head/Neck, Main Hand/Body/Off Hand, Hands/Ammunition/Feet order. Runtime tinting
was removed so both supported themes display the authored PNG colors exactly. Existing
rarity, quantities, tooltips, paging, sorting, and drag/drop behavior is retained.

The finalized sizing pass locks inventory wells to 96 pixels and item artwork to 68
pixels. Equipment uses an exact 720-pixel (9x source) rendering cap within its 735-pixel
layout maximum, with 100-pixel target maxima, and scales both to the available tab dimensions. Occupied targets
replace only their exact board cell with the shared slot artwork. Rarity is shown on the
hover-card border and title rather than around item wells. Auto-Sort now exposes stable
Default, Rarity, Type, and Value orders without touching equipped items.

The follow-up alignment fix uses the board's measured 22-pixel well origins at 6, 29,
and 52 source pixels, eliminating the offset occupied overlays. A complete six-column
inventory page is centered in both axes when space permits; constrained pages retain
their existing four-column, top-origin scrolling behavior.
The equipment board and occupied-cell images are now rendered once at their final label
dimensions with nearest-neighbor scaling; QLabel no longer performs a second resample.

The Windows custom title bar now enters the native `HTCAPTION` move loop. Windows owns
top-edge Aero Snap and maximized drag-restore behavior; the existing Qt move/restore path
remains as the non-Windows fallback, and double-click maximize/restore is unchanged.

Release 26.7 creation maintenance consolidates Character Creation into four numbered
tabs: Appearance/Identity/Skills/Role, Equipment, Campaign, and Final Review. The two
split pages use invisible equal columns and the review uses separate themed cards.
Campaign randomization now receives the complete confirmed profile but may return only
the campaign name and editable premise, preventing model output from replacing earlier
player choices. Creation commits immediately with a visible generation placeholder;
the local model then writes an approximately 150-word opening, which atomically replaces
the placeholder and autosaves. A deterministic opening is used if Unsloth Studio is unavailable.
Every gameplay generation path carries a shared Dungeon Master role instruction, while
the bounded action context includes non-empty persisted player and campaign details.
Compatible inventory hover cards now appear beside the occupied equipment-slot card,
with the equipped item explicitly labeled. Schema 20 remains current.

Release 26.8 adds Local AI Model Selection as the required first Character Creation tab
and disables every later section until a loaded model is confirmed. Model switching
unloads other active Unsloth Studio models before loading the requested model. Creation,
campaign, title, and opening requests now use prompted plain JSON with local validation;
valid tool-call arguments are parsed as a compatibility path. Gameplay generators retain
strict mechanical schemas, automatically retry without `response_format` after a schema
failure, and remember the affected model for the rest of the session. Generated
appearance prose is capped at 75 words, biography/backstory at 120 words, manual fields at
4,000 characters, and campaign titles at 12 words. Personality and focus-skill buttons
show explicit selection, equipment choices expose mechanics tooltips, Final Review uses
wrapping tables/cards, and creation remains disabled until confirmation. Schema 20 is
unchanged.

Release 26.8.1 fixes repeated character-creation randomization after cancelling the
option chooser. The shared parser now normalizes safe option objects and exactly three
numbered or bulleted plain-text choices in addition to the existing JSON formats. Cancel
remains non-mutating, button/task cleanup remains bounded, and every existing option
limit is applied before display. Schema 20 is unchanged.

Release 26.8.2 consolidates Biography and Backstory into one written/generated field,
removes Custom from Difficulty, and replaces generic creative-output instructions with
field-specific contracts. Body options require explicit Height and Build details; campaign
titles use three numbered lines; campaign generation uses labeled name and premise text
while retaining JSON compatibility. The model evaluation now probes these same live
Character Creation contracts. Schema 20 is unchanged.

Release 26.8.3 preserves an existing campaign name when Unsloth Studio returns premise-only
prose, accepts labeled or unlabeled premises, and may use a short first line as a title
when no name exists. Generated action, combat, travel/camp, and synced-dialogue prose is
capped at 125 total words before entering Narrative & Player Action; the initial campaign
introduction is capped separately at 220 words. Schema 20 is unchanged.

World & Safety now places an editable Campaign Premise field directly below Randomize
Campaign. Full-campaign generation fills it, manual changes remain authoritative, and
creation uses the final text for the saved premise, starting location, opening narrative,
and future Unsloth Studio action context. Database schema 20 persists the premise.

Release 27 introduces one shared plain-text presentation boundary for every local-model
output path. Ordered quest gates prevent important confrontations and final objectives
from being skipped by descriptive prose or direct completion calls. Local AI onboarding
now explains setup expectations, Settings exposes model-capability metadata and a bounded
troubleshooting sequence, and a one-click ZIP export includes runtime/evaluation logs but
not saved campaigns or preferences. Deadly difficulty now also affects commerce and social
checks. Targeted keyboard-focus and accessible-name coverage is regression tested. Schema
21 remains current.
