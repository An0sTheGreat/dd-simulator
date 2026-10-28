import importlib.util
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFontDatabase, QImage
from PySide6.QtWidgets import QApplication

from dd_simulator.ui.fonts import register_application_fonts
from dd_simulator.ui.themes.theme_schema import REQUIRED_TOKEN_PATHS, ThemeDefinition


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = PROJECT_ROOT / "src" / "dd_simulator" / "ui"
CODEX_KEYS = [path.split(".", 1)[1] for path in REQUIRED_TOKEN_PATHS if path.startswith("codex.")]


def _import_script():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "import_codex_assets", PROJECT_ROOT / "scripts" / "import_codex_assets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _theme_manifest(theme_id: str) -> dict:
    return json.loads((UI_ROOT / "themes" / theme_id / "theme.json").read_text(encoding="utf-8"))


def test_every_codex_asset_exists_and_loads() -> None:
    script = _import_script()
    images = [target for _, target, _ in script.import_jobs(Path("unused")) if target.suffix == ".png"]

    assert len(images) == 20 + 24 + 6 * 50
    for target in images:
        assert target.is_file(), target
        image = QImage(str(target))
        assert not image.isNull(), target
        if target.parent.name == "markers":
            assert max(image.width(), image.height()) == 64, target
        elif target.parent.parent.name == "portraits":
            assert (image.width(), image.height()) == (256, 256), target


def test_oxanium_is_registered() -> None:
    QApplication.instance() or QApplication([])

    assert "Oxanium" in register_application_fonts()
    assert "Oxanium" in QFontDatabase.families()


def test_both_themes_carry_codex_tokens() -> None:
    assert len(CODEX_KEYS) == 33
    fantasy = _theme_manifest("high_fantasy")
    dark = _theme_manifest("modern_proof")
    for manifest in (fantasy, dark):
        ThemeDefinition.from_mapping(manifest)
        assert sorted(manifest["tokens"]["codex"]) == sorted(CODEX_KEYS)

    codex = fantasy["tokens"]["codex"]
    assert codex | {
        "ink": "#ecdfc3", "muted": "#a6967a", "gold": "#d9b46c", "gold_dark": "#7d6034",
        "success": "#9fc27a", "rarity_common": "#e8e0d0", "rarity_uncommon": "#9fd77e",
        "rarity_rare": "#7fb6ff", "rarity_epic": "#b9a3ff", "rarity_legendary": "#f0a050",
        "bubble_player": "rgba(58, 44, 26, 0.82)", "bubble_player_border": "#6a522c",
        "bubble_npc": "rgba(22, 18, 13, 0.88)",
    } == codex
    frames = [key for key in CODEX_KEYS if key.startswith("frame_")]
    for key in frames:
        assert (UI_ROOT / "assets" / codex[key]).is_file(), key
        assert dark["tokens"]["codex"][key] == "", key
