# UI Redesign Plan — Concept T

Status: **approved** (2026-10-27). Decisions D1–D4, D6 and D8 approved as recommended; D5 and D7 adjusted below.

Approved target: Concept T, "Paired Cards, Concept I Messages"
(`artifacts/ui-concepts/concept-t-classic-messages.png`, source HTML beside it; shared
tooltip sheet `artifacts/ui-concepts/concept-m-tooltips.png`). `artifacts/` is gitignored, so
Phase 1 copies those two PNGs to `docs/design/` as the committed reference.

## 1. What changes for the player

| Area | Today (Release 27) | Concept T |
| --- | --- | --- |
| Layout | Three rows: summary, narrative + quests, event log + recent events; right utility sidebar with tabs | Two columns. Left: the whole character. Right: the scene and the story |
| Character | Player Summary panel; Skills, Inventory, Equipment and Combat behind Adventurer Tools tabs | Always visible: vitals strip; paperdoll with 9 slots around the portrait; skill list with descriptions; Inventory card (5×5, scrolls); Abilities & Spells card (two columns) |
| Location | Location Summary panel + location image in the minimap slot | Location art fills the right column; title, region and condition chips over it |
| Quest | Quests & Objectives panel with tabs | Quest-progress card over the art: ring, objectives, rewards |
| Conversation | Latest 20 messages in a framed panel | Scrollable history fading up into the art. Narrator: plain shadowed text. Player: rounded brown box, right. NPC: rounded box with portrait and name. Update tags under the message that caused them |
| Actions | 6 buttons + input, truncated labels | 2×3 choice grid with number keys, wide input, ACT |
| Navigation | Bottom button row with blank placeholders | Tabs above the art: Adventure, Map, People, Character Sheet, Settings |
| Tooltips | Item and ability hover cards | One shared card family for items (with comparison when equipped), abilities, spells and skills |

## 2. Decisions needed before Phase 2

Each has a recommendation; the plan assumes it unless you say otherwise.

- **D1 — Event Log, Recent Events and "At this location".** Concept T has no panel for them.
  *Recommend:* inline update tags replace the event log on the Adventure view. A new
  **Journal** tab holds the full filterable Event Log, Recent Events and the quest list.
  Present NPCs stay on the People tab, plus small "present" chips under the location title.
- **D2 — Combat.** Today combat lives in the Adventurer Tools Combat tab, which Concept T removes.
  *Recommend:* while an encounter is active, the quest card becomes an **Encounter card**
  (combatants, health, initiative, intents), and the choice grid becomes the combat action
  grid (Attack, Advance, Defend, Use Potion, Negotiate, Flee). Abilities and spells are cast by
  clicking them in the Abilities & Spells card. Free-text input stays locked during combat, as today.
- **D3 — Crafting.** It is also an Adventurer Tools tab today.
  *Recommend:* move it to the Character Sheet page as a section.
- **D4 — Themes.** *Recommend:* Concept T's bronze look becomes **Modern Fantasy Simple**.
  **Modern Dark Simple** keeps the same layout with its own palette and no bronze textures.
- **D5 — Icons. Decided:** RPG Mega painted icons for everything: skills, abilities, spells, and
  every item type (weapons, armor, jewelry, consumables, materials, quest items). Skills, abilities and
  spells are mapped in Phase 3. Items are mapped in Phase 8 through a new RPG Mega item manifest that
  replaces the 1,686-icon SVG mapping.
  *Analysed and rejected:* the Quaternius `RpgItems` models (106 GLB, CC0). Rendered headless with
  Blender 5.2, they come out flat grey and brown, and thin items such as necklaces and bows are
  unreadable at slot size. They are not ported.
- **D6 — Portrait.** *Recommend:* use the confirmed Visual Registry portrait. Otherwise use a
  painted RPG Mega avatar chosen by class and ancestry, which the player can change in Character
  Creation. The current "KS" initials remain a last fallback.
- **D7 — Inventory capacity. Decided:** keep the existing 320-slot cap and its "inventory is full"
  rules. The 5×5 Inventory card scrolls through every occupied position (up to 320) in rows of 5,
  with drag and drop, auto-sort, selection and keyboard navigation working across the whole scrolled range.
- **D8 — Speaker names in free-form turns.** Today the model's spoken lines carry no speaker.
  *Recommend:* extend the turn contract with an optional `speaker_id`, validated against NPCs present
  at the location. Unknown or invalid values fall back to an unnamed speech box. Lines synced from
  People dialogue already know their NPC.

## 3. Assets

Copied into `src/dd_simulator/ui/assets/codex/` (packaged via `pyproject.toml` and `DnDSimulator.spec`),
with sources recorded in `docs/ASSET_CREDITS.md`:

