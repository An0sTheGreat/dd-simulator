# Handoff

Last updated: 2026-10-27

## Current state

- **Release 27 + Phase 29** merged into `main` and pushed to
  `github.com/An0sTheGreat/dd-simulator` (private). Package version `0.27.0`, database schema **21** on `main` (**24** on `ui-concept-t`).
- **Local AI providers:** bundled llama.cpp (recommended), existing GGUF, **Unsloth
  Studio (primary external server)**, **LM Studio (secondary)**. All share
  `dd_simulator.local_model.LocalModelClient`, selected by `provider=`
  (`"openai"` for llama.cpp, `"unsloth"`, `"lm_studio"`).
- **Tests:** 301 passed, 0 failed, about 2 min 20 s (`.\scripts\test.ps1`).
- **Packaged build** rebuilt from `phase-29-unsloth`. These smoke switches exit 0:
  `--smoke-test`, `--smoke-test-release27`, `--smoke-test-release19`,
  `--smoke-test-preset-campaign`, `--smoke-test-character-creation`.
  `--smoke-test-release18` exits 18 on `main` too (Known issue 2).

## In progress: Concept T redesign (branch `ui-concept-t`, not pushed)

Plan: `docs/UI_REDESIGN_PLAN.md` (approved 2026-10-27; D5 icons from `Project Resources/assets`, D7 keep 320 cap).

