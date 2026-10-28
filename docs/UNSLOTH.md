# Unsloth Studio Integration

> **Providers:** Unsloth Studio is the primary external model server and LM Studio the
> secondary one (see [LM Studio (secondary provider)](#lm-studio-secondary-provider)).
> The bundled llama.cpp runtime uses the same `LocalModelClient`
> (`src/dd_simulator/local_model/`) without authentication or model loading. Every
> request contract and trust boundary below applies to all three.

Release and canonical workflow numbering are tracked separately in
`WORKFLOW_STATUS.md`. Release 23 adds no model-authored mechanics: item statistics
are deterministic application data. Unsloth Studio may later phrase optional item
descriptions, with a local fallback, but cannot set damage, armor, healing, value,
weight, durability, requirements, compatibility, or bonuses.

Release 20 merchant dialogue may continue through the People conversation path, but
merchant stock, eligibility, prices, barter discounts, inventory movement, and
currency changes are calculated and committed without an Unsloth Studio request.

Release 21 crafting also runs without an Unsloth Studio request. Recipe requirements,
skill and campaign-difficulty checks, material and tool consumption, output quality,
rarity, inventory placement, and Crafting XP are deterministic application logic.
The themed result popup reads the committed SQLite result and does not generate prose.

Release 22 only changes navigation and skill-progress presentation. Moving Campaign
management into Settings does not change model selection, loading, evaluation, or the
application-owned campaign-state boundary.

Release 23 adds one optional `character_creation_profile` request. The request includes
the user's World & Safety selections and explicit allowed-choice catalogs. The strict
response contains every non-World/Safety field; a single low-temperature retry repairs
format drift. Application code then checks exact fields, types, lengths, adult age,
catalog membership, unique skill/personality limits, and the existing draft validator.
Invalid output leaves the entire current form unchanged. Valid output still requires
the normal written review and explicit campaign-creation confirmation.

Campaign Name and Character Name use the existing three-option request. Appearance
requests explicitly instruct the model to follow world, tone, region, safety, and visual
direction. All work remains asynchronous and localhost-only.

## Unsloth Studio API boundary

Unsloth Studio serves loaded models (including GGUFs, through its bundled
`llama-server`) as an authenticated OpenAI-compatible API. The application uses it as
an optional, stateless writing assistant.

- **Base URL:** `http://localhost:<PORT>/v1`. Unsloth prints the actual endpoint and port
  when it starts; `unsloth studio -p 8888` pins the port. The application defaults to
  `http://localhost:8888/v1`, lets the user change the port in Settings, and rejects
  any non-local host.
- **Bind address:** Unsloth binds `127.0.0.1` by default. Do not start it with
  `-H 0.0.0.0` or `--secure` (Cloudflare tunnel) for this application; both expose the
  model beyond the local machine and are outside the localhost-only boundary.
- **Authentication:** every request sends `Authorization: Bearer sk-unsloth-…`. Create the
  key in Unsloth Studio under the avatar menu → **Settings → API** (shown as **Settings → API Keys** in Unsloth Desktop) → **Create**, and copy
  it immediately; Unsloth shows it only once and stores only a hash. The key is saved in
  the application configuration directory, never in campaign data, checkpoints, or
  diagnostic exports. A missing, revoked, or wrong key returns `401` (`Not authenticated`), which the
  application reports as an API-key problem rather than an offline server.
- **Endpoints used:**
  - `GET /v1/models` — model discovery; the `loaded` field identifies models in memory.
  - `GET /v1/models/{model_id}` and `GET /v1/props` — model and llama-server metadata
    (context length and similar fields) for Settings and evaluation reports.
  - `POST /v1/chat/completions` — every generation path, with `stream: false`.
  - `POST /v1/chat/count_tokens` — optional prompt-size measurement for evaluation.
- **Management routes (installed Unsloth Studio build):** model loading uses the
  management root (`http://127.0.0.1:<PORT>`, no `/v1`), with the same bearer key:
  - `POST /api/inference/load` — load a model. Body fields include `model_path`
    (for example `unsloth/Qwen3.5-4B-GGUF`), `gguf_variant` (for example `Q4_K_M`),
    `max_seq_length`, `cache_type_kv`, `n_parallel`, `n_batch`, `n_ubatch`,
    `gpu_memory_mode`, `gpu_layers`, `reasoning_budget`, `disable_vision`, and
    `llama_extra_args`.
  - `POST /api/inference/unload` — unload a model (`{"model_path": "..."}`).
  - `GET /api/inference/status` — the active load, including `requested_context_length`
    and `reasoning_budget`.
  - `GET /api/inference/monitor` — per-request token and speed entries (`entries`).

  These routes are used successfully by the local Agent Orchestrator against the
  installed Unsloth Studio build but are not part of Unsloth's public API reference.
  If a route is missing or rejected, the application reports the error and falls back to
  manual loading in Unsloth Studio.
- **Not used:** `/v1/responses`, `/v1/messages`, server-side tools (`enable_tools`), image,
  audio, and video endpoints. Server-side tools must stay disabled: the model must not
  gain Python, terminal, or web access from inside a game request.
- **Reference:** a running Unsloth instance publishes its interactive API reference at
  `/docs` and its schema at `/openapi.json` on the same port.

## Request flow

1. The user selects Randomize for body and height, face and features, clothing
   style, or the combined biography/backstory.
2. The application uses the explicit loaded model selected in Settings. If no choice
   has been saved, it prefers the model that `GET /v1/models` reports as `loaded`.
3. It sends the selected target plus a bounded snapshot of the current draft to
   `POST /v1/chat/completions`, requests three numbered plain-text choices, and validates
   the result locally. No `response_format` is sent for non-mechanical creation prose.
4. Unsloth Studio must return exactly three distinct, non-empty text options. Release
   26.8.1 also accepts simple option objects and exactly three numbered or bulleted
   plain-text choices from models that drift from the requested JSON shape.
5. A theme-aware chooser lets the user apply one option. Cancel leaves the
   field untouched. Cancelling a chooser never consumes or locks the Randomize control;
   the player can generate again until an option is selected.

Release 26.8.2 gives every creative field its own contract. Body choices require explicit
`Height:` and `Build:` details and reject unrelated scene prose. Campaign titles use the
same numbered-choice parser. Full campaign generation requests only `CAMPAIGN NAME:` and
`CAMPAIGN PREMISE:` labels while retaining safe JSON compatibility for older models. The
three-sample evaluation probes body, campaign-title, and campaign-detail generation.

Release 26.8.3 treats an existing campaign name as authoritative and requests only the
premise. Labeled and unlabeled premise prose are accepted; a short first line can provide
a title only when the name field is empty. Ordinary model prose entering Narrative &
Player Action is capped at 125 words across all semantic segments. The generated campaign
introduction has a separate 220-word cap.

Requests run on Qt's worker pool so the interface remains responsive. Existing
text is preserved if the server is offline, the API key is rejected, no model is loaded,
the request times out, or the response does not match the required shape. Release 26.8
requires a confirmed loaded model before the remaining Character Creation tabs are
unlocked.

## People dialogue

Release 17 routes People-tab written questions and all six suggested responses
through the same loaded-model selection used by other generation paths. Each request
contains only a bounded NPC/player/location snapshot: profile and voice, relationship,
important memories, the last eight conversation turns, active visible quest details,
current scene facts, and campaign content preferences.

The first attempt requests strict `speech` and `monologue` JSON. A rejected schema or
HTTP 400/422 compatibility response retries once without `response_format` and accepts
common wrapped field names or bounded plain dialogue. Any remaining failure commits no
conversation, relationship, memory, quest, or discovery change; the People page keeps
the written input visible and shows the user-safe Unsloth Studio error. Deterministic
fallback dialogue is used only when no narrator is configured, such as offline tests,
and is not silently substituted for a failed configured model.

## Trust boundary

Current form values are included as untrusted character data, not executable
instructions. The model cannot access the database and cannot commit game
state. Applying a suggestion only updates the corresponding in-memory field;
the established draft validator and atomic SQLite transaction remain required
to create the campaign.

## Local setup

1. Install Unsloth Studio and start it on a fixed local port, for example
   `unsloth studio -p 8888`. A model can also be served directly with
   `unsloth run --model <repo>:<variant>` (for example
   `unsloth/gemma-4-26B-A4B-it-GGUF:UD-Q4_K_XL`).
2. In Unsloth Studio, open **Settings → API** and create an API key.
3. In D&D Simulator, choose **Connect to Unsloth Studio** in Local AI Setup (or
   **Change Local AI Setup** in Settings), enter the port and the `sk-unsloth-…` key.
4. Select **Refresh Models** in Settings. Models reported by `GET /v1/models` appear;
   loaded ones are marked **Loaded and ready**.
5. For an unloaded model, choose **Load Selected Model**. Off the UI thread, the
   application unloads any other active model through `POST /api/inference/unload`,
   calls `POST /api/inference/load`, confirms the result through `GET /v1/models`
   (`loaded`) and `GET /api/inference/status`, saves the selection, and refreshes the
   list. Loading a large GGUF can take minutes; the request uses a long timeout.

Dropdown selection alone never loads a model. If the management routes are unavailable,
load the model manually in Unsloth Studio (its **Select model** dropdown or
`unsloth run`) and press **Refresh Models**. The saved explicit selection is used by all
generation paths and survives Restore UI Defaults.

## LM Studio (secondary provider)

LM Studio remains supported for existing setups and as an alternative server. Saved
`lm_studio` configurations keep loading unchanged.

- **Base URL:** `http://localhost:1234/v1`; no API key.
- **Discovery:** LM Studio's native `GET /api/v1/models` (its `loaded_instances` metadata
  identifies loaded models), falling back to `GET /v1/models`.
- **Loading:** **Load Selected Model** unloads other active instances through
  `POST /api/v1/models/unload`, then calls `POST /api/v1/models/load` and waits for
  `loaded` status. Native loading requires LM Studio 0.4 or newer; manual loading in
  LM Studio plus **Refresh Models** also works.
- **Setup:** start LM Studio's local server on port 1234 and choose **Connect to LM Studio**
  (listed after Unsloth Studio) in Local AI Setup.
- Some models route strict `response_format` output through an unsupported tool-call
  channel and LM Studio returns `Channel Error`; the compatibility retry below handles it.

## Release 26.8 structured-output compatibility

Unsloth Studio does not document `response_format` / `json_schema` support for
`/v1/chat/completions`, so strict schemas are treated as best-effort.

Creation options, character and campaign names, campaign premise, and opening prose do
not send strict `response_format` schemas. The system prompt demands compact JSON;
application code extracts ordinary message content or valid
`tool_calls[].function.arguments`, then enforces exact fields, types, option counts,
uniqueness, lengths, and word limits.

Mechanical action, combat, dialogue, and travel requests still attempt their strict
schemas first. HTTP 400/422, an ignored or rejected schema, a tool-call-only response,
or otherwise invalid structured output triggers one bounded request without
`response_format`. Once that compatibility retry is needed, the selected model remains
in plain-JSON mode for later mechanical requests in the same application session.
Parsing and deterministic state validation are identical in either mode; the model never
gains mutation authority.

## Release 18 evaluation

Settings can run three isolated probes against the selected model. The evaluator
does not receive a campaign snapshot and cannot commit game state. It records strict
schema success, compatibility retries, average latency, reported token counts and
completion rate, a small authority/continuity quality rubric, and context or memory
metadata when Unsloth Studio exposes them through `GET /v1/models/{model_id}` or
`GET /v1/props`. Prompt size can be measured with `POST /v1/chat/count_tokens` when
completion responses omit usage. The latest machine-readable and readable reports
are written to the configured `model-evaluations` directory. See
`RECOMMENDED_UNSLOTH_SETTINGS.md` for the initial baseline and interpretation rules.

## Non-combat player turns

Phase 8 also uses `POST /v1/chat/completions` for one structured non-combat turn
at a time. The request contains the player's action and a newly rebuilt bounded
snapshot with stable allowed target IDs. The response must contain ordered
narrative, monologue, and spoken segments, an enumerated state-change array,
quest notes, memory candidates, and exactly six suggested actions. A malformed
format receives one low-temperature repair
retry. Model prose is never interpreted as a database command.

Release 24 tightens the same contract: each segment must contain one semantic kind,
spoken dialogue uses ordinary double quotation marks, and segment text must not contain
Markdown. At the trust boundary the application removes stray backticks, normalizes
clear quote pairs, splits clearly mixed narration/dialogue, and uses narrative styling
for the non-dialogue portions. Model choice may affect how often malformed prose is
generated, but raw formatting tokens are no longer trusted by the UI.

Item contracts distinguish all owned inventory from owned unequipped items that
have a configured equipment slot. `equip_item` can target only the latter;
`examine_item` can target any owned item and does not consume it. Suggestions
that expose internal IDs or impossible equipment actions are removed and safe
fallbacks preserve exactly six player-facing choices.

Application code revalidates the parsed outcome independently and permits only
the documented non-combat operation allowlist. Invalid ownership, fields,
values, routes, resource limits, item rules, objectives, or clocks reject the
entire turn. Cancellation discards the response before the transaction, and a
database failure rolls back narration and state together.

## Combat narration and intent

Phase 11 continues the Phase 9 primary bounded combat request, with at most one strict-format
retry, after the player's numerical result has been calculated. The request contains the resolved player-action
summary, combatants, position, health, morale, environment, hazard, and an exact
per-enemy list of currently legal intents. The strict response contains only
ordered narrative/monologue/spoken segments and an enemy-ID-to-intent map.

Application code rejects unavailable combatants and intents outside the supplied
allowlist. Dice, attack modifiers, armor, damage, healing, resource costs,
ammunition, durability, conditions, movement, victory, defeat, and progression
never come from the model. If Unsloth Studio is unavailable or its result fails
validation, the combat turn uses deterministic fallback intent and text;
mechanical authority never moves outside SQLite-backed application code.

Spells and class abilities do not add a model-authored mechanics schema. The
application resolves the selected catalog action first, then supplies its
already-resolved summary through the existing combat narration request. The
model cannot invent actions, change costs, extend durations, select targets, or
alter any effect.

Generated encounter introductions may be phrased through the same bounded combat
narrator, but deterministic application data supplies the selected archetypes,
terrain, awareness, difficulty, and legal intents. The added `ability` intent is
accepted only when the active enemy snapshot owns a legal catalogued ability.
Negotiation, resistances, vulnerabilities, reinforcements, and rewards are never
model-authored or model-calculated.

## Quest boundary

Phase 12 does not introduce model-authored quest mechanics. Unsloth Studio may phrase
narrative, quest notes, and player-facing updates using the existing bounded turn
contract. Application code alone matches typed events to objective triggers,
increments counts, evaluates deadlines, changes lifecycle state, activates
follow-ups, and calculates or grants rewards. A model response cannot invent a
quest, rewrite an objective trigger, set a reward, or bypass validation.

## Travel boundary

Phase 13 may request one concise journey/arrival or camp paragraph after reading
bounded, already-selected route facts. The request contains no mutation schema.
It cannot choose a destination, open a route, alter distance or duration, change
stamina or recovery, set danger, trigger or suppress an encounter, advance the
clock, discover a location, or progress a quest. Generation runs on the Qt worker
pool and before the SQLite write transaction. Unavailable or malformed model
output uses deterministic local prose without changing the travel result.

## NPC dialogue boundary

Phase 14 resolves the NPC, relationship score, check type, visible d20 roll,
modifier, difficulty, outcome, memory, reputation, quest effects, and map
discoveries in application code. Unsloth Studio receives that bounded context only
to phrase one speech response and a short monologue. Its strict response has no
mutation fields. Missing, malformed, or unavailable model output falls back to
deterministic local prose, and generation runs on the Qt worker pool.
