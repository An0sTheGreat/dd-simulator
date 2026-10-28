# Release 26.7 Asset Credits and Distribution Notes

Current packaging note: the Default theme and every Default-only runtime derivative
listed below have been removed from the application. The entries remain as historical
source attribution; supplied files under Project Resources are unchanged.

Release 24 uses only assets currently present under
`Project Resources/dnd_ui_source/assets`.

## Semantic item icons

- Source: `Icons_svg` and its semantic manifest.
- Runtime copies: the numbered SVG files and `item_manifest.json` beneath
  `src/dd_simulator/ui/assets/icons`.
- Supplied terms: free for personal and commercial use; credit appreciated but not
  required; do not redistribute, resell, or reupload the asset files as a standalone
  pack or claim them as original work.
- The application packages and resolves the 1,686 numbered SVGs as integrated game
  assets rather than redistributing them as a standalone pack.

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
  owner; runtime copy: `assets/background-dark.jpg` in the Default theme.
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