| Commit | Phase |
| --- | --- |
| `06e4772`, `15b05f9` | Plan, PROJECT.md Phases 30-32, reference mockups in `docs/design/` |
| `ddee2bb` | 1: codex frames, markers, portrait fallbacks, Oxanium, theme tokens, packaging |
| `a24cf02` | 2a: schema 22 `narrative_messages.speaker_npc_id`; dialogue and turn speakers |
| `2dd587a` | 2b: schema 23 `turn_notes`; per-turn note tags; transcript pages of 40 whole turns |
| `d440dd8` | 2c: skill descriptions, abilities/spells split with status, full inventory list, portrait path |
| `f328f11` | 3a: `power_icon_manifest.json` maps 8 skills + 44 catalog actions to CraftPix icons; `scripts/import_power_icons.py` copies them at 128 px to `ui/assets/icons/powers/`; resolver `ui/power_icons.py`; contact sheet `docs/design/power-icons.png` |
| (this commit) | 3b: `ui/widgets/codex_character.py` — `CharacterStrip`, `PaperdollPanel` (an `EquipmentGrid` subclass, nine slots around the portrait), `SkillDetailList`; QSS block at the end of both themes; preview `scripts/preview_codex_left.py`; not yet wired in |
| (p4a commit) | 4a: `ui/widgets/conversation_view.py` `ConversationView` (narrator, player, NPC boxes, note tags, top fade by `QGraphicsOpacityEffect` mask on the viewport, paging via `older_requested`/`prepend_messages`, 3 s new-turn emphasis, reduced motion); QSS block `Concept T: conversation` in both themes; preview `scripts/preview_conversation.py`; not yet wired in |
| (this commit) | 4b: `ui/widgets/scene_view.py` — `SceneView` (painted location art + overlay, `NavTabs` with Journal, title and chips, conversation placeholder), `QuestProgressCard`/`EncounterCard` (swapped by `set_combat`, D2), `ChoiceGrid` (keys 1-6, ACT, NarrativePanel signals and pending/cancel/retry); QSS block in both themes; preview `scripts/preview_scene.py`; not yet wired in |
| `b42d498` + this commit | 5: shared tooltip cards (item with comparison, ability, spell, skill, response); one card at a time; edge placement |
| (this commit) | 6a-2 part 1: `PlayerSummaryView.attack_bonus` from `state.combat.player_attack_bonus` (shared with combat) on the paperdoll caption; quest reward chips add faction reputation ("LORD ARIC +1"); target picker (D2): with two or more active enemies an `EncounterCard` row click, Enter or Space picks `choice_grid.target_id` (QSS `targetSelected` in both themes), kept across `set_combat` and dashboard reloads while that enemy is active, used by attacks and PowersCard casts. Still owed: Journal page (D1), repointing the two `test_release_twenty_five` tests, `tests/test_concept_t_window.py` |
| (this commit) | 6a-3 part 1 (D1): `JournalPage` in `navigation_pages.py` (quest list, `EventLogPanel`, `RecentEventsPanel`); `_reload_dashboard` keeps the event filter and scroll (latest on new events); `capture_concept_t.py` also grabs `journal-<theme>.png`; `tests/test_concept_t_window.py` started. Still open: repoint the two `test_release_twenty_five` tests and delete `UtilityContentPanel`; the window tests (regions, free-text turn, older page, combat, cast target, Back targets, splitter persistence) are done in `tests/test_concept_t_window.py` |
| (this commit) | 6a-3 part 2: `test_release_twenty_five` inventory and choice-tooltip tests repointed at `InventoryCard` and `ChoiceGrid`; `UtilityContentPanel` deleted with its imports and QSS (`#inventoryUtilityPage`, `#inventoryUtilityScroll`, `#inventoryEquipmentSurface`); Journal quest column framed (`journalQuestPanel`, QUESTS) and `QuestListWidget` stretches only occupied columns; `textRole="system"` events use `text_secondary` in both themes. Still open: the remaining `tests/test_concept_t_window.py` window tests (regions, free-text turn, older-page loading, combat, PowersCard cast, Back targets, splitter persistence) |
| (this commit) | Review fix 2: schema 24 nullable `turn_notes.sequence`; `claim_turn_notes` records the turn's last message sequence, and the projection attaches notes to that message (NULL falls back to the turn's last message), so a People exchange no longer re-homes the action's notes under the NPC reply. Review fixes 1 and 3-6 are still owed |
| (this commit) | Review fixes: 1 FIXED (game and model text in scene, codex, quest and event labels is `PlainText`; tooltips go through `convertFromPlainText`), 3 FIXED (item refresh keeps the paperdoll ATK), 4 FIXED (journal `event_filter` saved, restored, reset to 0), 5 FIXED (turn-note isolation pinned by file-backed tests), 6b FIXED (unused `INVENTORY_PAGE_SIZE` removed). 6a: not reproducible: every `_apply_resource_change` path rejects a zero delta; no change made. Fix 2 above |
| (p7 commit 1) | 7 part 1 (1280x720): `CodexColumn` scales `PaperdollPanel.set_scale` and `InventoryCard.set_scale` (0.6-1.0) to the column height; `SkillDetailList` is a scroll area that takes the paperdoll's height; scene cards sit in `sceneCardScroll` (width 45% of the scene, 240-340) and the conversation keeps 150 px; location title wraps; `capture_concept_t.py --size --scale --pages`; test `test_dashboard_fits_1280x720_at_150_percent_font`. Still clipped at 1280 px: header campaign title, nav tabs and clock, scene chips, the strip's Experience caption. Not started: contrast script, Release 28 bump and smoke switch, `docs/screenshots/` set |
| (p7 commit 2) | 7 part 2 (elision): `ElidedLabel(tooltip_on_self=)` sizes to its full text and re-elides on font change; `ElidedButton` elides inside its padding (nav tabs); header ornaments shrink to 0 before the campaign title elides; clock, scene chips and strip resource captions elide with tooltips; window buttons `padding: 0`; test `test_no_dashboard_text_is_cut_off_at_1280x720_and_150_percent`. At 150% the tabs elide hard (PEOPLE shows only "…"). Not started: contrast script (`scripts/check_scene_contrast.py`), Release 28 bump and smoke switch, `docs/screenshots/` set |
| `afd6a6f`, `928b07d`, (this commit) | 7 polish: `scripts/check_scene_contrast.py` (95 location images, both themes, brightest 5% of the 45-80% band vs the narrator colour; exit 1 below 4.5:1): worst before 3.87:1 high_fantasy / 4.45:1 modern_proof (castle_daylight), after a 45% `OVERLAY_STOPS` stop 5.61:1 / 6.48:1; `tests/test_scene_contrast.py` checks the 5 brightest. Power rows elide to the column viewport (`_clipped_texts` counts viewport clipping). Nav tabs share one width cap and go `compact` (narrower QSS padding) when they do not fit; `ElidedButton` minimum fixed. Elided labels and buttons use the full text as accessible name; the clock name is its text, "Day and turn" its description |
| (p7 release commit) | Release 28: version 0.28.0, header "RELEASE 28", `--smoke-test-release28` (regions, demo conversation, Journal, item and ability tooltip cards, `older_messages`), docs (RELEASE_HISTORY, README, PROJECT.md); packaged build passed the six smoke switches. Still owed: `docs/screenshots/` and README screenshots |
| (screenshots commit) | Release 28 README screenshots: `capture_concept_t.py --set readme` writes six 1280 px PNGs to `docs/screenshots/` (adventure fantasy and dark, combat with two enemies, item tooltip with equipped comparison composited from the card window, Journal, character sheet) and README gets a Screenshots section. Known look issues (src untouched): Journal event log and recent events sit at the bottom of tall empty panels; the quest bar label overlaps its fill; the character sheet combat summary values run together ("42 / 4215"). |
| `977969c`, `36c7793`, `b824867`, `2e558b5`, (this commit) | Release 28 final fixes: Character Sheet Combat Summary in five equal-stretch columns (10 px gutter); Journal event log and recent events anchored to the top; quest count beside the progress bar (`questProgressLabel`, both themes); `ConversationView.older_load_failed()` called by `_load_older_messages` on no service/campaign or `GameStateError`; 150% font tests use the `large_font_window` fixture (reset in `finally`); contrast test covers all 95 images, 98th-percentile band luminance, `NARRATOR_COLOR` regex `(?<![-\w])color:` (worst 5.40:1 fantasy, 6.25:1 dark, `OVERLAY_STOPS` unchanged); `sync_character_combat_catalog` clamps `current_uses`; Journal and character-sheet README screenshots recaptured. Not fixed: a saved `current_uses` of NULL stays NULL when the catalog adds a maximum. |
| (p8 commits) | Phase 8 item icons: `item_icon_manifest.json` maps all 1,686 catalog records to 1,367 CraftPix paintings (128 px, `ui/assets/icons/library/`, +31 MB; SVG set and atlas removed, -7.4 MB) via `scripts/build_item_icon_manifest.py` (keyword, then subtype pools; icons ranked by PNG size as a detail proxy, records by tier) and `scripts/import_item_icons.py`. `item_manifest.json` keeps only semantic fields. Owed: G3 contact sheet `docs/design/item-icons.png` + visual review of pool choices, G4 packaged smoke. |

