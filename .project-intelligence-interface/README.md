# Project Dashboard

A single-folder, offline project intelligence dashboard you can drop into any Git repository. A small Python script reads your Git history and a few Markdown notes, writes a data snapshot, and `index.html` turns that snapshot into a developer control center: what the project is, where it stands, how it has evolved, what is happening inside it, and what it looks like.

Nothing is installed, nothing is served, and nothing leaves your machine. Open `index.html` with a double-click.

## Quick start

1. Copy this whole folder into your repository, for example to `docs/dashboard/`.
2. Edit `dashboard.config.json`: set `project.name` and point `paths` at your notes files.
3. Edit `data/curation.json` (start from `data/curation.example.json`): roadmap, decisions, pillars, screenshots.
4. Run the collector, from any directory:

   ```
   python docs/dashboard/refresh.py
   ```

   On Windows you can double-click `Refresh Dashboard.cmd` instead.
5. Open `index.html` by double-click. It works from `file://`, with no server and no internet.

Other modes:

| Command | What it does |
| --- | --- |
| `python refresh.py` | Rebuild `data/project.json` and `data/project-data.js`, and copy screenshots into `media/`. |
| `python refresh.py --check` | Validate the inputs and report counts. Writes nothing. |
| `python refresh.py --watch` | Rebuild whenever the notes, config or Git state change (polls every 5 seconds). Reload the browser after an update. Ctrl+C to stop. |

`index.html` reads `data/project-data.js`. `data/project.json` is the same snapshot as plain JSON for other tools.

## The interface

Five views, always reachable from the side rail (a bottom bar on narrow screens). Views and modules with no data hide themselves.

| View | What it shows |
| --- | --- |
| **Overview** | Project identity (name, stage flow, version, branch, HEAD, last update, working tree, banner art), development pulse, current focus, next milestone, health signals, recent commits, composition, major systems, open decisions, latest captures, AI activity or recent sessions, project facts. |
| **Development** | Totals, commit activity (per day, or per week for long histories), commit categories, additions vs deletions, most active areas (all time or last 30 days), repository composition, size on disk, sessions and AI activity, working tree, and a searchable, filterable commit history with per-file changes. |
| **Roadmap** | Progress ring, an interactive product-evolution timeline (the current milestone is marked *Now*), tests and associated commits per milestone, phases, and the completed archive. |
| **Intelligence** | Current state and in-progress work, next steps, open decisions, systems with their Git activity, pillars, health signals, grouped facts, plan coverage with search, rules and the source documents (long text opens in a side panel). |
| **Media** | The banner as a feature image and every capture in a masonry gallery with a keyboard-driven viewer. |

