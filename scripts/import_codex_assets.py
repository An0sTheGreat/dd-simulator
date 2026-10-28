"""Import the Concept T codex assets from the owner's Untitled RPG project.

UI frames are copied at their original size, markers are downscaled to 64 px,
RPG Mega portrait fallbacks to 256 px, and the Oxanium font is copied as-is.
Every source is checked before anything is written, and files whose bytes
already match are left untouched, so re-running the script changes nothing.

Usage: python scripts/import_codex_assets.py [UNTITLED_RPG_ASSETS_ROOT]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage


DEFAULT_SOURCE_ROOT = Path(r"Y:\Games\Untitled RPG\Assets")
UI_ASSETS = Path(__file__).resolve().parents[1] / "src" / "dd_simulator" / "ui" / "assets"
CODEX_ROOT = UI_ASSETS / "codex"
FONT_ROOT = UI_ASSETS / "fonts"

FRAMES = (
    "ui_panel_large", "ui_panel_small", "ui_tooltip", "ui_slot_frame", "ui_slot_selected",
    "ui_rarity_common", "ui_rarity_uncommon", "ui_rarity_rare", "ui_rarity_epic",
    "ui_rarity_legendary", "ui_button_normal", "ui_button_hover", "ui_button_pressed",
    "ui_button_disabled", "ui_tab_normal", "ui_tab_active", "ui_divider",
    "ui_ornamental_corner", "ui_quest_tracker", "ui_progress_bar_frame",
)
MARKERS = (
    "ui_checkbox_checked", "ui_dropdown_arrow",
    "ui_icon_guard", "ui_icon_mage", "ui_icon_potion", "ui_icon_pugilist", "ui_icon_ranger",
    "ui_icon_swordsman", "ui_marker_boss", "ui_marker_cursor", "ui_marker_dungeon",
    "ui_marker_npc_service", "ui_marker_party", "ui_marker_player", "ui_marker_quest_main",
    "ui_marker_quest_objective", "ui_marker_quest_side", "ui_marker_service_inn",
    "ui_marker_service_merchant", "ui_marker_service_smith", "ui_marker_service_trainer",
    "ui_marker_undiscovered", "ui_marker_waypoint", "ui_marker_waystone",
)
MARKER_SIZE = 64
PORTRAIT_PACKS = {
    "fantasy": "Free RPG Fantasy Avatars",
    "dwarf": "rpg-avatar-dwarf-icons",
    "goblin": "rpg-avatar-goblin-icons",
    "fairy": "rpg-avatar-fairy-icons",
    "demon": "rpg-avatar-demon-icons",
    "undead": "50-rpg-avatar-undead-icons",
}
PORTRAITS_PER_PACK = 50
PORTRAIT_SIZE = 256
FONT_FILES = {  # source name -> bundled name
    "Oxanium-Regular.ttf": "Oxanium-Regular.ttf",
    "Oxanium-SemiBold.ttf": "Oxanium-SemiBold.ttf",
    "Oxanium-Bold.ttf": "Oxanium-Bold.ttf",
    "SIL Open Font License.txt": "oxanium-ofl.txt",
}


def import_jobs(source_root: Path) -> list[tuple[Path, Path, int | None]]:
    """Return (source, target, downscale size or None for a byte copy) for every asset."""

    ui = source_root / "Art" / "UI"
    jobs: list[tuple[Path, Path, int | None]] = []
    jobs += [(ui / "Textures" / f"{name}.png", CODEX_ROOT / f"{name}.png", None) for name in FRAMES]
    jobs += [
        (ui / "Source" / "Icons" / f"{name}.png", CODEX_ROOT / "markers" / f"{name}.png", MARKER_SIZE)
        for name in MARKERS
    ]
    for pack, folder in PORTRAIT_PACKS.items():
        source = source_root / "RPG Mega" / folder / "PNG" / "background"
        jobs += [
            (source / f"{n}.png", CODEX_ROOT / "portraits" / pack / f"{n}.png", PORTRAIT_SIZE)
            for n in range(1, PORTRAITS_PER_PACK + 1)
        ]
    jobs += [
        (source_root / "Fonts" / "Oxanium" / name, FONT_ROOT / bundled, None)
        for name, bundled in FONT_FILES.items()
    ]
    return jobs


def _downscaled_png(source: Path, size: int) -> bytes:
    image = QImage(str(source))
    if image.isNull():
        raise SystemExit(f"Cannot read image: {source}")
    image = image.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG", 0):  # quality 0 = strongest PNG compression
        raise SystemExit(f"Cannot encode image: {source}")
    return bytes(buffer.data())


def main(argv: list[str]) -> int:
    source_root = Path(argv[1]) if len(argv) > 1 else DEFAULT_SOURCE_ROOT
    jobs = import_jobs(source_root)
    missing = [str(source) for source, _, _ in jobs if not source.is_file()]
    if missing:
        raise SystemExit("Missing source files:\n  " + "\n  ".join(missing))

    written = 0
    for source, target, size in jobs:
        data = source.read_bytes() if size is None else _downscaled_png(source, size)
        if target.is_file() and target.read_bytes() == data:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written += 1
    print(f"{len(jobs)} assets checked, {written} written.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
