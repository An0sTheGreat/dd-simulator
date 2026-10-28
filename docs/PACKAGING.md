# Release 27 Packaging and First Run

Build with `scripts\build.ps1`. Run only
`dist\DnDSimulator\DnDSimulator.exe` beside its `_internal` directory. The executable
under `build` is a PyInstaller intermediate and cannot run independently.

First launch creates `%APPDATA%\DnDSimulator` unless `DDSIM_CONFIG_DIR` overrides it.
Settings reports package mode, storage path, and database schema readiness. A damaged
ledger still opens the established in-memory recovery campaign without overwriting the
original file.

To use Unsloth Studio, start it on a fixed localhost port (for example
`unsloth studio -p 8888`) and create an API key under **Settings → API**. Enter the port
and key in Local AI Setup, press Refresh Models, select a model, then press Load Selected
Model (or load it manually in Unsloth Studio). Selection, loading, and evaluation never
mutate campaign state. LM Studio remains available as a secondary server on port 1234
(see `UNSLOTH.md`).

Package verification:

```powershell
$env:DDSIM_CONFIG_DIR = "$env:TEMP\ddsim-release26-8-1-smoke"
& .\dist\DnDSimulator\DnDSimulator.exe --smoke-test-release26-8-3
```

Release 26 packages the compiled themes, fonts, semantic item manifest, all numbered
semantic SVGs, three small UI-pack navigation icons, and three original Default-theme
texture surfaces. See `ASSET_CREDITS.md` before redistributing the build.
Release 26.1 also packages the transparent ornamental frame, header flourish, compass,
and splitter-grip assets used exclusively by Default.
Release 26.4 packages the 96-pixel stone tile and rectangular minimap presentation.
Release 26.5 packages the optimized `background2.png` runtime surface, 32-slot paged
inventory presentation, restored minimap/hover ornament, and curated semantic mappings.
Release 26.6 packages the optimized `background.jpg`, supplied rarity card frames and
button rail, centered Character Sheet, shared item/ability cards, and live compass overlay.
Release 26.7 adds the supplied `background_dark.jpg` runtime copy and the selected
Deep Dark Fantasy SVG panel, button, progress, divider, scrollbar, and ornament assets.
The historical Release 26 smoke aliases remain compatible packaged smoke entrypoints.

Release 26.7 maintenance removes that Default theme and all of its runtime assets from
the package. Current builds contain only Modern Fantasy Simple and Modern Dark Simple;
the latest smoke path verifies both themes and their opaque item-hover surfaces.

The current maintenance build also packages the owner-supplied `Inventory_Slot_1.png`
and `Inventory_Example_01.png` under `ui/assets/inventory`. Their authored colors are
displayed unchanged in both supported themes. The same packaged slot image is reused for
exact occupied-equipment-cell overlays; no duplicate runtime asset is required.

The Concept B chrome replaces the 10 MB `background_dark.jpg` with generated title-bar
ornaments and page backgrounds (about 45 KB across both themes) under each theme's
`assets/` folder, which the existing `ui/themes/*/assets/*` package-data glob covers.
