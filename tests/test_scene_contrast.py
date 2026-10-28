import importlib.util
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Brightest conversation bands of the 95 location images (scripts/check_scene_contrast.py).
BRIGHTEST = ("castle/castle_daylight", "mountain/mountain_snow", "cave/cave_sunset", "road/road_snow", "village/village_snow")


def _import_script():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "check_scene_contrast", PROJECT_ROOT / "scripts" / "check_scene_contrast.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_narration_keeps_4_5_contrast_over_the_brightest_location_art() -> None:
    _app = QApplication.instance() or QApplication([])
    script = _import_script()
    colors = script.theme_colors()
    assert {"high_fantasy", "modern_proof"} <= set(colors)
    for theme_id, (overlay, narrator) in colors.items():
        for name in BRIGHTEST:
            path = script.UI / "assets" / "location" / f"{name}.png"
            ratio = script.contrast(script.luminance(narrator), script.band_luminance(path, overlay))
            assert ratio >= script.MINIMUM, f"{theme_id} {name}: {ratio:.2f}:1"
