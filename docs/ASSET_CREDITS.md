# Release 26.7 Asset Credits and Distribution Notes

Current packaging note: the Default theme and every Default-only runtime derivative
listed below have been removed from the application. The entries remain as historical
source attribution; supplied files under Project Resources are unchanged.

Release 24 uses only assets currently present under
`Project Resources/dnd_ui_source/assets`.

## CraftPix item icons

- Source: the owner's CraftPix icon library under `Project Resources/assets/items/<theme>/`
  (catalog skill and spell records use `Project Resources/assets/skills/<class>/`).
- Runtime copies: the icons listed in the `sources` section of `item_icon_manifest.json`,
  downscaled to 128 px PNGs beneath `src/dd_simulator/ui/assets/icons/library` by
  `scripts/import_item_icons.py`; `scripts/build_item_icon_manifest.py` maps catalog records.
- Supplied terms: CraftPix free license (https://craftpix.net/file-licenses/); use in the
  game is permitted; do not redistribute, resell, or reupload the files as a standalone pack.
- The application packages them only as integrated in-game icons.

## Semantic item icons (retired in Phase 8)

- Retired: the numbered SVGs and the `item_icons.png` atlas are no longer packaged. Only the
  semantic data in `item_manifest.json` (names, categories, tiers) remains, for the catalog.
- Source: `Icons_svg` and its semantic manifest.
- Runtime copies: only `item_manifest.json` beneath `src/dd_simulator/ui/assets/icons`;
  the numbered SVG files are no longer packaged.
- Supplied terms: free for personal and commercial use; credit appreciated but not
  required; do not redistribute, resell, or reupload the asset files as a standalone
  pack or claim them as original work.
- Until Phase 8 the application packaged the 1,686 numbered SVGs as integrated game
  assets; it no longer packages them. Item art now comes from the CraftPix library
  icons mapped by `item_icon_manifest.json`.

## CraftPix skill, ability and spell icons

- Source: the owner's CraftPix icon library under `Project Resources/assets/skills/<class>/`.
- Runtime copies: the 52 icons mapped in `power_icon_manifest.json`, downscaled to 128 px
  PNGs beneath `src/dd_simulator/ui/assets/icons/powers` by `scripts/import_power_icons.py`.
- Supplied terms: CraftPix free license (https://craftpix.net/file-licenses/); use in the
  game is permitted; do not redistribute, resell, or reupload the files as a standalone pack.
- The application packages them only as integrated in-game icons.

## Interface sound effects

- Runtime copies: `src/dd_simulator/ui/assets/audio/ui/<event>.wav` (44.1 kHz mono,
  peak-levelled), decoded by `scripts/import_ui_sfx.py`; per-file source, SHA-256, author
  and license in `audio/ui/sources.json`.
- Kenney, RPG Audio (https://kenney.nl/assets/rpg-audio), CC0-1.0: `page` (bookFlip1),
  `pickup` (handleSmallLeather), `drop` (dropLeather), `equip` (beltHandle1), `unequip`
  (cloth2), `coins` (handleCoins). Source copies under `Untitled RPG/Assets/.CC0 Assets/Audio/SFX/KenneyRPGAudio`.
- 80-CC0-RPG-SFX, CC0-1.0, as levelled by Untitled RPG `Tools/build_sfx_pack.py`: `click`
  (item_wood_02), `deny` (lock_01).
- Original synthesis by the Untitled RPG project: `hover` (`Audio/SFX/UI/ui_hover_1.wav`).
- Not used: the "Sound FX Starter Pack" (royalty-free, not CC0) and every combat, spell
  and creature clip; interface sounds only.

## Music and ambience (Untitled RPG)

- Source: `Untitled RPG/Assets/Audio/Music` and `Audio/Ambience`; provenance in that
  project's `Assets/Audio/SOURCES.md`.
- Runtime copies: unchanged files beneath `src/dd_simulator/ui/assets/audio`, copied by
  `scripts/import_audio.py`; mapping in `music_manifest.json` (see `docs/AUDIO.md`).
- Supplied as CC0; verify before public release. SOURCES.md records no per-track creator
  or license for these:
  - `menu/music_menu.mp3` ("Shores of Yore"), `town/music_village_day.mp3` ("Awakening"),
    `town/music_village_night.mp3` ("Akash Chamber"),
    `forest_wilderness/music_forest_day.mp3` ("Faerie Shrine"),
    `forest_wilderness/music_forest_night.mp3` ("Aural"): from a folder named CC0.
  - `battle/combat_1_better_tomorrow_metal.ogg` to `battle/combat_7_survive.ogg`: from a
    folder named CC0, converted to OGG by the Untitled RPG project.
- Original synthesis by the Untitled RPG project (`generate_audio.py`):
  `boss/music_boss.wav`, `exploration_cave/music_cave.wav`, the five `ambience/amb_*.wav`
  loops, and the unused fallbacks `battle/music_combat.wav`,
  `forest_wilderness/music_forest.wav` and `town/music_village.wav`.

## UI Pack 3

- Creator: Kibyra.
- Runtime use: three colored 32×32 icons for Map, People, and Settings.
- Supplied terms: free for personal and commercial use; credit appreciated but not
  required; do not redistribute or resell the files as a standalone pack.

Anyone distributing the application remains responsible for retaining these notes and
confirming that the intended distribution complies with the supplied asset terms.

## Original Release 26 textures

- Runtime files: `charcoal-stone-surface.jpg`, `dark-leather-surface.jpg`, and
  `hammered-iron-surface.jpg` in the Default theme's assets directory.
- These are original project surfaces generated with OpenAI's built-in image generation
  for this application; no third-party texture source was used.
- Full-resolution generation outputs are retained under
  `artifacts/release26/production-texture-sources` (removed in the 2026-10-27 cleanup) for project history.
- Release 26.1 adds an original corner-only nine-slice frame, divider/header flourishes,
  an open-center compass overlay, and splitter grips generated for the approved mockup
  correction. Their chroma-key sources are retained beside the texture sources.
- Release 26.4 uses `charcoal-stone-tile.png`, a 96×96 derivative of the original
  charcoal surface used for seamless native-scale repetition.

## Supplied Release 26.5 background

- Source: `Project Resources/background2.png`, supplied by the project owner.
- Runtime copy: `src/dd_simulator/ui/themes/default/assets/background2.png`.
- The runtime copy is resized and converted to RGB to reduce package and paint cost;
  the supplied source file remains unchanged.

## Supplied Release 26.6 background and card references

- Background source: `Project Resources/background.jpg`, supplied by the project owner.
- Card sources: `Project Resources/cards/Uncommon.png`, `Rare.png`, `Epic.png`, and
  `buttons_misc.png`, supplied by the project owner.
- Runtime files: `background.jpg`, `card-frame-uncommon.png`, `card-frame-rare.png`,
  and `card-frame-epic.png` under the Default theme assets.
- Runtime derivatives retain only the artwork required by the integrated interface;
  every supplied source remains unchanged.

## Supplied Release 26.7 background and Deep Dark Fantasy UI

- Background source: `Project Resources/background_dark.jpg`, supplied by the project
  owner. Its last runtime copy, in the Modern Fantasy Simple theme, was retired by the
  Concept B chrome below and is no longer packaged.
- UI source: `Project Resources/ui_final/ornate_fantasy_ui_svg_labeled/themes/`
  `deep_dark_fantasy`, supplied by the project owner.
- Runtime selection: 27 labeled SVG panel, button, progress, divider, scrollbar, and
  ornament files under `assets/deep-dark`. The full source library remains unchanged.
- These assets style only the Default theme. Existing semantic item and skill icons are
  neither replaced nor modified by Release 26.7.

## Supplied inventory and equipment layout art

- Sources: `Project Resources/Inventory_Slot_1.png` and
  `Project Resources/Inventory_Example_01.png`, supplied by the project owner.
- Runtime copies: `src/dd_simulator/ui/assets/inventory`, packaged unchanged.
- Application rendering crops only the transparent margin of the individual slot and
  otherwise preserves the authored colors; the supplied source files are not modified.
- Occupied equipment targets reuse that same packaged slot image as a precisely aligned
  cell overlay. Empty targets continue to show the board's original silhouettes.

## Concept T codex assets (UI redesign Phase 1)

Imported by `scripts/import_codex_assets.py`, which records every source path and can be
re-run to reproduce the runtime copies byte for byte. `scripts/flatten_codex_speckle.py`
then flattens the speckled fill of the panel, tooltip, button and tab frames (stretched
over large cards it showed as low-resolution spots); rerun it after a re-import.

- **UI frames and markers.** Runtime copies: the PNGs in `src/dd_simulator/ui/assets/codex`
  (frames, original size) and `codex/markers` (downscaled to 64 px). Sources:
  `Untitled RPG/Assets/Art/UI/Textures` and `Untitled RPG/Assets/Art/UI/Source/Icons`.
  This art is original: it is drawn in code by the project owner's Untitled RPG project
  (`Tools/art/flat_library.py`) and can be regenerated at a higher resolution there.
- **Portrait fallbacks.** Runtime copies: `codex/portraits/<pack>/1.png` … `50.png`, downscaled
  from 512 px to 256 px. Sources: the `PNG/background` folder of the RPG Mega packs
  `Free RPG Fantasy Avatars` (`fantasy`), `rpg-avatar-dwarf-icons` (`dwarf`),
  `rpg-avatar-goblin-icons` (`goblin`), `rpg-avatar-fairy-icons` (`fairy`),
  `rpg-avatar-demon-icons` (`demon`) and `50-rpg-avatar-undead-icons` (`undead`) under
  `Untitled RPG/Assets/RPG Mega`. Creator: CraftPix. License: in-game use allowed; no
  standalone redistribution of the files (https://craftpix.net/file-licenses/). The
  application ships them only as integrated game assets.
- **Oxanium font.** Runtime copies: `Oxanium-Regular.ttf`, `Oxanium-SemiBold.ttf` and
  `Oxanium-Bold.ttf` in `src/dd_simulator/ui/assets/fonts`, from
  `Untitled RPG/Assets/Fonts/Oxanium`. SIL Open Font License 1.1; the license text ships
  beside the fonts as `oxanium-ofl.txt`.

## Application icon (original, generated in code)

- `src/dd_simulator/ui/assets/icons/app/dd_simulator.ico` (16-256 px) and `dd_simulator.png`
  (512 px): a gold d20 on a crimson tile, drawn with QPainter by
  `scripts/generate_app_icon.py`; the "20" uses the bundled Oxanium Bold. No third-party
  art. Rerunning the script reproduces the files.

## Concept B title bar and page backgrounds (original, generated in code)

- Original art, drawn procedurally with QPainter and seeded noise by
  `scripts/generate_chrome_textures.py`; no third-party source. Rerunning the script
  reproduces the files.
- Modern Fantasy Simple (`themes/high_fantasy/assets`): `background_stone.jpg` (smooth dark
  umber, candlelight from the top), `header_crest.png`, `header_rule_left.png`,
  `header_rule_right.png`, `title_rule_left.png`, `title_rule_right.png`.
- Modern Dark Simple (`themes/modern_proof/assets`): `background_charcoal.jpg`,
  `header_crest.png`, `header_rule_left.png`, `header_rule_right.png`,
  `title_rule_left.png`, `title_rule_right.png`, `dropdown_arrow.png`.