Open items: `InventorySlotView` needs a bag `position` for Phase 6 drag and drop; turn notes are not yet written for combat ammo, potion and HP changes or for quests started from dialogue; the Phase 1 source frames include identical placeholder images (panel = tooltip = quest tracker); `CommerceHoverEntry.enterEvent` (navigation_pages.py) lacks the rebuild-while-visible guard added to the inventory and skill hosts.
Icon library (28 supplied CraftPix packs + RPG Mega gap packs): `Y:/Games/D&D Simulator/Project Resources/assets`.

## Phase 29 summary (branch `phase-29-unsloth`)

| Commit | Change |
| --- | --- |
| `02a04c2` | Pure rename `lm_studio` → `local_model`, `LMStudio*` → `LocalModel*` |
| `f52b859` | Unsloth Studio mode (superseded in part by the next commit) |
| `5010fd6` | LM Studio kept as secondary provider; per-provider client behavior |
| `123c031` | Docs: Unsloth primary, LM Studio secondary |
| `18aaf8f` | Review fixes: setup without a loaded model, redirects refused, quiet status probe |

- Unsloth: `http://127.0.0.1:<port>/v1` (default 8888), `Authorization: Bearer
  sk-unsloth-…`, key in `preferences.json` only (`repr=False`; not in logs, errors, or
  the diagnostics ZIP), 401 → `LocalModelAuthenticationError`, discovery via
  `GET /v1/models` `loaded`, load and unload via `/api/inference/load|unload`, best-effort
  `context_length` from `/api/inference/status`.
- LM Studio: unchanged behavior (port 1234, native `/api/v1/models`, `loaded_instances`,
  native load and unload). Saved `lm_studio` setups keep loading as LM Studio.
- Model preference is stored per mode: `"unsloth"` for Unsloth, `"lm_studio"` for
  LM Studio and llama.cpp (as before).
- The fresh-context review returned APPROVE. Findings 1–3 were fixed in `18aaf8f`, each
  with a test that fails without its fix. Findings 4–6 were accepted (see Known issues).

## Known issues

1. **Manual gate still owed:** load a model and play a turn against a live Unsloth
   Studio with a real key, and against LM Studio. It is unconfirmed that Unsloth accepts
   a `/v1/models` id as `model_path`; if not, the server's error detail is shown.
2. **Pre-existing:** `--smoke-test-release18` exits 18 on a fresh config on `main` as
   well. It expects a model client although Release 26.9.4 made a configured local AI
   mandatory. Give the smoke a configured mode or retire it.
3. If `is_model_loaded()` itself raises while `action_resolver.py` or
   `dialogue_narrator.py` handles a failed request, that error escapes the `except`
   block (pre-existing pattern).
4. An empty `/v1/models` list now yields "0 loaded" in Settings instead of raising
   "no model is loaded" (llama.cpp and LM Studio fallback paths).
5. `LocalModelClient`'s default `base_url` for `provider="openai"` uses port 8888; every
   call site passes an explicit URL, so this is cosmetic.
6. `tests/test_release_twenty_seven.py` export test only proves the key is absent from
   the ZIP; the real leak guard is
   `test_rejected_key_raises_authentication_error_without_the_key`.
7. `docs/reference/` keeps the original architecture guide under its original filename.
8. `vendor/llama_cpp` binaries are committed (largest 50 MB); consider Git LFS.
9. After copying the project anywhere, rebuild `dist` rather than copying it (an earlier
   copy renamed the packaged `icons` folder and crashed startup).

## Testing notes

- `tests/conftest.py` closes leftover top-level widgets after each test; without it the
  suite took ~29 minutes. It must call `processEvents()` first, because several panels
  use `QTimer.singleShot(0, self.method)` without a context object.
- One module while iterating: set `$env:QT_QPA_PLATFORM = 'offscreen'` and run
  `.venv\Scripts\python.exe -m pytest tests\test_local_model.py`.
- `scripts\build.ps1` fails under PowerShell 5.1 when its output is redirected with
  `2>&1` (PyInstaller INFO lines on stderr). Run it plainly, or call
  `.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean DnDSimulator.spec`.

## Next steps

1. Run the manual gate (Known issue 1).
2. Phase 30: target hardware profile and final model selection (PROJECT.md).