Keyboard: **Ctrl+K** (Cmd+K on a Mac) or **/** opens the command palette. It searches views, actions, milestones, decisions, systems, plan sections, captures, sessions, archive entries and commits, grouped by kind: arrow keys move, **Tab** jumps between groups, **Enter** opens. **1** to **5** switch views. Roadmap nodes take the arrow keys, Home and End; the capture viewer takes the left and right arrows, Home, End and Esc.

**Customize layout** (top bar, Overview only) lets you arrange the Overview cards: drag a card onto another, or use the arrow buttons on each card. Widths adjust automatically: each card has a preferred and a minimum width, cards share a row while they fit, and every row is stretched or squeezed to span the full page. The order is saved in this browser (local storage) per project; **Reset** restores the default, **Done** or Esc finishes.

**Themes**: the round swatch button in the top bar (or "Theme" in the command palette) switches between Project default, Forest Green, Light Blue, Track Gold, Orange, Purple and Aqua. Each theme sets the accent and tints the background layers; the choice is saved in this browser per project. `project.theme` in the config sets the starting theme.

Old links keep working: `#brief`, `#history` and `#numbers` open Overview and Development.

## What it reads

| Source | Used for |
| --- | --- |
| Git history of the repository | Commit list, activity, areas of the codebase, line counts, branch, nearest tag, working-tree changes. |
| Handoff file (Markdown) | "Current state", "In progress" and "Next steps". |
| Completed file (Markdown) | One milestone per heading, linked to commits. |
| Plan file (`.md` or `.docx`, optional) | A numbered list of plan sections with a status each. |
| Rules file (optional) | Shown under Intelligence as rules and constraints. |
| `data/curation.json` | Hand-written roadmap, decisions, pillars, phases, plan status, health signals, systems, screenshots, banner. |
| `data/sessions.json` | Session notes, optionally with AI model, provider, role and usage. |

Every input except Git itself is optional. A missing file, heading or list simply becomes empty data.

## `dashboard.config.json` reference

All paths in `paths`, `capturesFolder` and `banner` are relative to the repository root. Omitted keys use the defaults shown.

### `project`

Display information. Every key is optional except that `name` must be a nonempty string.

| Key | Default | Meaning |
| --- | --- | --- |
| `name` | `"Project"` | Title of the dashboard. |
| `subtitle` | `""` | One line under the title. |
| `description` | `""` | Short paragraph about the project. |
| `repository` | `""` | Link to the hosted repository. |
| `timezone` | `""` | IANA timezone used to show dates (for example `Europe/Berlin`); empty uses the viewer's. |
| `accent` | `""` | Accent colour as `#rrggbb`. Anything else is rejected. Text on accent fills switches between dark and light automatically. |
| `theme` | `""` | Default colour theme: `forest-green`, `light-blue`, `track-gold`, `orange`, `purple` or `aqua`. Empty or `default` uses `accent`. Viewers can still pick their own. |
| `version` | `""` | Version label shown in the identity area. When empty, the nearest Git tag is shown instead. |
| `stage` | `""` | Current stage label. The matching `flow` step is highlighted (the text before ` - ` is compared). |
| `flow` | `[]` | Ordered stage names, for example `["Idea", "Prototype", "Alpha", "Release"]`. |
| `facts` | `[]` | List of `{"label": "...", "value": "..."}` pairs. Both keys are required. Optional `group` collects facts under a heading (for example `"Engine"`, `"Build"`, `"Quality"`); optional `status` (`healthy`, `warning`, `danger`, `unknown`) adds a status icon. |

### Repository and notes

| Key | Default | Meaning |
| --- | --- | --- |
| `repoRoot` | `""` | Path from the dashboard folder to the repository root. Empty means "ask Git", which works when the folder is inside the repository. Set it (for example `"../.."`) if the dashboard lives outside the repo. |
| `paths.handoff` | `"HANDOFF.md"` | Handoff file. |
| `paths.completed` | `"COMPLETED.md"` | Archive of finished milestones. |
| `paths.rules` | `""` | Optional project-rules file. |
| `paths.plan` | `""` | Optional plan file (`.md` or `.docx`). |
| `handoff.currentState` | `"Current State"` | Heading text to read the current state from. |
| `handoff.inProgress` | `"In Progress"` | Heading text for work in progress. |
| `handoff.nextSteps` | `"Next Steps"` | Heading text for the next steps. Its bullet or numbered lines become the list. |
| `headingLevels.completed` | `2` | Markdown heading level (`##`) that starts a milestone in the completed file. |
| `headingLevels.plan` | `1` | Heading level that starts a plan section. For `.docx` it is the paragraph style `Heading<level>`. |
| `planHeadingPattern` | `""` | `.docx` only: a regular expression. Paragraphs matching it start a plan section instead of using styles. A named group `(?P<title>...)` becomes the section title. |

Heading matching is case-insensitive and works at any level. Any extra entry you add under `paths` (a key with a file name) that exists is also listed under the dashboard's sources.

Milestones are linked to commits first by any commit hash written in the milestone's heading or body, then by the `milestoneMatches` hints in `curation.json`.

### `content`

Counts of tracked files, shown as content numbers. A list of `{"label": "Guides", "glob": "docs/guides/*.md"}`. Default `[]`. Globs use `fnmatch` against repo-relative paths with forward slashes; `*` also matches `/`.

### `source`

Controls which tracked files count as first-party code in the line counts.

| Key | Default | Meaning |
| --- | --- | --- |
| `include` | `["*"]` | Glob patterns a file must match. |
| `exclude` | `[]` | Glob patterns that remove files again (for example `["vendor/*", "*.min.js"]`). |
| `languages` | `.py` Python, `.js` JavaScript, `.ts` TypeScript, `.css` CSS, `.html` HTML | Map of file extension to label. Only listed extensions are counted. Setting it replaces the default map. |

### Screenshots

| Key | Default | Meaning |
| --- | --- | --- |
| `capturesFolder` | `""` | A folder of images (`png`, `jpg`, `jpeg`, `gif`, `webp`, `svg`). Every image not already listed in `curation.json` becomes a capture. |
| `banner` | `""` | Path of a wide image shown behind the brief header. `curation.json` can override it with a title and caption. |

Images are copied into the dashboard's `media/` folder on refresh, so the folder can be zipped and shared on its own. Missing images are skipped, never fatal.

### `size`

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `true` | Measure the on-disk size of the whole repository folder. Set `false` to skip the scan on very large repositories. |
| `groups` | Git history (`.git`); Dependencies and caches (`node_modules`, `__pycache__`, `.venv`, `venv`, `.cache`, `build`, `dist`, `bin`, `obj`, `target`) | List of `{"label": "...", "match": ["name", ...]}`. A file goes to the first group whose `match` patterns equal any folder or file name in its path; everything else is "Project files". Symlinks and junctions are skipped. |

## Curation (`data/curation.json`)

Hand-written content that Git and your notes cannot provide. Copy `data/curation.example.json`, which shows every key with a short example. In brief:

- `roadmap`: items with `id`, `title`, `status` (`done`, `next`, `planned` or `gated`), optional `date`, `summary`, `tests` (list of names) and `side` (`true` draws the item smaller and keeps it out of the progress count).
- `decisions`: open questions as `{title, detail}`.
- `pillars`: `{name, text}` principles.
- `phases`: `{number, title, status}` plus an optional `commit`.
- `planStatus`: status per plan section number, `{"1": {"status": "implemented", "note": "..."}}`. Statuses: `implemented`, `partial`, `planned`, `design` (default).
- `milestoneMatches`: for milestones that cite no commit hash, words to look for in commit subjects, keyed by the exact milestone heading.
- `captures`: `{source, title, caption}` images; `banner`: one `{source, title, caption}` image.
- `health` (optional): build and project signals as `{label, value, status, detail}`. `status` is `healthy`, `warning`, `danger` or `unknown`; `value` and `detail` are optional. The dashboard adds two automatic signals of its own (last commit age and working tree).
- `systems` (optional): the major systems or features as `{name, status, summary, paths, tags}`. `status` is `stable`, `active`, `planned` or `blocked`. `paths` are globs (same rules as `content`) that attribute Git activity to the system: commits, lines changed, last touched and an 8-week trend. `summary`, `paths` and `tags` are optional.

Text fields accept simple Markdown: `**bold**` and `` `code` ``. A malformed roadmap item, decision, pillar, phase, plan status, health signal, system, fact status or accent colour stops the refresh with a clear message.

## Session notes (`data/sessions.json`)

A list of short records of work sessions. See `data/sessions.example.json`.

```json
{"date": "2026-01-21", "agent": "Who did it", "title": "Short title",
 "summary": "What changed and what remains.", "minutes": 45,
 "tokens": null, "toolCalls": null, "costUsd": null}
```

`date` (ISO `YYYY-MM-DD`), `agent`, `title` and `summary` are required. `minutes`, `tokens`, `toolCalls` and `costUsd` are optional nonnegative numbers or `null`.

Optional AI fields, for AI-assisted projects:

```json
{"model": "Claude Opus 4.6", "provider": "Anthropic", "role": "Implementer",
 "local": false, "commits": ["c374ca2", "792e103"]}
```

`model`, `provider` and `role` (for example planner, implementer, reviewer) are strings; `local` is `true` for a locally run model and `false` for an API; `commits` lists the commit hashes the session produced. When any session carries these fields, the dashboard shows an AI activity module (models and agents with their roles, sessions, tokens, tool calls, API cost and session time) and links sessions to their commits. Only recorded numbers are summed; nothing is estimated.

## Example: a game project

Nothing in the template is game-specific; facts, health signals and systems carry it. In `dashboard.config.json`:

```json
"project": {
  "name": "Ember Hollow", "subtitle": "A cozy dungeon-crafting game", "version": "0.7.2-playtest",
  "stage": "Vertical slice", "flow": ["Prototype", "Vertical slice", "Alpha", "Beta", "Launch"],
  "facts": [
    {"label": "Engine", "value": "Godot 4.4", "group": "Engine"},
    {"label": "Renderer", "value": "Forward+", "group": "Engine"},
    {"label": "Targets", "value": "Windows, Steam Deck", "group": "Build"},
    {"label": "Build type", "value": "Debug, nightly", "group": "Build"},
    {"label": "Playtest", "value": "Round 3 open", "group": "Quality", "status": "healthy"}
  ]
},
"capturesFolder": "docs/screenshots",
"content": [{"label": "Scenes", "glob": "scenes/*.tscn"}, {"label": "Shaders", "glob": "*.gdshader"}],
"source": {"languages": {".gd": "GDScript", ".gdshader": "Shader", ".cs": "C#"}}
```

and in `data/curation.json`:

```json
"health": [
  {"label": "Frame time", "value": "14 ms on Steam Deck", "status": "warning", "detail": "Target is 11 ms."},
  {"label": "Unit tests", "value": "212 passing", "status": "healthy"}
],
"systems": [
  {"name": "Combat", "status": "active", "paths": ["scripts/combat/*"], "tags": ["hitboxes", "enemy AI"]},
  {"name": "Crafting", "status": "stable", "paths": ["scripts/crafting/*"]},
  {"name": "Save system", "status": "planned"}
]
```

## Empty sections hide themselves

You only fill in what you have. A dashboard with just Git history and a handoff shows just those parts; roadmap, decisions, systems, health, plan, captures, content numbers and sessions appear only once they contain data. The Roadmap and Media views leave the navigation entirely when they would be empty.

Existing configurations keep working unchanged: every field added in this version is optional.

## Demo data

If `data/project-data.js` is missing, `index.html` falls back to `examples/demo-project-data.js` (the fictional "Sample Project") and shows a demo marker, so a fresh copy of the folder is never blank. Run `python refresh.py` to replace it with your own data. Demo screenshots live in `examples/media/` and can be deleted along with `examples/` once you no longer want the fallback.

## Optional notes

- **Git.** Generated files (`data/project.json`, `data/project-data.js`, `media/`) are ignored by the provided `.gitignore` because `refresh.py` rebuilds them. Remove those lines if you want teammates to open the dashboard without running Python. Your own `data/curation.json` and `data/sessions.json` are worth committing. Changes under the dashboard folder are excluded from the working-tree list, so refreshing does not make the repository look dirty.
- **Engines and tools that import every folder.** Some tools scan all folders in the project and would try to import the dashboard's images and scripts. Tell them to skip it, for example Godot: add an empty `.gdignore` file to the dashboard folder; Unity: folders whose name ends in `~` are ignored, so name the folder `dashboard~`.

## Requirements and privacy

- Python 3.10 or newer (standard library only) and Git on your `PATH`.
- Any modern browser to view `index.html`.
- Everything is local. The collector makes no network calls, the page loads no external scripts, fonts or images (icons are an inline sprite, fonts are the system's), and the data never leaves your machine unless you share the folder yourself.
- Motion respects `prefers-reduced-motion`: entrance animations, chart growth, count-ups and smooth scrolling are switched off.