| Asset | Source | License |
| --- | --- | --- |
| Bronze panel, tooltip, slot, rarity, button, tab and divider frames; ornamental corners; gold markers | `Untitled RPG/Assets/Art/UI/Textures` and `UI/Source/Icons` | Original: drawn in code by your Untitled RPG project (`Tools/art/flat_library.py`); can be regenerated at higher resolution |
| Skill, ability and spell icons; portrait fallbacks | `Untitled RPG/Assets/RPG Mega/*` (CraftPix) | CraftPix free license: in-game use allowed; no standalone redistribution |
| Oxanium font | `Untitled RPG/Assets/Fonts/Oxanium` | SIL Open Font License |
| Georgia (story text, headings) | Windows system font (already used by High Fantasy) | System; not bundled |
| Location art | Existing 95-image location catalog | Already shipped |

PNGs are downscaled at copy time (512 px icons → 128 px) to keep the package small.

## 4. Phases

Work happens on branch `ui-concept-t`, one reviewed commit per phase. Every phase ends with the
full suite green (`scripts/test.ps1`, about 2 minutes) and a 1600×900 capture compared with the mockup.

### Phase 1 — Assets, tokens and reference (no visible change)
- Copy and downscale assets (section 3); add theme tokens for the codex palette to both theme JSONs;
  register Oxanium in `ui/fonts.py`; package data and spec entries; credits.
- Commit the Concept T and tooltip-sheet PNGs to `docs/design/`.
- Tests: asset presence and loadability; packaged `--smoke-test` still passes.

### Phase 2 — Data and projection (no visible change)
- **Schema 22:** nullable `speaker_npc_id` on `narrative_messages`; People-dialogue sync writes it.
  Backed up before migration like every migration. (D8 contract change in `local_model/action_resolver.py`.)
- **Per-turn notes:** projection groups each turn's audited state changes (XP, items gained or lost,
  quest updates, relationship changes, travel, resource changes) into `TurnNoteView(kind, text)`,
  attached to the last message of that turn.
- **Transcript paging:** the projection returns the newest 40 messages plus `has_older`; the service gains
  `older_messages(before_turn, limit)` for scroll-back.
- **Character data:** skill descriptions (catalog constant); ability and spell lists split by the existing
  `action_kind`; power status (ready, cooldown n, uses n/m); full unpaged inventory list.
- **Inventory:** the projection exposes all occupied positions (up to the 320 cap) instead of 36-slot pages.
- Tests: migration from schema 21 with data preserved; note grouping per turn; paging boundaries;
  ability/spell split, including empty lists; projection of more than 36 items.

### Phase 3 — Left column widgets
- `CharacterStrip` (name, class, purse, carry, five resource bars).
- `PaperdollPanel`: nine slots around the portrait, reusing `EquipmentSlotWidget` drag, drop and
  compatibility rules.
- `SkillDetailList` (icon, name, value, description, XP bar).
- `InventoryCard`: 5×5 viewport that scrolls without limit, reusing `InventorySlotWidget`, drag, drop and auto-sort.
- `PowersCard`: Abilities column and Spells column. An empty column hides; if both are empty the card shows
  "No abilities or spells yet".
- Inventory and Powers cards keep equal height.
- Tests: widget-level, for slots, scrolling past 25, hidden columns and drag between bag and paperdoll.

### Phase 4 — Right column widgets
- `SceneView`: location art from the existing resolver, with the dark gradient overlay; tabs; title and chips.
- `QuestProgressCard` (ring, objectives, rewards); an `EncounterCard` variant for D2.
- `ConversationView`: transparent scroll area over the art with a top fade mask. Message widgets follow
  Concept I's styles (narrator, player, NPC with portrait and name), with note chips under each turn.
  Scrolling to the top loads older pages; a new turn scrolls to the newest message. Reduced-motion mode keeps
  today's static emphasis.
- `ChoiceGrid`: 2×3 grid with keys 1–6; wide input with ACT; Cancel and Retry behaviour unchanged.
- Tests: rendering of each message kind, note placement, paging on scroll, keyboard choices, combat lock.

### Phase 5 — Tooltips
- Restyle the `PositionedHoverCard` family to the shared card: item, equipped item with a comparison block,
  ability, spell, skill and suggested response.
- Rarity colours on names and frames; cards stay inside the window; one hover lifecycle (create on hover,
  destroy on leave), as today.
- The People tab's conversation uses the same message widgets as the Adventure conversation, so both
  read alike.
- Tests: content for each kind; comparison appears only for compatible equipped items; screen-edge placement.

### Phase 6 — Main window assembly
- Replace `_build_main_splitter` and the bottom navigation with the two-column layout. Left and right
  splitter sizes are saved; old splitter preference keys are ignored, not migrated.
- Add the Journal tab (D1) and move crafting (D3) to the Character Sheet. Retire the Adventurer Tools,
  Event Log, Recent Events, Location Summary and Minimap panels from the dashboard.
