# Release 26 approved asset inventory

Current status: this document is historical. The Default theme and all runtime copies
described below were removed during Release 26.7 maintenance; source resources and
production artifacts remain untouched.

Inventory date: 2026-07-23

Scope: `Project Resources/dnd_ui_source/assets`. The inventory did not modify the source
asset folders. The approved implementation adds only original runtime textures beneath
the application's isolated Default theme.

## Available assets

### UI_pack_3

- 144 individual transparent PNG assets:
  - 64 colored HUD/interaction icons at 32 x 32.
  - 64 muted HUD/construction elements at 32 x 32.
  - 16 fantasy menu controls at 64 x 32.
- Three supplied overview sheets: two at 256 x 256 and one at 256 x 128.
- The pack permits personal and commercial use. Credit to Kibyra is appreciated but
  optional. Redistribution or resale of the files as-is is prohibited.

The individual filenames are numeric rather than semantic. These assets are suitable
for a small, manually approved set of navigation/status accents. They are not suitable
for automatic generated-item matching, and the menu buttons contain baked-in English
labels that prevent reuse for arbitrary controls.

### Icons_svg

- 1,686 numbered semantic item SVGs plus one full vector overview sheet.
- Stable semantic manifests in JSON and CSV.
- Tier distribution: Tier 0: 161; Tier 1: 368; Tier 2: 512; Tier 3: 351; Tier 4: 294.
- Largest categories: weapon 597, spell 340, armor 321, skill 99, food 91, material 84,
  and potion 73.
- Personal and commercial use is permitted; redistribution or resale as-is is not.

These remain the authoritative item-image pool. They should not be stretched into UI
surfaces or used as background decoration.

### Existing scene art

- `avatar.png`: 99 x 125 character portrait.
- `greystone-road.png`: 208 x 124 location visual.
- `world-map.png`: 338 x 260 framed world map.

The map supplies the strongest approved material language: dark masonry, aged bronze,
and restrained ornament. The portrait and location visual provide useful warm-light and
natural-color anchors.

## Practical UI mapping

| UI need | Approved source | Recommendation |
| --- | --- | --- |
| Item art | Icons_svg | Continue deterministic semantic resolution and rarity selection. |
| Navigation accents | Selected UI_pack_3 icons | Manually map only clearly understood icons such as Map, People, and Settings. |
| Major frame language | world-map.png reference | Reproduce with QSS borders and purpose-built nine-slice assets; do not stretch the map itself. |
| Buttons and tabs | UI_pack_3 reference plus QSS | Use native text with bevels and state colors; avoid baked-text menu PNGs. |
| Splitter grips | UI_pack_3 frame/rivet reference plus QSS | Use a narrow themed handle with a small central grip. Preserve existing splitter behavior. |
| Resource bars | QSS | Carved trough, colored fill, readable value text, and no resource icons. |
| Panel interiors | New approved texture assets required | The supplied folders contain no seamless leather, stone, parchment, or metal textures. |
| Application background | New approved texture asset required | Use a subtle seamless charcoal-stone texture; maintain text contrast. |

## Gaps at inventory time

The approved folders do not contain tileable backgrounds, scalable panel skins,
nine-slice borders, generic button surfaces, or splitter textures. QSS can provide
gradients, borders, bevels, and interaction states, but convincing organic texture will
require a small original texture set approved separately before implementation.

Recommended minimum new artwork:

1. One seamless charcoal-stone background.
2. One seamless dark-leather panel texture.
3. One compact bronze/iron nine-slice frame.
4. One generic textured button surface without baked text.
5. One horizontal and one vertical splitter grip.

## Implemented Release 26 assets

The approved mockup was implemented with three original, low-contrast production
surfaces generated specifically for the application:

1. Seamless charcoal stone for application rails and structural backgrounds.
2. Dark worn leather for panel interiors and compact cards.
3. Hammered blackened iron for headers, footers, splitters, and control accents.

Compact 512-pixel PNG variants are stretched through Qt's native border-image renderer,
preventing seams at arbitrary window sizes while keeping paint and package costs bounded.
The 2048 x 1080 JPEG design surfaces remain as retained production intermediates. All
live paths are beneath
`src/dd_simulator/ui/themes/default/assets`; full-resolution source outputs are retained
under `artifacts/release26/production-texture-sources` (removed in the 2026-10-27 cleanup).

## Mockup status

The Release 26 mockup was the approved design target. The production pass preserves the
current dashboard layout, item icons, rarity colors, inventory density, and splitter
boundaries while implementing textured surfaces, bronze framing, carved resource bars
without icons, and stronger visual hierarchy.

Release 26.4 renders `charcoal-stone-tile.png` at 96 x 96 pixels and repeats it at native
scale to reduce the apparent masonry size without introducing stretched surfaces.

Release 26.5 replaces that application surface with the project-owner-supplied
`Project Resources/background2.png`. The runtime copy is resized to 1920 pixels wide
and converted to RGB for predictable Qt painting and package size. The supplied source
and every file under `Project Resources/dnd_ui_source` remain untouched. Existing
ornamental assets continue to frame the minimap and now frame item-hover cards.

Release 26.6 replaces the runtime surface with a 3840-pixel, high-quality optimized
copy of `Project Resources/background.jpg`. Transparent derivatives of the supplied
Uncommon, Rare, Epic, and miscellaneous-button card artwork provide rarity card frames
and a reusable control rail. The source card sheets, background, and `dnd_ui_source`
remain unchanged.

Release 26.7 replaces only the Default backdrop with the project-owner-supplied
`Project Resources/background_dark.jpg` and packages an unchanged runtime copy as
`background-dark.jpg`. Twenty-seven labeled SVGs from the supplied
`ui_final/ornate_fantasy_ui_svg_labeled/themes/deep_dark_fantasy` set provide shared
panels, buttons, resource frames, dividers, scrollbars, and ornaments. The complete
source library, semantic item icons, and semantic skill icons remain unchanged.

- Contact sheet: `artifacts/release26/approved-ui-assets-contact-sheet.png` (removed in the 2026-10-27 cleanup)
- Mockup: `artifacts/release26/release26-default-theme-mockup.png` (removed in the 2026-10-27 cleanup)
- Generation method: built-in image generation, using the current application screenshot
  as the edit target and the approved contact sheet as the supporting style reference.

## Release 26.1 fidelity correction

The first production pass reproduced the palette and broad textures but not the mockup's
ornamental structure. Release 26.1 adds a scalable corner-only nine-slice frame, separate
header/divider flourishes, an open-center minimap compass, and orientation-specific
splitter grips. Near-black native gradients now replace the oversized brown leather
fields. The transparent runtime assets and their retained chroma-key generation sources
remain project-owned and isolated to Default.
