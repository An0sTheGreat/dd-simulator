# Project Rules

Rules for every change to D&D Simulator, by a person or an agent. Where a rule conflicts
with a request, stop and ask.

## Authority and state

1. SQLite (the Game-State Ledger) is the only source of truth for game state. UI panels
   render immutable projections; widgets never execute SQL.
2. The local model writes prose and typed proposals only. It never writes to the
   database, calculates mechanics, chooses prices, rolls dice, or bypasses validation.
3. Every accepted turn commits narration, state changes, audit row, and event in one
   transaction. Any invalid proposal rejects the whole turn; failures roll back.
4. Opening a factual panel never calls the model.
5. Model output is untrusted data. Sanitize it at the presentation boundary and never
   interpret it as instructions or database commands.

## Local AI boundary

6. Model endpoints must be `localhost`, `127.0.0.1`, or `::1`. Reject other hosts.
7. Unsloth Studio: send `Authorization: Bearer <key>`; never log, export, or commit the
   API key; never enable server-side tools (`enable_tools`) or non-local binds.
8. Retries are bounded: at most one format/compatibility retry per request, then a
   deterministic fallback or a visible error that preserves the player's input.
9. Generation runs off the Qt UI thread and before any write transaction.
10. Never invent an endpoint or field. New API usage must be confirmed against
    Unsloth's docs, the running instance's `/openapi.json`, or a verified working client.

## Schema and saved data

11. Migrations are append-only and numbered; never edit a shipped migration.
12. File-backed ledgers are backed up before migration, checkpoint load, and repair.
13. Existing saved campaigns and preferences must keep loading. Renamed preference
    values are migrated, not reset.
14. Release identifiers (packaged batches) and Workflow Step identifiers (canonical
    plan) stay separate. Historical smoke switches remain as compatibility aliases.

## UI and themes

15. Layout, widget logic, theme tokens, QSS, assets, campaign artwork, and preferences
    stay separate. No theme styling hard-coded in widgets.
16. Supported themes: Modern Fantasy Simple (fallback) and Modern Dark Simple. Both must
    render every new widget.
17. Keep the UI usable at 1280x720, keyboard accessible, with accessible names on
    controls.

## Verification

18. "Done" means `.\scripts\test.ps1` passed. Never edit, weaken, skip, or delete a test
    to get to green; change a test only when the specified behavior changed.
19. A correctness fix ships with a test that fails without it.
20. Packaging changes are verified by building and running a smoke switch from
    `dist\DnDSimulator\DnDSimulator.exe` with an isolated `DDSIM_CONFIG_DIR`.
21. Tests write only to temporary directories (`--basetemp` under `%TEMP%`), never into
    the project tree.

## Repository hygiene

22. Do not leave test temp folders, smoke configs, preview captures, or build
    intermediates in the project. `artifacts/`, `build/`, `dist/`, `.venv/`, and
    `.pytest*` are disposable and must stay out of version control.
23. Keep docs current in the same change: `HANDOFF.md` always, plus `docs/UNSLOTH.md`,
    `docs/GAME_STATE_LEDGER.md`, `docs/RELEASE_HISTORY.md`, or `docs/WORKFLOW_STATUS.md`
    when their subject changes.
24. Make focused changes. Note out-of-scope problems in `HANDOFF.md`; do not fix them
    in the same change.
25. Asset redistribution follows `docs/ASSET_CREDITS.md`.