- Behaviour at 1280×720: the paperdoll and bag slots shrink proportionally, the skill list scrolls, and the
  conversation keeps a minimum height. Font scaling 75–150% must not clip either column.
- Both themes; accessible names and keyboard focus for every new control (Release 27 rules).
- Tests: update the tests tied to the old layout (about 15 modules reference `utility_panel`,
  `navigation_buttons`, `narrative_panel`, the inventory, equipment and skill grids, or the minimap) where
  the contract changed; behaviour assertions stay.

### Phase 7 — Verification and release
- Captures at 1600×900 and 1280×720 in both themes, plus combat, Journal and tooltip states, compared
  with the mockup.
- New packaged switch `--smoke-test-release28` covering the new layout, transcript paging, notes and the
  tooltips. All existing smoke switches still pass.
- Fresh-context code review of the branch; docs (README, RELEASE_HISTORY, GAME_STATE_LEDGER for
  schema 22, HANDOFF); release as **Release 28**.

### Phase 7b — Proof screenshots
- Capture the finished build at 1600×900 (both themes, plus combat and tooltip states) into
  `docs/screenshots/`. Embed them in `README.md`, commit, and push `main` to GitHub after merge.

### Phase 8 — RPG Mega item icons (D5)
- Build `ui/assets/icons/rpgmega_manifest.json`, mapping every item catalog record (category, subtype,
  rarity tier) to an RPG Mega icon. Sources: weapon, armor, helmet, glove, boot, greaves, belt, shield,
  jewelry, loot, elixir, food, ingredient, book and achievement packs.
- Copy the mapped icons, downscaled to 128 px, into `ui/assets/icons/rpgmega/`.
- `item_icons.py` resolves through the new manifest. Rare and higher items prefer the more elaborate
  icons in a pack, as the SVG resolver does today.
- Remove the SVG set once nothing references it.
- Tests: every catalog record and every preset item resolves to an existing icon; resolution is stable
  across reloads; rarity tiers prefer higher-detail art; package size check.

### Phase 9 — Music by context
- Copy every track from `Untitled RPG/Assets/Audio/Music` and `Audio/Ambience` into
  `ui/assets/audio/<context>/`. Contexts: `battle`, `boss`, `travel_road`, `forest_wilderness`,
  `town`, `tavern_inn`, `exploration_cave`, `menu`, plus `day` and `night` variants where they exist.
- `ui/assets/audio/music_manifest.json` lists the track files for each context. Replacing a track
  means editing the manifest or swapping the file, with no code change.
- Initial mapping:

  | Context | Tracks |
  | --- | --- |
  | battle | combat_1–7 (rotated) |
  | boss | music_boss |
  | travel_road | music_menu |
  | forest_wilderness | music_forest_day / music_forest_night |
  | town | music_village_day / music_village_night |
  | tavern_inn | music_village_day (placeholder: no dedicated tavern track yet) |
  | exploration_cave | music_cave |
  | menu | music_menu |

- Ambience loops (forest, village, cave, rain) map by biome and weather.
- A `MusicController` on QtMultimedia (`QMediaPlayer` and `QAudioOutput`, already in PySide6) picks the
  context from game state: combat active → battle; then the current location biome; then time of day.
  It crossfades on change and never repeats the same battle track twice in a row.
- Settings gains Music volume, Ambience volume and Mute, saved in UI preferences. Audio failure is
  silent and non-fatal.
- Credits: SOURCES.md records no per-track creator or license, so `ASSET_CREDITS.md` marks these tracks
  "supplied as CC0; verify before public release".
- Tests: manifest coverage for every biome; context selection rules; no repeat of a battle track;
  settings round-trip; offscreen runs with audio disabled.

## 5. Risks

- **Fade and translucency in Qt:** the masked scroll area is the riskiest piece. Phase 4 starts with a
  spike that measures scrolling performance on a full history; if needed it falls back to a painted
  gradient overlay instead of a mask.
- **Model output:** speaker attribution (D8) depends on the model naming present NPCs correctly; the
  fallback keeps unattributed speech readable.
- **Test churn:** the layout change touches many UI tests; each change must trace to the new contract,
  never to getting green.
- **Bright location images:** unboxed narration relies on the dimming gradient; verify against all 95 images
  in the Phase 7 capture pass.

## 6. Other pages

Map, People, Character Sheet, Settings, Character Creation and the modal dialogs (rewards, crafting
result, level-up, option chooser) keep their layouts. They pick up the new frames, fonts and colours through the
shared theme tokens only. Each is checked in the Phase 7 capture pass.

## 7. Project plan update

`PROJECT.md` lists this redesign as **Phase 30 — Concept T dashboard** (plan Phases 1–7b),
**Phase 31 — RPG Mega item icons** (plan Phase 8) and **Phase 32 — Music** (plan Phase 9). The earlier
Phases 30–32 (hardware and final model, content catalogs, data location and backups) become 33–35.

## 8. Out of scope

- Changes to game rules.
