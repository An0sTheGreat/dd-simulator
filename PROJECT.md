# Project

## Project Goal

Deliver a Windows desktop, local-first, single-player tabletop role-playing game in which
a local language model narrates while application code and a SQLite Game-State Ledger
own every rule, roll, and persistent fact.

The system should:

- Run entirely on the player's machine, with the local model served by the bundled
  llama.cpp runtime or by Unsloth Studio's authenticated localhost API.
- Turn free-form player input into bounded, validated, atomically committed game turns
  covering exploration, dialogue, combat, travel, quests, commerce, crafting, and
  progression.
- Let the model write prose and typed proposals only; application code validates and
  commits every state change.
- Preserve the player's work under failure: invalid model output rejects the whole turn,
  database errors roll back, schema migrations and restores create backups first, and a
  damaged ledger opens an in-memory recovery session without overwriting the original.

## Target Project

`Y:\Games\D&D Simulator\project` — Python 3.12+ / PySide6 package `dd_simulator`
(`src/dd_simulator`), tests in `tests/`, PowerShell scripts in `scripts/`, PyInstaller
spec `DnDSimulator.spec`, packaged build in `dist\DnDSimulator`.

## Authoritative Supporting Documents

- `PROJECT_RULES.md` — rules every change must follow.
- `HANDOFF.md` — current verified state and the next concrete steps.
- `docs/UNSLOTH.md` — Unsloth Studio API boundary and all model request contracts.
- `docs/GAME_STATE_LEDGER.md` — SQLite schema history and persistence boundaries.
- `docs/DECISIONS.md` — confirmed and open decisions.
- `docs/WORKFLOW_STATUS.md` — Release versus canonical Workflow Step status.
- `docs/RESOURCE_MAP.md` and `docs/reference/` — the original design documents (Main
  instructions, Adventure Reference Guide, Application Architecture and Setup Guide,
  UI Implementation Instructions, Project Workflow).
- `PROJECT.md` (this file) — the development plan.

These documents define the project requirements, implementation constraints, architecture decisions, and phased work plan.

## Existing Work

Release 27 (package version 0.27.0, database schema 21) is implemented and packaged.
Canonical Workflow Steps 1–19 are complete; Releases 20–27 are gameplay and presentation
expansions. Implemented and covered by the pytest suite and packaged smoke tests:

- First-run Local AI Setup: bundled CPU/Vulkan llama.cpp with a pinned, checksum-verified
  Qwen3-4B download, existing-GGUF selection, and an external OpenAI-compatible server
  mode (currently the former local-server client; see Phase 29).
- SQLite ledger with 21 append-only migrations, foreign keys, WAL, integrity checks,
  checkpoints, replay checksums, safe repair, and recovery backups.
- Character creation (D&D 5E point-buy, class hit dice, validated generated suggestions),
  campaign generation, and the preset *The Last Orrery of Sol*.
- Structured non-combat turns, deterministic combat with spells/abilities and enemy
  archetypes, quests with ordered gates and rewards, map travel and camping, NPC dialogue
  with social checks, merchants and bartering, crafting, levels 1–20, tiered loot,
  Visual Registry, model evaluation, diagnostics export, two themes, accessibility checks.

Do not reimplement completed work unless current validation demonstrates that it is incomplete, incorrect, or regressed.

## Remaining Work

Use the project’s development plan as the authoritative source for phase numbering, scope, acceptance criteria, and gates.

### Phase 28 — Version control and verification baseline

Put the project under version control so later phases are reviewable and reversible.

Required behavior:

- `git init` the project with a `.gitignore` covering `.venv/`, `build/`, `dist/`,
  `artifacts/`, `.pytest*`, `__pycache__/`, `*.egg-info/`, logs, and any API-key file.
- Commit the cleaned Release 27 tree as the baseline before Phase 29 code changes land.
- Record the passing test count and packaged smoke result in `HANDOFF.md`.

### Phase 29 — Unsloth Studio client migration

Replace the former external local-server client with an Unsloth Studio client so the code
matches `docs/UNSLOTH.md`.

Required behavior:

