# Handoff

Last updated: 2026-10-27

## Current state

- **Release 27 + Phase 29** merged into `main` and pushed to
  `github.com/An0sTheGreat/dd-simulator` (private). Package version `0.27.0`, database schema **21** on `main` (**23** on `ui-concept-t`).
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
| (this commit) | 4b: `ui/widgets/scene_view.py` — `SceneView` (painted location art + overlay, `NavTabs` with Journal, title and chips, conversation placeholder), `QuestProgressCard`/`EncounterCard` (swapped by `set_combat`, D2), `ChoiceGrid` (keys 1-6, ACT, NarrativePanel signals and pending/cancel/retry); QSS block in both themes; preview `scripts/preview_scene.py`; not yet wired in |

Open items: quest reward chips show XP and gold only (`QuestListItemView.reward_summary`; reputation is not projected); combat choices target the first active enemy by initiative (no target picker yet); `InventorySlotView` needs a bag `position` for Phase 6 drag and drop; the paperdoll's ATK figure needs a projected player attack bonus (`PaperdollPanel(attack_bonus=...)`; combat computes it from equipment); turn notes are not yet written for combat ammo, potion and HP changes or for quests started from dialogue; the Phase 1 source frames include identical placeholder images (panel = tooltip = quest tracker).
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