- Rename the `dd_simulator.lm_studio` package, `LMStudioClient`, `LMStudio*Error`
  classes, the `lm_studio` setup mode, and user-facing strings to Unsloth equivalents;
  migrate a saved `lm_studio` mode preference to the Unsloth mode instead of resetting it.
- Default base URL `http://localhost:8888/v1`, port editable in Local AI Setup/Settings,
  non-localhost hosts still rejected.
- Send `Authorization: Bearer <key>` on every request; collect the `sk-unsloth-…` key in
  setup, store it only in the configuration directory, exclude it from logs and
  diagnostics exports, and report `401` as an API-key error.
- Discover models with `GET /v1/models` (`loaded` field); load, unload, and confirm with
  `POST /api/inference/load`, `POST /api/inference/unload`, and
  `GET /api/inference/status`, falling back to manual loading when those routes fail.
- Keep the strict-schema-then-plain-JSON compatibility retry and all trust boundaries
  unchanged; read model metadata from `GET /v1/models/{id}` / `GET /v1/props`.
- Update `tests/test_lm_studio.py` and every affected test for the new client, add tests
  for the auth header, 401 handling, key redaction, and preference migration; full suite
  green; rebuild and pass `--smoke-test-release27` from `dist`.

### Phase 30 — Target hardware profile and final model selection

Resolve the open decision on target hardware and the preferred model/quantization.

Required behavior:

- Record the target GPU, VRAM, RAM, and storage profile in `docs/DECISIONS.md`.
- Run the in-app three-sample evaluation for Qwen3-4B (bundled runtime) and the Gemma 4
  E4B candidate (Unsloth Studio) on that hardware.
- Choose the recommended models from the evaluation acceptance rules in
  `docs/RECOMMENDED_UNSLOTH_SETTINGS.md` and update setup recommendations accordingly.

### Phase 31 — Content catalog expansion

Expand the deterministic content catalogs beyond the Phase 11 starter set.

Required behavior:

- Expanded spell catalogs per class, with deterministic costs, effects, and level unlocks.
- Campaign-authored enemy archetypes loadable from preset data.
- Catalog validation tests in the style of the existing preset validation.
- No new model-authored mechanics.

### Phase 32 — User data location and backup retention

Resolve the open decision on campaign data location and backup retention.

Required behavior:

- Decide and document the final campaign data location.
- Bound the growth of `backups/` (migration, checkpoint, recovery, repair) with a
  documented retention policy that never deletes the newest verified checkpoint.
- Tests proving retention never removes a backup needed for recovery.

## Constraints

- Preserve verified working behavior unless a current requirement or regression requires a change.
- Use supported interfaces and documented integration points.
- Do not introduce unrelated features or architectural changes.
- Do not expose or log secrets, credentials, protected data, or sensitive source content.
- Do not trust unverified external or generated claims as proof.
- Enforce defined scope boundaries.
- Keep retries, loops, and automatic recovery bounded.
- Preserve path-independent or environment-independent behavior when required.
- Make focused changes and preserve unrelated work.
- SQLite remains the only authority for game state; the model never writes to it.
- Model endpoints stay localhost-only; never enable Unsloth server-side tools.
- Schema migrations are append-only; existing saved campaigns must keep loading.

## Completion Criteria

The project is complete when:

- All required phases satisfy their acceptance criteria.
- All required deterministic tests or validation scenarios pass.
- Live, destructive, or environment-dependent tests remain explicitly controlled where applicable.
- Required documentation is sufficient for setup, operation, testing, and troubleshooting.
- No credential, sensitive-data, or unintended path leak exists.
- The full relevant validation suite passes.
- No known blocking defect remains.
- The final implementation matches the authoritative project documentation.

## Execution Guidance

Before beginning implementation:

1. Read this file and all authoritative supporting documents completely.
2. Determine the current verified state before changing code.
3. Identify the first incomplete or failed phase.
4. Work only on that phase unless a dependency requires a bounded prerequisite fix.
5. Validate the work against that phase’s acceptance criteria.
6. Update `HANDOFF.md` with the verified result before stopping.
7. Do not mark work complete based only on historical claims.
